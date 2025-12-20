use ahash::HashMap;
use serde::{Deserialize, Serialize};

use crate::pipeline::context::Props;

pub const TASK_INLINE_KEYWORD: &str = "cmd";
pub const TASK_PREFIX: &str = "tasks";
pub const PROP_PREFIX: &str = "props";

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
pub struct Module {
    pub uses: Option<String>,

    #[serde(default)]
    pub props: Props,
    pub tasks: HashMap<String, Task>,

    #[serde(flatten, default)]
    pub modules: HashMap<String, Module>,
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

/*
module1:
    uses: "builtin://log.yaml"
    features:
        - "featureA"

props:
    prop1: "value1"

tasks:
    task1:
        props: "pp"
        cmd: "echo Hello"
*/
