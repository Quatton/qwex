use std::sync::Arc;
use std::{fs::OpenOptions, path::PathBuf};

use crate::pipeline::{Pipeline, error::PipelineError};

fn read_to_string(path: &PathBuf) -> Result<String, PipelineError> {
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

impl Pipeline {
    pub fn load_file(&mut self, path: PathBuf) -> Result<Arc<String>, PipelineError> {
        self.path_to_string
            .query_or_compute_with(path.clone(), || read_to_string(&path))
    }
}
