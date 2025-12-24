use ahash::HashSet;
use minijinja::{Environment, Error, ErrorKind, State, Value, value::Object};
use std::sync::{Arc, Mutex};

use crate::pipeline::{
    Pipeline, PipelineStore,
    ast::{Module, Props, UseRef},
    error::PipelineError,
};

#[derive(Default, Debug, Clone, serde::Serialize)]
pub struct TaskNode {
    pub cmd: String,
    pub deps: HashSet<u64>,
    pub hash: u64,
    pub alias: String,
}

fn to_jinja_err(e: impl std::fmt::Display) -> Error {
    Error::new(ErrorKind::InvalidOperation, e.to_string())
}

#[derive(Debug, Clone)]
struct ModuleContext {
    module: Arc<Module>,
    store: Arc<PipelineStore>,
    visited: Arc<Mutex<HashSet<u64>>>,
}

impl ModuleContext {
    fn new(module: Module, store: Arc<PipelineStore>, visited: Arc<Mutex<HashSet<u64>>>) -> Self {
        Self {
            module: Arc::new(module),
            store,
            visited,
        }
    }

    fn from_ref(module: &Module, parent: &ModuleContext) -> Self {
        Self {
            module: Arc::new(module.clone()),
            store: parent.store.clone(),
            visited: parent.visited.clone(),
        }
    }
}

impl Object for ModuleContext {
    fn get_value(self: &Arc<Self>, key: &Value) -> Option<Value> {
        let key_str = key.as_str()?;
        let definition = self.module.uses.as_ref().and_then(|u| match u {
            UseRef::Hash(h) => self.store.metamodules.get(h).map(|m| &m.module),
            _ => None,
        });

        match key_str {
            "props" => Some(Value::from_object(PropsContext {
                ctx: (**self).clone(),
                task_props: None,
                call_props: None,
            })),
            "tasks" => Some(Value::from_object(TaskScopeProxy {
                ctx: (**self).clone(),
            })),
            other => {
                if let Some(sub) = self.module.modules.get(other) {
                    return Some(Value::from_object(ModuleContext::from_ref(sub, self)));
                }
                if let Some(def) = definition {
                    if let Some(sub_def) = def.modules.get(other) {
                        return Some(Value::from_object(ModuleContext::from_ref(sub_def, self)));
                    }
                }
                None
            }
        }
    }
}

#[derive(Debug)]
struct TaskScopeProxy {
    ctx: ModuleContext,
}

impl Object for TaskScopeProxy {
    fn get_value(self: &Arc<Self>, key: &Value) -> Option<Value> {
        let task_name = key.as_str()?.to_string();
        let store = self.ctx.store.clone();

        let task_def = if let Some(t) = self.ctx.module.tasks.get(&task_name) {
            Some(t.clone())
        } else if let Some(UseRef::Hash(h)) = self.ctx.module.uses {
            store
                .metamodules
                .get(&h)
                .and_then(|m| m.module.tasks.get(&task_name))
                .cloned()
        } else {
            None
        }?;

        let ctx = self.ctx.clone();

        Some(Value::from_function(
            move |_: &State, args: &[Value]| -> Result<Value, Error> {
                let call_args = if let Some(first) = args.first() {
                    let v = serde_json::to_value(first).map_err(to_jinja_err)?;
                    serde_json::from_value(v).unwrap_or_default()
                } else {
                    Props::default()
                };

                if let Some(UseRef::Hash(target_hash)) = &task_def.uses {
                    let mut merged_props = task_def.props.clone();
                    merged_props.extend(call_args);

                    let virtual_module = Module {
                        uses: Some(UseRef::Hash(*target_hash)),
                        props: merged_props,
                        ..Default::default()
                    };
                    let virtual_ctx =
                        ModuleContext::new(virtual_module, store.clone(), ctx.visited.clone());
                    let node = compile_task_internal(virtual_ctx, "main".into(), Props::default())
                        .map_err(to_jinja_err)?;
                    return Ok(Value::from(node.cmd.clone()));
                }

                let node = compile_task_internal(ctx.clone(), task_name.clone(), call_args)
                    .map_err(to_jinja_err)?;
                Ok(Value::from(node.cmd.clone()))
            },
        ))
    }
}

