use std::{
    collections::{HashSet, VecDeque},
    path::PathBuf,
    sync::Arc,
};

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
    pub target_path: PathBuf,
    pub features: String,
    pub source_path: PathBuf,
    pub enable_cache: bool,
}

impl Default for Config {
    fn default() -> Self {
        let cwd = std::env::current_dir().expect("Failed to get current dir");
        let home_dir = cwd.join(".qwex");
        let features = "default".to_string();
        Config {
            target_path: cwd.join("build").join(&features).join("qwex.sh"),
            home_dir,
            features,
            source_path: cwd.join("qwex.yaml"),
            enable_cache: true,
        }
    }
}

/// Aggregate stores used by the pipeline. Keeps related stores together
/// so they are easier to reason about and maintain.
#[derive(Debug)]
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

    pub fn compile(&mut self) -> Result<String, PipelineError> {
        let parsed = self.parse_root()?;
        let script = ron::ser::to_string_pretty(&parsed, ron::ser::PrettyConfig::default())?;
        Ok(script)
    }
}
