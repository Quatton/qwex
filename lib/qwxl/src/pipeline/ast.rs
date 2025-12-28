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

    #[serde(skip)]
    pub path_buf: std::path::PathBuf,
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
    pub props: Option<Props>,
    #[serde(default)]
    pub tasks: IHashMap<String, Task>,

    #[serde(flatten, default)]
    pub modules: IHashMap<String, Module>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Task {
    pub uses: Option<UseRef>,
    #[serde(default, alias = "with")]
    pub props: Option<Props>,
    #[serde(default, alias = "command", alias = "run")]
    pub cmd: String,
}

impl Default for Task {
    fn default() -> Self {
        Task {
            props: Some(Props::default()),
            cmd: "".to_string(),
            uses: None,
        }
    }
}