#[derive(Debug)]
struct PropsContext {
    ctx: ModuleContext,
    task_props: Option<Props>,
    call_props: Option<Props>,
}

impl Object for PropsContext {
    fn get_value(self: &Arc<Self>, key: &Value) -> Option<Value> {
        let k = key.as_str()?;

        if let Some(v) = self.call_props.as_ref().and_then(|m| m.get(k)) {
            return Some(v.clone());
        }
        if let Some(v) = self.task_props.as_ref().and_then(|m| m.get(k)) {
            return Some(v.clone());
        }
        if let Some(v) = self.ctx.module.props.get(k) {
            return Some(v.clone());
        }
        if let Some(UseRef::Hash(h)) = self.ctx.module.uses {
            if let Some(v) = self
                .ctx
                .store
                .metamodules
                .get(&h)
                .and_then(|m| m.module.props.get(k))
            {
                return Some(v.clone());
            }
        }
        None
    }
}

fn compile_task_internal(
    ctx: ModuleContext,
    task_name: String,
    call_props: Props,
) -> Result<Arc<TaskNode>, PipelineError> {
    // 1. Resolve Definition
    let task_def = if let Some(t) = ctx.module.tasks.get(&task_name) {
        t.clone()
    } else if let Some(UseRef::Hash(h)) = ctx.module.uses {
        ctx.store
            .metamodules
            .get(&h)
            .and_then(|m| m.module.tasks.get(&task_name))
            .cloned()
            .ok_or_else(|| PipelineError::Internal(format!("Task {} not found", task_name)))?
    } else {
        return Err(PipelineError::Internal(format!(
            "Task {} not found",
            task_name
        )));
    };

    if let Some(UseRef::Hash(target_hash)) = &task_def.uses {
        // Merge props: Call Args > Task Props
        let mut merged_props = task_def.props.clone();
        merged_props.extend(call_props);

        // Create Virtual Module to point to the library
        let virtual_module = Module {
            uses: Some(UseRef::Hash(*target_hash)),
            props: merged_props,
            ..Default::default()
        };

        let virtual_ctx =
            ModuleContext::new(virtual_module, ctx.store.clone(), ctx.visited.clone());

        // Recurse: Call "main" (or your preferred default entry) on the target library
        return compile_task_internal(virtual_ctx, "main".to_string(), Props::default());
    }
    // --- FIX END ---

    // 2. Normal Compilation Logic (Props, Hashing, Rendering)
    let mut effective_props = Props::default();
    if let Some(UseRef::Hash(h)) = ctx.module.uses {
        if let Some(m) = ctx.store.metamodules.get(&h) {
            effective_props.extend(m.module.props.clone());
        }
    }
    effective_props.extend(ctx.module.props.clone());
    effective_props.extend(task_def.props.clone());
    effective_props.extend(call_props.clone());

    // ... (rest of the function: hashing, cache check, env creation, rendering) ...
    let mut hasher = ahash::AHasher::default();
    use std::hash::{Hash, Hasher};
    task_def.cmd.hash(&mut hasher);
    serde_json::to_string(&effective_props)
        .unwrap()
        .hash(&mut hasher);
    let cache_key = hasher.finish();

    if let Some(node) = ctx.store.tasks.get(&cache_key) {
        ctx.visited.lock().unwrap().insert(cache_key);
        return Ok(node.clone());
    }

    let mut env = Environment::new();
    env.add_template("main", &task_def.cmd)
        .map_err(|e| PipelineError::Internal(e.to_string()))?;

    let root = Value::from_object(RootContext {
        props: Value::from_object(PropsContext {
            ctx: ctx.clone(),
            task_props: Some(task_def.props.clone()),
            call_props: Some(call_props),
        }),
        tasks: Value::from_object(TaskScopeProxy { ctx: ctx.clone() }),
        module_ctx: ctx.clone(),
    });

    let tmpl = env
        .get_template("main")
        .map_err(|e| PipelineError::Internal(e.to_string()))?;
    let rendered = tmpl
        .render(root)
        .map_err(|e| PipelineError::Internal(e.to_string()))?;

    let node = Arc::new(TaskNode {
        cmd: rendered,
        deps: ctx.visited.lock().unwrap().clone(),
        hash: cache_key,
        alias: task_name,
    });

    Ok(node)
}

