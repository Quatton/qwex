use crate::pipeline::{ast::Task, cache::Store};

struct EnvironmentContext {
    module_context: Store<String, String>,
}

pub fn normalize_task(task: Task) -> Task {
    match task {
        Task::Uses { props, uses } => Task::Cmd {
            props: crate::pipeline::context::Props::default(),
            cmd: format!(
                "{{{{ {}({}) }}}}",
                uses,
                if props.is_empty() {
                    "{}".to_string()
                } else {
                    serde_json::to_string(&props).unwrap_or_else(|_| "{}".to_string())
                }
            ),
        },
        _ => task,
    }
}

use crate::pipeline::error::PipelineError;
use minijinja::Value;
use minijinja::context;

// pub fn resolve_task(
//     pipeline: &mut crate::pipeline::Pipeline,
//     alias: &str,
//     task_name: &str,
// ) -> Result<crate::pipeline::renderer::TaskNode, PipelineError> {
//     // First try alias -> module_hash direct mapping (handles props-overrides)
//     if let Some(module_hash) = pipeline.stores.alias_to_module_hash.get(&alias.to_string()) {
//         let arc = pipeline
//             .stores
//             .module_instances
//             .get(&module_hash.as_ref().clone())
//             .ok_or(PipelineError::ModuleNotFound(alias.to_string()))?;

//         let module = &*arc.0;
//         let instance_props = &*arc.1;
//         // proceed below using module/instance_props

//         // Collect props: module props + instance overrides + task props
//         let mut props = module.props.clone();
//         for (k, v) in instance_props.iter() {
//             props.insert(k.clone(), v.clone());
//         }
//         if let Some(task) = module.tasks.get(task_name) {
//             match task {
//                 crate::pipeline::ast::Task::Cmd {
//                     props: task_props, ..
//                 } => {
//                     for (k, v) in task_props.iter() {
//                         props.insert(k.clone(), v.clone());
//                     }
//                 }
//                 crate::pipeline::ast::Task::Uses {
//                     props: task_props, ..
//                 } => {
//                     for (k, v) in task_props.iter() {
//                         props.insert(k.clone(), v.clone());
//                     }
//                 }
//             }
//         }

//         println!(
//             "[resolver] merged props for {}: {:?}",
//             alias,
//             props.keys().collect::<Vec<_>>()
//         );

//         let task_context = crate::pipeline::context::TaskContext::new(props);

//         let task = module
//             .tasks
//             .get(task_name)
//             .ok_or(PipelineError::TaskNotFound(task_name.to_string()))?;

//         match task {
//             crate::pipeline::ast::Task::Cmd { cmd, .. } => {
//                 let mut env = minijinja::Environment::new();
//                 env.add_global("props", Value::from_object(task_context));

//                 // Expose submodule task function names to templates, e.g. `utils.once` -> "utils.once"
//                 for (sub_name, sub_module) in module.modules.iter() {
//                     let fq_alias = if alias.is_empty() {
//                         sub_name.clone()
//                     } else {
//                         format!("{}.{}", alias, sub_name)
//                     };
//                     let mut sub_map: std::collections::BTreeMap<String, Value> =
//                         std::collections::BTreeMap::new();
//                     for (tname, _t) in sub_module.tasks.iter() {
//                         sub_map.insert(
//                             tname.clone(),
//                             Value::from(format!("{}.{}", fq_alias, tname)),
//                         );
//                     }
//                     env.add_global(sub_name.as_str(), Value::from_object(sub_map));
//                 }

//                 // Generic scanner: replace tokens like `{{ mod.task }}` with fully-qualified
//                 // names `alias.mod.task` when `mod` is a declared submodule.
//                 let mut out = String::with_capacity(cmd.len());
//                 let mut i = 0usize;
//                 while let Some(start) = cmd[i..].find("{{") {
//                     let start_idx = i + start;
//                     out.push_str(&cmd[i..start_idx]);
//                     if let Some(rel_end) = cmd[start_idx..].find("}}") {
//                         let end_idx = start_idx + rel_end + 2;
//                         let token = &cmd[start_idx + 2..start_idx + rel_end];
//                         let token_trim = token.trim();
//                         if let Some(dot_pos) = token_trim.find('.') {
//                             let (mod_name, task_name) = token_trim.split_at(dot_pos);
//                             let task_name = &task_name[1..];
//                             if module.modules.contains_key(mod_name) {
//                                 let fq_alias = if alias.is_empty() {
//                                     mod_name.to_string()
//                                 } else {
//                                     format!("{}.{}", alias, mod_name)
//                                 };
//                                 out.push_str(&format!("{}.{}", fq_alias, task_name));
//                                 i = end_idx;
//                                 continue;
//                             }
//                         }
//                         out.push_str(&cmd[start_idx..end_idx]);
//                         i = end_idx;
//                     } else {
//                         out.push_str(&cmd[start_idx..]);
//                         i = cmd.len();
//                         break;
//                     }
//                 }
//                 if i < cmd.len() {
//                     out.push_str(&cmd[i..]);
//                 }
//                 tracing::trace!("[resolver] cmd after sub replacements:\n{}", out);
//                 let rendered = env.render_str(&out, context! {})?;
//                 tracing::trace!(
//                     "[resolver] rendered {}.{} => {}",
//                     alias,
//                     task_name,
//                     rendered
//                 );
//                 return Ok(crate::pipeline::renderer::TaskNode {
//                     name: format!("{}.{}", alias, task_name),
//                     body: rendered,
//                     dependencies: vec![],
//                 });
//             }
//             crate::pipeline::ast::Task::Uses { uses, .. } => {
//                 return Ok(crate::pipeline::renderer::TaskNode {
//                     name: format!("{}.{}", alias, task_name),
//                     body: String::new(),
//                     dependencies: vec![uses.clone()],
//                 });
//             }
//         }
//     }

