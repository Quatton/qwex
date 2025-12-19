use std::collections::BTreeMap;

use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(untagged)]
pub enum Resource {
    Local(std::path::PathBuf),
    Remote(String),
    BuiltIn(std::path::PathBuf),
}

impl From<String> for Resource {
    fn from(s: String) -> Self {
        if s.starts_with("http://") || s.starts_with("https://") {
            Resource::Remote(s)
        } else if s.starts_with("builtin://") {
            let path = s.trim_start_matches("builtin://");
            Resource::BuiltIn(std::path::PathBuf::from(path))
        } else {
            Resource::Local(std::path::PathBuf::from(s))
        }
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ModuleFile {
    pub default: Module,

    #[serde(flatten)]
    pub features: BTreeMap<String, Module>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Module {
    pub extends: Option<String>,
    pub modules: Option<BTreeMap<String, ModuleRef>>,
    pub props: Option<Props>,
    pub tasks: BTreeMap<String, Task>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ModuleRef {
    pub uses: String,
    pub features: Option<Vec<String>>,
    pub props: Option<Props>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(untagged)]
pub enum Task {
    Cmd {
        props: Option<Props>,
        // You can use either "cmd" or "command" or "run" as the key for the command string
        // Nah not anymore
        // #[serde(alias = "command", alias = "run")]
        cmd: String,
    },
    Uses {
        props: Option<Props>,
        uses: String,
    },
}

pub type Props = BTreeMap<String, ron::Value>;
