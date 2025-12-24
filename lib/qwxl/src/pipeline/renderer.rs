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
                    // Optimization TODO: Use minijinja Value directly to avoid JSON roundtrip
                    let v = serde_json::to_value(first).map_err(to_jinja_err)?;
                    serde_json::from_value(v).unwrap_or_default()
                } else {
                    Props::default()
                };

                // Syntactic Sugar for 'uses'
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

    // Handle "uses" Sugar for Entry Points
    if let Some(UseRef::Hash(target_hash)) = &task_def.uses {
        let mut merged_props = task_def.props.clone();
        merged_props.extend(call_props);

        let virtual_module = Module {
            uses: Some(UseRef::Hash(*target_hash)),
            props: merged_props,
            ..Default::default()
        };

        let virtual_ctx =
            ModuleContext::new(virtual_module, ctx.store.clone(), ctx.visited.clone());
        return compile_task_internal(virtual_ctx, "main".to_string(), Props::default());
    }

    // 2. Normal Compilation
    // Optimization TODO: Use ChainMap or Copy-on-Write to avoid cloning maps
    let mut effective_props = Props::default();
    if let Some(UseRef::Hash(h)) = ctx.module.uses {
        if let Some(m) = ctx.store.metamodules.get(&h) {
            effective_props.extend(m.module.props.clone());
        }
    }
    effective_props.extend(ctx.module.props.clone());
    effective_props.extend(task_def.props.clone());
    effective_props.extend(call_props.clone());

    // 3. Hashing
    let mut hasher = ahash::AHasher::default();
    use std::hash::{Hash, Hasher};
    task_def.cmd.hash(&mut hasher);
    // Optimization: JSON serialization for hashing is slow but robust for Value types
    serde_json::to_string(&effective_props)
        .unwrap()
        .hash(&mut hasher);
    let cache_key = hasher.finish();

    if let Some(node) = ctx.store.tasks.get(&cache_key) {
        ctx.visited.lock().unwrap().insert(cache_key);
        return Ok(node.clone());
    }

    // 4. Render
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
    pub fn render(&mut self, alias: &str, task: &str) -> Result<TaskNode, PipelineError> {
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

    fn create_pipeline() -> Pipeline {
        Pipeline::new(Config::default())
    }

    fn create_props(pairs: &[(&str, &str)]) -> Props {
        let mut p = Props::with_hasher(RandomState::with_seed(0));
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
        // Note: Store::insert wraps in Arc automatically
        p.stores.metamodules.insert(hash, meta);
        p.stores.aliases.insert(alias.to_string(), hash);
    }

    // --- Tests ---

    #[test]
    fn test_basic_render_with_props() {
        let mut p = create_pipeline();

        let module = create_module(&[("hello", "echo {{ props.msg }}")], &[("msg", "World")]);

        register_module(&mut p, "root", module, 1);

        let result = p.render("root", "hello").expect("Should compile");
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

        if let Some(t) = module.tasks.get_mut("override_task") {
            t.props = create_props(&[("val", "TASK_LEVEL")]);
        }

        register_module(&mut p, "root", module, 10);

        // 1. Module Level
        let res1 = p.render("root", "base").unwrap();
        assert_eq!(res1.cmd, "MODULE_LEVEL");

        // 2. Task Level
        let res2 = p.render("root", "override_task").unwrap();
        assert_eq!(res2.cmd, "TASK_LEVEL");

        // 3. Call Level (Inline override)
        // This requires a task that calls another with args
        let module_call = create_module(
            &[
                ("identity", "{{ props.val }}"),
                ("caller", "{{ tasks.identity(val='CALL_LEVEL') }}"),
            ],
            &[("val", "MODULE_LEVEL")],
        );
        register_module(&mut p, "root_call", module_call, 11);
        let res3 = p.render("root_call", "caller").unwrap();
        assert_eq!(res3.cmd, "CALL_LEVEL");
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

        let result = p.render("root", "wrapper").unwrap();
        assert_eq!(result.cmd, "Hello World");
    }

    #[test]
    fn test_submodule_access_and_props() {
        let mut p = create_pipeline();

        // 1. Create a "Utils" module with its own props
        let utils_mod = create_module(
            &[("log", "LOG: {{ props.prefix }} {{ props.msg }}")],
            &[("prefix", "DEFAULT")],
        );
        let utils_hash = 31;
        register_module(&mut p, "ignored", utils_mod.clone(), utils_hash);

        // 2. Create Root module that overrides Utils props on import
        let mut root_mod = create_module(&[("main", "{{ utils.tasks.log(msg='Injected') }}")], &[]);

        // Simulate submodule import with property overrides
        let mut utils_instance = utils_mod;
        utils_instance.props = create_props(&[("prefix", "OVERRIDDEN")]);
        root_mod.modules.insert("utils".to_string(), utils_instance);

        register_module(&mut p, "root", root_mod, 30);

        let result = p.render("root", "main").unwrap();
        // Should resolve: prefix (from import override) + msg (from task call)
        assert_eq!(result.cmd, "LOG: OVERRIDDEN Injected");
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

        let result = p.render("consumer", "deploy").unwrap();

        // Should resolve to the 'main' task of the library and respect the sugar-provided props
        assert_eq!(result.cmd, "Library Action: sugar");
    }

    #[test]
    fn test_deep_inheritance_props() {
        let mut p = create_pipeline();

        // Level 3: Base Template
        let base_mod = create_module(&[("run", "Value: {{ props.val }}")], &[("val", "base")]);
        let base_hash = 100;
        register_module(&mut p, "base", base_mod.clone(), base_hash);

        // Level 2: Middleware (inherits base, overrides val)
        let mut middle_mod = create_module(&[], &[("val", "middle")]);
        middle_mod.uses = Some(UseRef::Hash(base_hash));
        let middle_hash = 101;
        register_module(&mut p, "middle", middle_mod.clone(), middle_hash);

        // Level 1: App (inherits middleware, overrides val)
        let mut app_mod = create_module(&[], &[("val", "app")]);
        app_mod.uses = Some(UseRef::Hash(middle_hash));
        let app_hash = 102;
        register_module(&mut p, "app", app_mod, app_hash);

        // Resolve "run" (inherited all the way from base) starting at app
        let result = p.render("app", "run").unwrap();
        assert_eq!(result.cmd, "Value: app");
    }

    #[test]
    fn test_cross_module_dependency_tracking() {
        let mut p = create_pipeline();

        // Module B
        let mod_b = create_module(&[("task_b", "Output B")], &[]);
        let hash_b = 201;
        register_module(&mut p, "b", mod_b.clone(), hash_b);

        // Module A (calls B)
        let mut mod_a = create_module(&[("task_a", "{{ b.tasks.task_b() }}")], &[]);
        mod_a.modules.insert("b".to_string(), mod_b);
        let hash_a = 200;
        register_module(&mut p, "a", mod_a, hash_a);

        let result = p.render("a", "task_a").unwrap();
        assert_eq!(result.cmd, "Output B");

        // Verify that the hash of task_b is in the dependencies of task_a
        // (Assuming your hashing logic is deterministic for these tests)
        assert!(!result.deps.is_empty(), "Dependencies should be tracked");
    }
}
