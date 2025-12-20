use thiserror::Error;

#[derive(Debug, Error)]
pub enum PipelineError {
    #[error("Invalid alias format: {0}")]
    InvalidAliasFormat(String),

    #[error("Alias already exists: {0}")]
    AliasAlreadyExists(String),

    #[error("Import alias not found: {0}")]
    ImportAliasNotFound(String),

    #[error("Unknown file format: {0}")]
    UnsupportedFormat(String),

    #[error(transparent)]
    Serde(#[from] serde_saphyr::Error),

    #[error(transparent)]
    Io(#[from] std::io::Error),

    #[error(transparent)]
    Ron(#[from] ron::de::SpannedError),

    #[error(transparent)]
    Minijinja(#[from] minijinja::Error),
}
