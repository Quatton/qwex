use std::path::PathBuf;

mod ast;
mod cache;
mod error;
mod parser;

/// Shared pipeline configuration.
pub struct Config {
    pub home_dir: PathBuf,
    pub features: String,
    pub target_path: PathBuf,
    pub source_path: PathBuf,
}

impl Config {
    pub fn make_cache_dir(&self, name: &str) -> PathBuf {
        let path = self.home_dir.join("build").join(name);
        std::fs::create_dir_all(&path).expect("Failed to create cache dir");
        path
    }
}

impl Default for Config {
    fn default() -> Self {
        let cwd = std::env::current_dir().expect("Failed to get current dir");
        let home_dir = cwd.join(".qwex");
        let features = "default".to_string();
        Config {
            target_path: home_dir
                .clone()
                .join("build")
                .join("target")
                .join(features.clone()),
            home_dir,
            features,
            source_path: cwd.join("qwex.yaml"),
        }
    }
}

pub struct Pipeline {
    config: Config,
    parser: parser::Parser,
}

impl Pipeline {
    pub fn new(config: Config) -> Self {
        let parser =
            parser::Parser::with_cache(cache::Cache::with_dir(config.make_cache_dir("ast")));
        Pipeline { config, parser }
    }

    pub fn build(&mut self) -> Result<(), error::PipelineError> {
        let module = match self.config.source_path.extension() {
            Some(ext) if ext == "ron" => self
                .parser
                .load_ron(&std::fs::read_to_string(&self.config.source_path)?),
            _ => self
                .parser
                .load_yaml(&std::fs::read_to_string(&self.config.source_path)?),
        }?;
        Ok(())
    }
}
