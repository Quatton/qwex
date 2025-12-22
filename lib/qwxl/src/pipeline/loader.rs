use std::fs::OpenOptions;
use std::sync::Arc;

use crate::pipeline::{Pipeline, error::PipelineError};

macro_rules! accept {
    ($name:expr) => {
        concat!($name, ".yaml") | concat!($name, ".yml") | concat!($name)
    };
}

macro_rules! builtin {
    ($name: expr) => {
        include_str!(concat!("./builtins/", $name, ".yaml"))
    };
}

fn read_to_string(path: &str) -> Result<String, PipelineError> {
    if path.starts_with("@std/") {
        let name = path.trim_start_matches("@std/");

        // log, steps, test, utils
        match name {
            accept!("log") => Ok(builtin!("log").to_string()),
            accept!("steps") => Ok(builtin!("steps").to_string()),
            accept!("test") => Ok(builtin!("test").to_string()),
            accept!("utils") => Ok(builtin!("utils").to_string()),
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
