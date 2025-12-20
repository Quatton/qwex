use thiserror::Error;

#[derive(Debug, Error)]
pub enum PipelineError {
    #[error("Unknown file format")]
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
