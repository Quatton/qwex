use std::collections::{HashSet, VecDeque};
use std::sync::Arc;

use minijinja::Environment;
use serde::Serialize;

use crate::pipeline::{Pipeline, error::PipelineError, renderer::TaskNode};

pub const SCRIPT_TEMPLATE_NAME: &str = "script.sh.j2";
const SCRIPT_TEMPLATE_SOURCE: &str = include_str!("templates/script.sh.j2");

#[derive(Serialize)]
struct TemplateTask {
    name: String,
    body: String,
    source: String,
}

/// A stateless generator configuration.
pub struct ShellGenerator;

impl ShellGenerator {
    pub fn new() -> Self {
        Self
    }

    fn setup_env() -> Environment<'static> {
        let mut env = Environment::new();
        env.add_template(SCRIPT_TEMPLATE_NAME, SCRIPT_TEMPLATE_SOURCE)
            .expect("Failed to load embedded script template");
        // Indentation filter removed as requested to support heredocs safely
        env
    }

    pub fn generate(&self, pipeline: &mut Pipeline) -> Result<String, PipelineError> {
        let root_alias = pipeline.config.root_alias.clone();

        // 1. Identify Root Tasks (Entry Points)
        let root_hash = pipeline
            .stores
            .aliases
            .get(&root_alias)
            .ok_or_else(|| PipelineError::Internal("Root alias not found".to_string()))?;

        let root_task_names: Vec<String> = {
            let meta = pipeline
                .stores
                .metamodules
                .get(root_hash)
                .ok_or_else(|| PipelineError::Internal("Root module not found".to_string()))?;
            meta.module.tasks.keys().cloned().collect()
        };

        let mut tasks_to_render: Vec<TemplateTask> = Vec::new();
        let mut visited_hashes: HashSet<u64> = HashSet::new();
        let mut processing_queue: VecDeque<Arc<TaskNode>> = VecDeque::new();

        // 2. Compile Root Tasks & Queue Dependencies
        for task_name in &root_task_names {
            // Compile the entry point
            let node = pipeline.render(&root_alias, task_name)?;

            // Mark as visited so we don't duplicate logic if it calls itself
            if visited_hashes.insert(node.hash) {
                let node_arc = Arc::new(node.clone());

                tasks_to_render.push(TemplateTask {
                    name: format!("{}:{}", root_alias, task_name),
                    body: node.cmd.clone(),
                    source: format!("{}.{}", root_alias, task_name),
                });

                processing_queue.push_back(node_arc);
            }
        }

        // 3. Process Transitive Dependencies
        while let Some(node) = processing_queue.pop_front() {
            for dep_hash in &node.deps {
                if visited_hashes.insert(*dep_hash) {
                    if let Some(dep_node) = pipeline.stores.tasks.get(dep_hash) {
                        tasks_to_render.push(TemplateTask {
                            name: format!("task_{:x}", dep_hash),
                            body: dep_node.cmd.clone(),
                            source: format!("Hash: {:x}", dep_hash),
                        });

                        processing_queue.push_back(dep_node.clone());
                    }
                }
            }
        }

        // 4. Render Template
        let env = Self::setup_env();
        let template = env
            .get_template(SCRIPT_TEMPLATE_NAME)
            .map_err(|e| PipelineError::Internal(e.to_string()))?;

        let context = serde_json::json!({
            "tasks": tasks_to_render,
            "commands": root_task_names,
            "root_alias": root_alias,
        });

        template
            .render(context)
            .map_err(|e| PipelineError::Internal(e.to_string()))
    }
}
