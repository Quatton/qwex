use std::{collections::VecDeque, path::PathBuf};

use crate::pipeline::{ast::Module, cache::Store};

mod ast;
mod cache;
mod context;
mod error;
mod loader;
mod parser;
mod renderer;
mod resolver;

/// Shared pipeline configuration.
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

pub enum QueueItem {
    File(PathBuf),
    Task(String),
}

pub struct Pipeline {
    config: Config,
    file_queue: VecDeque<(PathBuf, String, String)>,
    path_to_string: Store<PathBuf, String>,
    path_to_ast: Store<String, Module>,
    alias_to_path: Store<String, PathBuf>,
    alias_to_ast: Store<String, Module>,
}

impl Pipeline {
    pub fn new(config: Config) -> Self {
        Pipeline {
            config,
            file_queue: VecDeque::new(),
            path_to_string: Store::new(),
            path_to_ast: Store::new(),
            alias_to_ast: Store::new(),
            alias_to_path: Store::new(),
        }
    }

    pub fn build(&mut self) -> Result<(), error::PipelineError> {
        let source_path = self.config.source_path.clone();
        self.file_queue
            .push_back((source_path, "".to_string(), "".to_string()));
        // let env = minijinja::Environment::new();

        while !self.file_queue.is_empty() {
            // 1. Process file queue and process ASTs
            while let Some((file_path, from, alias)) = self.file_queue.pop_front() {
                let module = self.parse(file_path, from, alias)?;
                println!("Parsed module: {:?}", module);
            }
        }

        Ok(())
    }
}

// module -> root tasks -> find dependencies ->
