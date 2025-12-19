use thiserror::Error;

#[derive(Debug, Error)]
pub enum PipelineError {
    #[error("Failed to parse pipeline: {0}")]
    ParseError(String),

    #[error("Invalid module structure: {0}")]
    InvalidModule(String),

    #[error("Task execution error: {0}")]
    TaskExecutionError(String),

    #[error(transparent)]
    Serde(#[from] serde_saphyr::Error),
}
