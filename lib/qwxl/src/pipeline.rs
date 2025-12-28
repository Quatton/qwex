use crate::pipeline::{
    ast::MetaModule,
    cache::Store,
    error::PipelineError,
    renderer::{RenderTarget, Resource, SCRIPT_TEMPLATE_NAME, SCRIPT_TEMPLATE_SOURCE},
};
use ahash::HashSet;
use minijinja::Environment;
use serde::Serialize;
use std::{fs::OpenOptions, path::PathBuf, sync::Arc};

mod ast;
mod cache;
mod error;
mod loader;
mod parser;
mod renderer;

/// Shared pipeline configuration.
#[derive(Clone)]
pub struct Config {
    pub cwd: PathBuf,
    pub home_dir: PathBuf,
    pub build_dir: PathBuf,
    pub target_path: PathBuf,
    pub features: String,
    pub source_path: PathBuf,
    pub enable_cache: bool,
    pub root_alias: String,
}

impl Config {
    pub fn get_source_path(&self) -> PathBuf {
        if self.source_path.is_absolute() {
            self.source_path.clone()
        } else {
            self.cwd.join(&self.source_path)
        }
    }

    pub fn get_build_dir(&self) -> PathBuf {
        if self.build_dir.is_absolute() {
            self.build_dir.clone()
        } else {
            self.cwd.join(&self.build_dir)
        }
    }

    pub fn get_home_dir(&self) -> PathBuf {
        if self.home_dir.is_absolute() {
            self.home_dir.clone()
        } else {
            self.cwd.join(&self.home_dir)
        }
    }

    pub fn get_target_path(&self) -> PathBuf {
        if self.target_path.is_absolute() {
            self.target_path.clone()
        } else {
            self.get_build_dir().join(&self.target_path)
        }
    }
}

impl Default for Config {
    fn default() -> Self {
        let cwd = std::env::current_dir().expect("Failed to get current dir");
        let home_dir = PathBuf::from(".qwex");
        let features = "default".to_string().replace(",", "-");
        let build_dir = home_dir.join("target").join(&features);
        Config {
            target_path: build_dir.join("qwex.sh"),
            build_dir,
            home_dir,
            features,
            source_path: PathBuf::from("qwex.yaml"),
            enable_cache: true,
            root_alias: "root".to_string(),
            cwd,
        }
    }
}

/// Aggregate stores used by the pipeline.
#[derive(Debug, Serialize)]
pub struct PipelineStore {
    pub content: Store<PathBuf, String>,
    pub metamodules: Store<u64, MetaModule>,
    pub aliases: Store<String, u64>,
    pub rendered: Store<RenderTarget, Resource>,
    pub 
}

impl Default for PipelineStore {
    fn default() -> Self {
        PipelineStore {
            content: Store::new(),
            metamodules: Store::new(),
            aliases: Store::new(),
            rendered: Store::new(),
        }
    }
}

impl PipelineStore {
    pub fn get_module_by_alias(&self, alias: &str) -> Option<&Arc<MetaModule>> {
        self.aliases
            .get(alias)
            .and_then(|hash| self.metamodules.get(hash))
    }
}

pub struct Pipeline {
    config: Config,
    stores: PipelineStore,
    env: minijinja::Environment<'static>,
}

impl Pipeline {
    pub fn new(config: Config) -> Self {
        let mut env = Environment::new();
        env.add_template(SCRIPT_TEMPLATE_NAME, SCRIPT_TEMPLATE_SOURCE)
            .expect("Failed to load embedded script template");

        Pipeline {
            config,
            stores: PipelineStore::default(),
            env,
        }
    }

    pub fn clean(&self) -> Result<(), PipelineError> {
        if self.config.build_dir.exists() {
            std::fs::remove_dir_all(&self.config.build_dir)?;
        }
        Ok(())
    }

    pub fn compile(&mut self) -> Result<String, PipelineError> {
        let _ = self.parse()?;

        // Example Cache Serialization (optional)
        if self.config.enable_cache {
            let artifacts =
                ron::ser::to_string_pretty(&self.stores, ron::ser::PrettyConfig::default())?;
            let content: Vec<(&PathBuf, &Arc<String>)> = self.stores.content.0.iter().collect();
            let hash = ahash::RandomState::default().hash_one(content);
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

        Ok(("script").to_string())
    }
}
