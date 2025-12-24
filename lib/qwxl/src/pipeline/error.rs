use thiserror::Error;

use crate::pipeline::ast::IHashSet;

#[derive(Debug, Error)]
pub enum PipelineError {
    #[error("Internal error: {0}")]
    Internal(String),

    #[error("Unimplemented feature: {0}")]
    Unimplemented(String),

    #[error("Cyclic dependency detected for alias: {0:?}")]
    CyclicDependency(IHashSet<String>),

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
