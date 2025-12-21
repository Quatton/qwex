use std::sync::Arc;

use ahash::HashSet;
use minijinja::Environment;

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

#[derive(Debug, serde::Serialize)]
pub struct TaskNode {
    pub name: String,
    pub cmd: String,
    pub deps: HashSet<Arc<TaskNode>>,
}

pub const SCRIPT_TEMPLATE_NAME: &str = "templates/script.sh.j2";

pub fn register_templates(env: &mut Environment) {
    let script_template = include_str!("templates/script.sh.j2");
    env.add_template(SCRIPT_TEMPLATE_NAME, script_template)
        .expect("Failed to add script_template");
}

#[cfg(test)]
mod tests {}