#[derive(Debug)]
struct RootContext {
    props: Value,
    tasks: Value,
    module_ctx: ModuleContext,
}

impl Object for RootContext {
    fn get_value(self: &Arc<Self>, key: &Value) -> Option<Value> {
        match key.as_str()? {
            "props" => Some(self.props.clone()),
            "tasks" => Some(self.tasks.clone()),
            other => {
                if let Some(sub) = self.module_ctx.module.modules.get(other) {
                    return Some(Value::from_object(ModuleContext::from_ref(
                        sub,
                        &self.module_ctx,
                    )));
                }
                None
            }
        }
    }
}

impl Pipeline {
    pub fn resolve_task(&mut self, alias: &str, task: &str) -> Result<TaskNode, PipelineError> {
        let store_arc = Arc::new(std::mem::take(&mut self.stores));
        let target_hash = store_arc
            .aliases
            .get(alias)
            .ok_or(PipelineError::Internal(format!(
                "Alias {} not found",
                alias
            )))?;
        let meta = store_arc
            .metamodules
            .get(target_hash)
            .ok_or(PipelineError::Internal("Module missing".into()))?;

        let visited = Arc::new(Mutex::new(HashSet::default()));
        let ctx = ModuleContext::new(meta.module.clone(), store_arc.clone(), visited);

        let node = compile_task_internal(ctx, task.to_string(), Props::default())?;

        self.stores = Arc::try_unwrap(store_arc).unwrap_or_default();
        Ok((*node).clone())
    }
}

#[cfg(test)]
mod tests {
    use crate::pipeline::{
        Config, Pipeline,
        ast::{MetaModule, Module, Props, Task, UseRef},
    };
    use ahash::RandomState;

    // --- Helpers ---

    fn create_pipeline() -> Pipeline {
        Pipeline::new(Config::default())
    }

    fn create_props(pairs: &[(&str, &str)]) -> Props {
        let mut p = Props::with_hasher(RandomState::new());
        for (k, v) in pairs {
            p.insert(k.to_string(), minijinja::Value::from(v.to_string()));
        }
        p
    }

    fn create_module(tasks: &[(&str, &str)], props: &[(&str, &str)]) -> Module {
        let mut m = Module::default();
        for (name, cmd) in tasks {
            m.tasks.insert(
                name.to_string(),
                Task {
                    cmd: cmd.to_string(),
                    ..Default::default()
                },
            );
        }
        m.props = create_props(props);
        m
    }

    fn register_module(p: &mut Pipeline, alias: &str, module: Module, hash: u64) {
        let meta = MetaModule { module, hash };
        p.stores.metamodules.insert(hash, meta); // Insert raw (Store auto-wraps in Arc)
        p.stores.aliases.insert(alias.to_string(), hash);
    }

    // --- Tests ---

    #[test]
    fn test_basic_render_with_props() {
        let mut p = create_pipeline();

        // Define a module with a global prop and a task using it
        let module = create_module(&[("hello", "echo {{ props.msg }}")], &[("msg", "World")]);

        register_module(&mut p, "root", module, 1);

        let result = p.resolve_task("root", "hello").expect("Should compile");
        assert_eq!(result.cmd, "echo World");
    }

