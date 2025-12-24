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

#[cfg(test)]
mod tests {
    use super::*;
    use crate::pipeline::{
        Config,
        ast::{MetaModule, Module, Task},
    };

    fn create_pipeline() -> Pipeline {
        Pipeline::new(Config::default())
    }

    fn register_module(p: &mut Pipeline, alias: &str, module: Module, hash: u64) {
        let meta = MetaModule { module, hash };
        p.stores.metamodules.insert(hash, meta);
        p.stores.aliases.insert(alias.to_string(), hash);
    }

    #[test]
    fn test_generate_simple_script() {
        let mut p = create_pipeline();
        let mut module = Module::default();
        module.tasks.insert(
            "build".to_string(),
            Task {
                cmd: "cargo build".to_string(),
                ..Default::default()
            },
        );
        register_module(&mut p, "root", module, 1);

        let generator = ShellGenerator::new();
        let script = generator.generate(&mut p).expect("Generate failed");

        assert!(script.contains("root:build() {"));
        assert!(script.contains("cargo build"));
        assert!(script.contains("FN=\"root:$CMD\""));
    }

    #[test]
    fn test_generate_with_deps() {
        let mut p = create_pipeline();

        // Lib module
        let mut lib = Module::default();
        lib.tasks.insert(
            "helper".to_string(),
            Task {
                cmd: "echo help".to_string(),
                ..Default::default()
            },
        );
        register_module(&mut p, "lib", lib.clone(), 10);

        // Root module uses lib
        let mut root = Module::default();
        root.modules.insert("lib".to_string(), lib);
        root.tasks.insert(
            "main".to_string(),
            Task {
                cmd: "{{ lib.tasks.helper() }}".to_string(),
                ..Default::default()
            },
        );
        register_module(&mut p, "root", root, 20);

        let generator = ShellGenerator::new();
        let script = generator.generate(&mut p).expect("Generate failed");

        assert!(script.contains("root:main() {"));
        // Dependency should be rendered as hash task
        assert!(script.contains("task_"));
        assert!(script.contains("echo help"));
    }
}
