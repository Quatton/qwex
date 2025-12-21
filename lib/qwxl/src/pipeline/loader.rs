use std::fs::OpenOptions;
use std::sync::Arc;

use crate::pipeline::{Pipeline, error::PipelineError};

fn read_to_string(path: &str) -> Result<String, PipelineError> {
    if path.starts_with("@std/") {
        let name = path.trim_start_matches("@std/");

        match name {
            // accept both with and without the .yaml extension
            "log.yaml" | "log" => Ok(include_str!("builtins/log.yaml").to_string()),
            "steps.yaml" | "steps" => Ok(include_str!("builtins/steps.yaml").to_string()),
            "test.yaml" | "test" => Ok(include_str!("builtins/test.yaml").to_string()),
            "utils.yaml" | "utils" => Ok(include_str!("builtins/utils.yaml").to_string()),
            other => Err(PipelineError::Io(std::io::Error::new(
                std::io::ErrorKind::NotFound,
                format!("builtin not found: {}", other),
            ))),
        }
    } else {
        tracing::debug!("Loading file from path: {}", path);
        OpenOptions::new()
            .read(true)
            .open(path)
            .and_then(|mut f| {
                let mut contents = String::new();
                use std::io::Read;
                f.read_to_string(&mut contents)?;
                Ok(contents)
            })
            .map_err(PipelineError::from)
    }
}

impl Pipeline {
    pub fn load_file(&mut self, path: &str) -> Result<Arc<String>, PipelineError> {
        self.stores
            .content
            .query_or_compute_with(path.to_string(), || read_to_string(path))
    }
}