//     // Fallback: symbol -> (path, props_key) -> key_to_module_hash
//     // Get the module for the alias
//     let sym = pipeline
//         .stores
//         .symbols
//         .get(&alias.to_string())
//         .ok_or(PipelineError::ModuleNotFound(alias.to_string()))?;
//     let sym_key = sym.as_ref().clone();

//     // Find module hash for this (path, props_key)
//     let module_hash_opt = pipeline
//         .stores
//         .key_to_module_hash
//         .get(&sym_key)
//         .or_else(|| {
//             pipeline
//                 .stores
//                 .key_to_module_hash
//                 .get(&(sym_key.0.clone(), None))
//         });

//     let module_hash = module_hash_opt.ok_or(PipelineError::ModuleNotFound(alias.to_string()))?;

//     let arc = pipeline
//         .stores
//         .module_instances
//         .get(&module_hash.as_ref().clone())
//         .ok_or(PipelineError::ModuleNotFound(alias.to_string()))?;
//     let module = &*arc.0;
//     let instance_props = &*arc.1;

//     // Collect props: module props + instance overrides + task props
//     let mut props = module.props.clone();
//     for (k, v) in instance_props.iter() {
//         props.insert(k.clone(), v.clone());
//     }
//     if let Some(task) = module.tasks.get(task_name) {
//         match task {
//             crate::pipeline::ast::Task::Cmd {
//                 props: task_props, ..
//             } => {
//                 for (k, v) in task_props.iter() {
//                     props.insert(k.clone(), v.clone());
//                 }
//             }
//             crate::pipeline::ast::Task::Uses {
//                 props: task_props, ..
//             } => {
//                 for (k, v) in task_props.iter() {
//                     props.insert(k.clone(), v.clone());
//                 }
//             }
//         }
//     }

//     println!(
//         "[resolver] merged props for {}: {:?}",
//         alias,
//         props.keys().collect::<Vec<_>>()
//     );

//     let task_context = crate::pipeline::context::TaskContext::new(props);

//     let task = module
//         .tasks
//         .get(task_name)
//         .ok_or(PipelineError::TaskNotFound(task_name.to_string()))?;

//     match task {
//         crate::pipeline::ast::Task::Cmd { cmd, .. } => {
//             let mut env = minijinja::Environment::new();
//             env.add_global("props", Value::from_object(task_context));

//             for (sub_name, sub_module) in module.modules.iter() {
//                 let fq_alias = if alias.is_empty() {
//                     sub_name.clone()
//                 } else {
//                     format!("{}.{}", alias, sub_name)
//                 };
//                 let mut sub_map: std::collections::BTreeMap<String, Value> =
//                     std::collections::BTreeMap::new();
//                 for (tname, _t) in sub_module.tasks.iter() {
//                     sub_map.insert(
//                         tname.clone(),
//                         Value::from(format!("{}.{}", fq_alias, tname)),
//                     );
//                 }
//                 env.add_global(sub_name.as_str(), Value::from_object(sub_map));
//             }

