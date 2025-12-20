use std::path::PathBuf;

use crate::pipeline::{
    loader::read_to_string,
    parser::{load_ron, load_yaml},
};

mod ast;
mod cache;
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

pub struct Pipeline {
    config: Config,
    cache: cache::CacheTree,
}

impl Pipeline {
    pub fn new(config: Config) -> Self {
        Pipeline {
            cache: cache::CacheTree::new(),
            config,
        }
    }

    fn parse_with_cache<T: Into<PathBuf>>(
        &mut self,
        path: T,
    ) -> Result<&ast::ModuleFile, error::PipelineError> {
        let source_string = read_to_string(&path.into())?;
        self.cache
            .source_ast_cache
            .query_or_compute_with(source_string.clone(), || {
                match self.config.source_path.extension() {
                    Some(ext) if ext == "ron" => load_ron(&source_string),
                    _ => load_yaml(&source_string),
                }
            })
    }

    pub fn build(&mut self) -> Result<(), error::PipelineError> {
        let source_path = self.config.source_path.clone();
        let module = self.parse_with_cache(source_path)?;

        Ok(())
    }
}

// module -> root tasks -> find dependencies ->