    #[test]
    fn test_prop_scope_precedence() {
        let mut p = create_pipeline();

        let mut module = create_module(
            &[
                ("base", "{{ props.val }}"),
                ("override_task", "{{ props.val }}"),
            ],
            &[("val", "MODULE_LEVEL")],
        );

        // Add task-specific override
        if let Some(t) = module.tasks.get_mut("override_task") {
            t.props = create_props(&[("val", "TASK_LEVEL")]);
        }

        register_module(&mut p, "root", module, 10);

        // 1. Module Level
        let res1 = p.resolve_task("root", "base").unwrap();
        assert_eq!(res1.cmd, "MODULE_LEVEL");

        // 2. Task Level
        let res2 = p.resolve_task("root", "override_task").unwrap();
        assert_eq!(res2.cmd, "TASK_LEVEL");
    }

    #[test]
    fn test_task_calling_task() {
        let mut p = create_pipeline();

        let module = create_module(
            &[
                ("greeter", "Hello"),
                ("wrapper", "{{ tasks.greeter() }} World"),
            ],
            &[],
        );

        register_module(&mut p, "root", module, 20);

        let result = p.resolve_task("root", "wrapper").unwrap();
        assert_eq!(result.cmd, "Hello World");
    }

    #[test]
    fn test_submodule_access() {
        let mut p = create_pipeline();

        // 1. Create a "Utils" module
        let utils_mod = create_module(&[("help", "display help")], &[]);
        register_module(&mut p, "ignored_alias", utils_mod.clone(), 31); // Hash 31

        // 2. Create Root module that imports Utils
        let mut root_mod = create_module(&[("main", "Running: {{ utils.tasks.help() }}")], &[]);

        // Add submodule manually to AST
        // We use Inline definition for the AST, but point it to the hash if we wanted 'uses'
        // For this test, let's use the Inline Submodule structure you support:
        root_mod.modules.insert("utils".to_string(), utils_mod);

        register_module(&mut p, "root", root_mod, 30);

        let result = p.resolve_task("root", "main").unwrap();
        assert_eq!(result.cmd, "Running: display help");
    }

    #[test]
    fn test_task_uses_sugar() {
        let mut p = create_pipeline();

        // 1. The Library Module (Target)
        let lib_mod = create_module(
            &[("main", "Library Action: {{ props.mode }}")],
            &[("mode", "default")],
        );
        let lib_hash = 41;
        register_module(&mut p, "lib", lib_mod, lib_hash);

        // 2. The Consumer Module
        let mut consumer_mod = create_module(&[], &[]);

        // Define a task that "uses" the library with specific props
        let task_with_uses = Task {
            uses: Some(UseRef::Hash(lib_hash)),
            props: create_props(&[("mode", "sugar")]),
            cmd: "this should be ignored".to_string(),
        };
        consumer_mod
            .tasks
            .insert("deploy".to_string(), task_with_uses);

        register_module(&mut p, "consumer", consumer_mod, 40);

        let result = p.resolve_task("consumer", "deploy").unwrap();

        // Should resolve to the 'main' task of the library and respect the sugar-provided props
        assert_eq!(result.cmd, "Library Action: sugar");
    }

    #[test]
    fn test_task_calling_task_with_args() {
        let mut p = create_pipeline();

        // Testing: {{ tasks.foo(bar="baz") }}
        let module = create_module(
            &[
                ("echo_prop", "{{ props.dynamic }}"),
                ("caller", "{{ tasks.echo_prop(dynamic='Success') }}"),
            ],
            &[("dynamic", "Fail")], // Default should be overridden
        );

        register_module(&mut p, "root", module, 50);

        let result = p.resolve_task("root", "caller").unwrap();
        assert_eq!(result.cmd, "Success");
    }
}
