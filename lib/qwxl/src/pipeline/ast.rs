use std::sync::Arc;

use ahash::{HashMap, HashMapExt as _};
use serde::{Deserialize, Serialize};

use crate::pipeline::context::Props;

pub const TASK_PREFIX: &str = "tasks";
pub const PROP_PREFIX: &str = "props";

#[derive(Default, Debug, Clone, Serialize, Deserialize)]
pub struct MetaModule {
    pub module: Module,
    pub hash: u64,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(untagged)]
pub enum UseRef {
    Define(String),
    Hash(u64),
}

#[derive(Default, Debug, Clone, Serialize, Deserialize)]
pub struct Module {
    pub uses: Option<UseRef>,

    #[serde(default)]
    pub props: Props,
    #[serde(default)]
    pub tasks: HashMap<String, Task>,

    #[serde(flatten, default)]
    pub modules: HashMap<String, Module>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Task {
    pub uses: Option<UseRef>,
    #[serde(default, alias = "with")]
    pub props: Props,
    #[serde(default, alias = "command", alias = "run")]
    pub cmd: String,
}

impl Default for Task {
    fn default() -> Self {
        Task {
            props: Props::new(),
            cmd: "".to_string(),
            uses: None,
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
