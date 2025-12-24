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

pub struct ShellGenerator<'a> {
    pipeline: &'a mut Pipeline,
}

impl<'a> ShellGenerator<'a> {
    pub fn new(pipeline: &'a mut Pipeline) -> Self {
        Self { pipeline }
    }

    /// Registers the template and any custom filters needed for shell generation.
    fn setup_env() -> Environment<'static> {
        let mut env = Environment::new();

        env.add_template(SCRIPT_TEMPLATE_NAME, SCRIPT_TEMPLATE_SOURCE)
            .expect("Failed to load embedded script template");

        // Register 'indent' filter: pads all lines except the first (handled by template usually)
        // But for shell functions, we typically want to indent the whole block if it's inside {}
        env.add_filter("indent", |s: String, width: usize| -> String {
            let pad = " ".repeat(width);
            s.lines()
                .enumerate()
                .map(|(i, line)| {
                    if i == 0 {
                        // First line is often handled by the caller's indentation,
                        // but minijinja's indent filter usually indents all.
                        // Let's indent everything for consistency within the function body block.
                        format!("{}{}", pad, line)
                    } else {
                        format!("{}{}", pad, line)
                    }
                })
                .collect::<Vec<_>>()
                .join("\n")
        });

        env
    }

    pub fn generate(&mut self) -> Result<String, PipelineError> {
        let root_alias = self.pipeline.config.root_alias.clone();

        // 1. Identify Root Tasks (Entry Points)
        // We need to look up the root module to see what tasks are available to be exposed.
        // We must clone the necessary data to avoid borrowing conflicts with self.pipeline.
        let root_hash = self
            .pipeline
            .stores
            .aliases
            .get(&root_alias)
            .ok_or_else(|| PipelineError::Internal("Root alias not found".to_string()))?;

        let root_task_names: Vec<String> = {
            let meta = self
                .pipeline
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
            let node = self.pipeline.render(&root_alias, task_name)?;

            // Mark as visited so we don't duplicate logic if it calls itself (recursion?)
            if visited_hashes.insert(node.hash) {
                let node_arc = Arc::new(node.clone()); // resolve_task returns TaskNode, wrap it

                // Add to output list with a specific "Namespaced" name
                tasks_to_render.push(TemplateTask {
                    name: format!("{}:{}", root_alias, task_name),
                    body: node.cmd.clone(),
                    source: format!("{}.{}", root_alias, task_name),
                });

                // Queue dependencies for processing
                // (Even if inlined, we might want to generate them for correctness or future refactors)
                processing_queue.push_back(node_arc);
            }
        }

        // 3. Process Transitive Dependencies
        // We need to fetch the TaskNode for every hash in `node.deps`
        while let Some(node) = processing_queue.pop_front() {
            for dep_hash in &node.deps {
                if visited_hashes.insert(*dep_hash) {
                    // We need to retrieve the TaskNode from the store
                    if let Some(dep_node) = self.pipeline.stores.tasks.get(dep_hash) {
                        // Add to output list with a "Hashed" name (internal library)
                        tasks_to_render.push(TemplateTask {
                            name: format!("task_{:x}", dep_hash), // e.g. task_a1b2c3...
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
            "commands": root_task_names, // For help message
            "root_alias": root_alias,
        });

        let script = template
            .render(context)
            .map_err(|e| PipelineError::Internal(e.to_string()))?;

        Ok(script)
    }
}
