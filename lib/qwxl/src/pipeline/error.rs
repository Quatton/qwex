use thiserror::Error;

#[derive(Debug, Error)]
pub enum PipelineError {
    #[error("Invalid alias format: {0}")]
    InvalidAliasFormat(String),

    #[error("Alias already exists: {0}")]
    AliasAlreadyExists(String),

    #[error("Import alias not found: {0}")]
    ImportAliasNotFound(String),

    #[error("Module not found: {0}")]
    ModuleNotFound(String),

    #[error("Task not found: {0}")]
    TaskNotFound(String),

    #[error("Unknown file format: {0}")]
    UnsupportedFormat(String),

    #[error(transparent)]
    SerdeYaml(#[from] serde_saphyr::Error),

    #[error(transparent)]
    Io(#[from] std::io::Error),

    #[error(transparent)]
    Ron(#[from] ron::error::Error),

    #[error(transparent)]
    RonDe(#[from] ron::de::SpannedError),

    #[error(transparent)]
    Minijinja(#[from] minijinja::Error),
}
