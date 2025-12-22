use std::{
    collections::{HashSet, VecDeque},
    fs::OpenOptions,
    path::PathBuf,
    sync::Arc,
};

use serde::Serialize;

use crate::pipeline::{
    ast::Module,
    cache::Store,
    context::Props,
    error::PipelineError,
    renderer::{NodeRecord, TaskNode},
};

mod ast;
mod cache;
mod context;
mod error;
mod loader;
mod parser;
mod renderer;
mod resolver;

/// Shared pipeline configuration.
#[derive(Clone)]
pub struct Config {
    pub home_dir: PathBuf,
    pub build_dir: PathBuf,
    pub target_path: PathBuf,
    pub features: String,
    pub source_path: PathBuf,
    pub enable_cache: bool,
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
        }
    }
}

/// Aggregate stores used by the pipeline. Keeps related stores together
/// so they are easier to reason about and maintain.
#[derive(Debug, Serialize)]
pub struct PipelineStore {
    /// path -> content
    pub content: Store<String, String>,

    /// alias -> source_path
    pub source_paths: Store<String, String>,

    /// resolved_path -> Module
    pub sources: Store<String, Module>,

    /// alias -> Module instance
    pub modules: Store<String, Module>,

    /// alias -> Node
    pub tasks: Store<String, NodeRecord>,

    /// alias -> Value
    pub props: Store<String, minijinja::Value>,
}

impl PipelineStore {
    pub fn new() -> Self {
        PipelineStore {
            content: Store::new(),
            sources: Store::new(),
            source_paths: Store::new(),
            modules: Store::new(),
            tasks: Store::new(),
            props: Store::new(),
        }
    }
}

impl Default for PipelineStore {
    fn default() -> Self {
        Self::new()
    }
}

pub struct Pipeline {
    config: Config,
    stores: PipelineStore,
}

impl Pipeline {
    pub fn new(config: Config) -> Self {
        Pipeline {
            config,
            stores: PipelineStore::new(),
        }
    }

    pub fn clean(&self) -> Result<(), PipelineError> {
        if self.config.build_dir.exists() {
            std::fs::remove_dir_all(&self.config.build_dir)?;
        }
        Ok(())
    }

    pub fn compile(&mut self) -> Result<String, PipelineError> {
        let _ = self.parse_root()?;

        if self.config.enable_cache {
            let artifacts =
                ron::ser::to_string_pretty(&self.stores, ron::ser::PrettyConfig::default())?;

            let content: Vec<(&String, &Arc<String>)> = self.stores.content.0.iter().collect();

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

        Ok("script".to_string())
    }
}
