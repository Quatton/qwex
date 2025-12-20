use std::{fs::OpenOptions, path::PathBuf};

use crate::pipeline::error::PipelineError;

pub fn read_to_string(path: &PathBuf) -> Result<String, PipelineError> {
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
