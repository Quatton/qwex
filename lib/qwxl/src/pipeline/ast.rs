use ahash::{HashMap, HashMapExt as _};
use serde::{Deserialize, Serialize};

use crate::pipeline::context::Props;

pub const TASK_PREFIX: &str = "tasks";
pub const PROP_PREFIX: &str = "props";

#[derive(Default, Debug, Clone, Serialize, Deserialize)]
pub struct Module {
    pub uses: Option<String>,

    #[serde(default)]
    pub props: Props,
    #[serde(default)]
    pub tasks: HashMap<String, Task>,

    #[serde(flatten, default)]
    pub modules: HashMap<String, Module>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(untagged)]
pub enum Task {
    Cmd {
        #[serde(default, alias = "with")]
        props: Props,
        // You can use either "cmd" or "command" or "run" as the key for the command string
        // Nah not anymore
        #[serde(alias = "command", alias = "run")]
        cmd: String,
    },
    Uses {
        #[serde(default, alias = "with")]
        props: Props,
        uses: String,
    },
}

impl Default for Task {
    fn default() -> Self {
        Task::Cmd {
            props: Props::new(),
            cmd: "".to_string(),
        }
    }
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