//             let mut out = String::with_capacity(cmd.len());
//             let mut i = 0usize;
//             while let Some(start) = cmd[i..].find("{{") {
//                 let start_idx = i + start;
//                 out.push_str(&cmd[i..start_idx]);
//                 if let Some(rel_end) = cmd[start_idx..].find("}}") {
//                     let end_idx = start_idx + rel_end + 2;
//                     let token = &cmd[start_idx + 2..start_idx + rel_end];
//                     let token_trim = token.trim();
//                     if let Some(dot_pos) = token_trim.find('.') {
//                         let (mod_name, task_name) = token_trim.split_at(dot_pos);
//                         let task_name = &task_name[1..];
//                         if module.modules.contains_key(mod_name) {
//                             let fq_alias = if alias.is_empty() {
//                                 mod_name.to_string()
//                             } else {
//                                 format!("{}.{}", alias, mod_name)
//                             };
//                             out.push_str(&format!("{}.{}", fq_alias, task_name));
//                             i = end_idx;
//                             continue;
//                         }
//                     }
//                     out.push_str(&cmd[start_idx..end_idx]);
//                     i = end_idx;
//                 } else {
//                     out.push_str(&cmd[start_idx..]);
//                     i = cmd.len();
//                     break;
//                 }
//             }
//             if i < cmd.len() {
//                 out.push_str(&cmd[i..]);
//             }
//             tracing::trace!("[resolver] cmd after sub replacements:\n{}", out);
//             let rendered = env.render_str(&out, context! {})?;
//             tracing::trace!(
//                 "[resolver] rendered {}.{} => {}",
//                 alias,
//                 task_name,
//                 rendered
//             );
//             Ok(crate::pipeline::renderer::TaskNode {
//                 name: format!("{}.{}", alias, task_name),
//                 body: rendered,
//                 dependencies: vec![],
//             })
//         }
//         crate::pipeline::ast::Task::Uses { uses, .. } => Ok(crate::pipeline::renderer::TaskNode {
//             name: format!("{}.{}", alias, task_name),
//             body: String::new(),
//             dependencies: vec![uses.clone()],
//         }),
//     }
// }

// pub fn resolve_all_tasks(
//     pipeline: &mut crate::pipeline::Pipeline,
//     root_alias: &str,
// ) -> Result<Vec<crate::pipeline::renderer::TaskNode>, PipelineError> {
//     pipeline.task_queue.clear();
//     pipeline.visited.clear();
//     let mut results = Vec::new();

//     // Get the root module
//     let sym = pipeline
//         .stores
//         .symbols
//         .get(&root_alias.to_string())
//         .ok_or(PipelineError::ModuleNotFound(root_alias.to_string()))?;
//     let sym_key = sym.as_ref().clone();
//     let module_hash_opt = pipeline
//         .stores
//         .key_to_module_hash
//         .get(&sym_key)
//         .or_else(|| {
//             pipeline
//                 .stores
//                 .key_to_module_hash
//                 .get(&(sym_key.0.clone(), None))
//         });
//     let module_hash =
//         module_hash_opt.ok_or(PipelineError::ModuleNotFound(root_alias.to_string()))?;
//     let arc = pipeline
//         .stores
//         .module_instances
//         .get(&module_hash.as_ref().clone())
//         .ok_or(PipelineError::ModuleNotFound(root_alias.to_string()))?;
//     let module = &*arc.0;

//     // Add all tasks in root module to queue
//     for task_name in module.tasks.keys() {
//         let task_key = if root_alias.is_empty() {
//             task_name.clone()
//         } else {
//             format!("{}.{}", root_alias, task_name)
//         };
//         pipeline.task_queue.push_back(task_key);
//     }

//     // Process queue with BFS
//     while let Some(task_key) = pipeline.task_queue.pop_front() {
//         if pipeline.visited.contains(&task_key) {
//             continue;
//         }

//         let (alias, task_name) = if task_key.contains('.') {
//             let parts: Vec<&str> = task_key.split('.').collect();
//             if parts.len() != 2 {
//                 return Err(PipelineError::InvalidAliasFormat(task_key));
//             }
//             (parts[0].to_string(), parts[1].to_string())
//         } else {
//             ("".to_string(), task_key.clone())
//         };

//         let node = resolve_task(pipeline, &alias, &task_name)?;

//         // Add dependencies to queue if not visited
//         for dep in &node.dependencies {
//             if !pipeline.visited.contains(dep) && !pipeline.task_queue.contains(dep) {
//                 pipeline.task_queue.push_back(dep.clone());
//             }
//         }

//         pipeline.visited.insert(task_key);
//         results.push(node);
//     }

//     Ok(results)
// }

// // impl Pipeline {
// //     pub fn resolve_task(&mut self, task: Task) -> Result<TaskNode, PipelineError> {}
// // }

#[cfg(test)]
mod tests {
    use crate::pipeline::{ast::Task, resolver::normalize_task};

    #[test]
    fn test_normalize_task() {
        let task = Task::Uses {
            uses: "moduleA.tasks.task".to_string(),
            props: crate::pipeline::context::Props::default(),
        };

        let normalized = normalize_task(task);

        match normalized {
            Task::Cmd { cmd, .. } => {
                assert_eq!(cmd, "{{ moduleA.tasks.task({}) }}");
            }
            _ => panic!("Expected Cmd task"),
        }
    }
}
