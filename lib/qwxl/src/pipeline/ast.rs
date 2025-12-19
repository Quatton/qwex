use std::collections::BTreeMap;

use serde::{Deserialize, Serialize};

pub type ModuleFile = BTreeMap<String, Module>;

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Module {
    pub tasks: BTreeMap<String, Task>,
    pub props: Option<Props>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(untagged)]
pub enum Task {
    Cmd {
        props: Option<Props>,
        // You can use either "cmd" or "command" or "run" as the key for the command string
        #[serde(alias = "command", alias = "run")]
        cmd: String,
    },
    Uses {
        props: Option<Props>,
        uses: String,
    },
}

pub type Props = BTreeMap<String, String>;
