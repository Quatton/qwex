use ahash::RandomState;

use serde::{Deserialize, Serialize};

pub type IHashMap<K, V> = indexmap::IndexMap<K, V, ahash::RandomState>;
pub type IHashSet<V> = indexmap::IndexSet<V, ahash::RandomState>;
pub type Props = IHashMap<String, minijinja::Value>;

pub const TASK_PREFIX: &str = "tasks";
pub const PROP_PREFIX: &str = "props";

#[derive(Default, Debug, Clone, Serialize, Deserialize)]
pub struct MetaModule {
    #[serde(flatten)]
    pub module: Module,

    #[serde(skip)]
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
    pub tasks: IHashMap<String, Task>,

    #[serde(flatten, default)]
    pub modules: IHashMap<String, Module>,
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
            props: Props::with_hasher(RandomState::with_seed(0)),
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
