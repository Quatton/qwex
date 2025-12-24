use crate::pipeline::{ast::MetaModule, cache::Store, error::PipelineError, renderer::TaskNode};
use serde::Serialize;
use std::{fs::OpenOptions, path::PathBuf, sync::Arc};

mod ast;
mod cache;
mod emitter;
mod error;
mod loader;
mod parser;
mod renderer;

/// Shared pipeline configuration.
#[derive(Clone)]
pub struct Config {
    pub home_dir: PathBuf,
    pub build_dir: PathBuf,
    pub target_path: PathBuf,
    pub features: String,
    pub source_path: PathBuf,
    pub enable_cache: bool,
    pub root_alias: String,
}

impl Default for Config {
    fn default() -> Self {
        let cwd = std::env::current_dir().expect("Failed to get current dir");
        let home_dir = cwd.join(".qwex");
        let features = "default".to_string().replace(",", "-");
        let build_dir = home_dir.join("target").join(&features);
        Config {
            target_path: build_dir.join("qwex.sh"),
            build_dir,
            home_dir,
            features,
            source_path: cwd.join("qwex.yaml"),
            enable_cache: true,
            root_alias: "root".to_string(),
        }
    }
}

/// Aggregate stores used by the pipeline.
#[derive(Debug, Serialize, Default)]
pub struct PipelineStore {
    pub content: Store<PathBuf, String>,
    pub metamodules: Store<u64, MetaModule>,
    pub aliases: Store<String, u64>,
    pub sources: Store<u64, PathBuf>,
    pub tasks: Store<u64, TaskNode>,
}

pub struct Pipeline {
    config: Config,
    stores: PipelineStore,
}

impl Pipeline {
    pub fn new(config: Config) -> Self {
        Pipeline {
            config,
            stores: PipelineStore::default(),
        }
    }

    pub fn clean(&self) -> Result<(), PipelineError> {
        if self.config.build_dir.exists() {
            std::fs::remove_dir_all(&self.config.build_dir)?;
        }
        Ok(())
    }

    pub fn generate_script(&mut self) -> Result<String, PipelineError> {
        let generator = emitter::ShellGenerator::new();
        generator.generate(self)
    }

    pub fn compile(&mut self) -> Result<String, PipelineError> {
        let _ = self.parse()?;

        // Example Cache Serialization (optional)
        if self.config.enable_cache {
            let artifacts =
                ron::ser::to_string_pretty(&self.stores, ron::ser::PrettyConfig::default())?;
            let content: Vec<(&PathBuf, &Arc<String>)> = self.stores.content.0.iter().collect();
            let hash = ahash::RandomState::with_seed(0).hash_one(content);
            let cache_file_name = format!("{:x}.ron", hash);
            let cache_dir = self.config.build_dir.join("cache");
            let cache_path = cache_dir.join(cache_file_name);

            std::fs::create_dir_all(&cache_dir)?;
            OpenOptions::new()
                .create(true)
                .write(true)
                .truncate(true)
                .open(&cache_path)
                .and_then(|mut f| {
                    use std::io::Write;
                    f.write_all(artifacts.as_bytes())
                })?;
        }

        self.generate_script()
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::pipeline::ast::{MetaModule, Module, Task};

    #[test]
    fn test_e2e_compile_cycle() {
        // This is a high-level integration test of the stores + renderer + emitter
        let mut p = Pipeline::new(Config::default());

        // Setup a module graph manually to simulate "parsed" state
        let mut module = Module::default();
        module.tasks.insert(
            "deploy".to_string(),
            Task {
                cmd: "echo deploying".to_string(),
                ..Default::default()
            },
        );

        let meta = MetaModule { module, hash: 123 };
        p.stores.metamodules.insert(123, meta);
        p.stores.aliases.insert("root".to_string(), 123);

        // Compile
        let script = p.generate_script().expect("Failed to generate script");

        assert!(script.contains("root:deploy"));
        assert!(script.contains("echo deploying"));
    }
}
