use std::sync::Arc;

use ahash::{HashMap, HashMapExt as _, HashSet};

use crate::pipeline::{Pipeline, ast::Task, cache::Store};

struct EnvironmentContext {
    module_context: Store<String, String>,
}

#[derive(Debug, serde::Serialize)]
pub enum NodeStatus {
    Pending,
    Resolved,
}

#[derive(Debug, serde::Serialize)]
pub struct NodeRecord {
    pub status: NodeStatus,
    pub node: TaskNode,
}

#[derive(Default, Debug, serde::Serialize)]
pub struct TaskNode {
    pub cmd: String,
    pub deps: HashSet<String>, // aliases of dependent tasks
}

impl Pipeline {
    pub fn resolve_and_render(&self) -> Result<(), crate::pipeline::error::PipelineError> {
        // let mut task_srcs = HashMap::new();

        Ok(())
    }
}

#[cfg(test)]
mod tests {}
