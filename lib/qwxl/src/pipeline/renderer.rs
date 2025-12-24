use ahash::HashSet;
use minijinja::{Environment, Error, ErrorKind, State, Value, value::Object};
use std::fmt;
use std::sync::{Arc, Mutex};

use crate::pipeline::{
    Pipeline, PipelineStore,
    ast::{IHashMap, Module, Props, Task, UseRef},
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

/// Context passed down through the recursive compilation.
#[derive(Debug, Clone)]
struct ModuleContext {
    module: Arc<Module>,
    store: Arc<PipelineStore>,
    visited: Arc<Mutex<HashSet<u64>>>,
    /// Cache for the current compilation session to prevent infinite recursion
    /// and to collect all transitive dependencies for the emitter.
    session_tasks: Arc<Mutex<IHashMap<u64, TaskNode>>>,
}

impl ModuleContext {
    fn new(
        module: Module,
        store: Arc<PipelineStore>,
        visited: Arc<Mutex<HashSet<u64>>>,
        session_tasks: Arc<Mutex<IHashMap<u64, TaskNode>>>,
    ) -> Self {
        Self {
            module: Arc::new(module),
            store,
            visited,
            session_tasks,
        }
    }

    fn from_ref(module: &Module, parent: &ModuleContext) -> Self {
        Self {
            module: Arc::new(module.clone()),
            store: parent.store.clone(),
            visited: parent.visited.clone(),
            session_tasks: parent.session_tasks.clone(),
        }
    }
}

// Recursively find task definition
fn find_task_recursive(ctx: &ModuleContext, task_name: &str) -> Option<Task> {
    if let Some(t) = ctx.module.tasks.get(task_name) {
        return Some(t.clone());
    }
    let mut current_uses = ctx.module.uses.as_ref();
    let mut depth = 0;
    while let Some(UseRef::Hash(h)) = current_uses {
        if depth > 100 {
            return None;
        }
        let meta = ctx.store.metamodules.get(h)?;
        if let Some(t) = meta.module.tasks.get(task_name) {
            return Some(t.clone());
        }
        current_uses = meta.module.uses.as_ref();
        depth += 1;
    }
    None
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
                // If this module defines a task with that name, return a TaskRef so
                // `module.foo` (or `utils.color`) works as a direct task reference.
                if let Some(task_def) = self.module.tasks.get(other) {
                    return Some(Value::from_object(TaskRef {
                        ctx: (**self).clone(),
                        task_name: other.to_string(),
                        task_def: task_def.clone(),
                    }));
                }

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

        // Ensure task exists
        let task_def = find_task_recursive(&self.ctx, &task_name)?;

        // Return a TaskRef object which can be Called (inline) or Rendered (reference)
        Some(Value::from_object(TaskRef {
            ctx: self.ctx.clone(),
            task_name,
            task_def,
        }))
    }
}

/// The star of the show: Handles both `{{ tasks.foo }}` and `{{ tasks.foo() }}`
#[derive(Debug)]
struct TaskRef {
    ctx: ModuleContext,
    task_name: String,
    task_def: Task,
}

impl TaskRef {
    /// Internal helper to compile the task to a node
    fn compile(&self, call_props: Props) -> Result<Arc<TaskNode>, Error> {
        // Handle "uses" Sugar
        if let Some(UseRef::Hash(target_hash)) = &self.task_def.uses {
            let mut merged_props = self.task_def.props.clone();
            merged_props.extend(call_props);

            let virtual_module = Module {
                uses: Some(UseRef::Hash(*target_hash)),
                props: merged_props,
                ..Default::default()
            };
            let virtual_ctx = ModuleContext::new(
                virtual_module,
                self.ctx.store.clone(),
                self.ctx.visited.clone(),
                self.ctx.session_tasks.clone(),
            );

            let node = compile_task_internal(virtual_ctx, "main".into(), Props::default())
                .map_err(to_jinja_err)?;

            self.ctx.visited.lock().unwrap().insert(node.hash);
            return Ok(node);
        }

        // Normal compilation
        let node = compile_task_internal(self.ctx.clone(), self.task_name.clone(), call_props)
            .map_err(to_jinja_err)?;

        // Track the dependency
        self.ctx.visited.lock().unwrap().insert(node.hash);
        Ok(node)
    }
}

impl Object for TaskRef {
    /// Handle `{{ tasks.foo() }}` -> Inlines the body
    fn call(self: &Arc<Self>, _state: &State, args: &[Value]) -> Result<Value, Error> {
        let call_args = if let Some(first) = args.first() {
            let v = serde_json::to_value(first).map_err(to_jinja_err)?;
            serde_json::from_value(v).unwrap_or_default()
        } else {
            Props::default()
        };

        let node = self.compile(call_args)?;
        Ok(Value::from(node.cmd.clone()))
    }

    /// Handle `{{ tasks.foo }}` -> Outputs the function name (Reference)
    /// This is the "Repr" vs "Call" distinction you wanted.
    fn render(self: &Arc<Self>, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        // When rendered as a string, we assume "Reference Mode" (default props)
        // We compile it to ensure it exists and has a hash
        match self.compile(Props::default()) {
            Ok(node) => {
                // Output the stable function name
                write!(f, "task_{:x}", node.hash)
            }
            Err(_) => Err(fmt::Error), // fmt::Result doesn't allow custom errors nicely
        }
    }

    // Allow property access just in case user really wants .name or .alias
    fn get_value(self: &Arc<Self>, key: &Value) -> Option<Value> {
        match key.as_str()? {
            "name" | "ref" => {
                let node = self.compile(Props::default()).ok()?;
                Some(Value::from(format!("task_{:x}", node.hash)))
            }
            "alias" => Some(Value::from(self.task_name.clone())),
            _ => None,
        }
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
    let task_def = find_task_recursive(&ctx, &task_name)
        .ok_or_else(|| PipelineError::Internal(format!("Task {} not found", task_name)))?;

    // Handle "uses" Sugar (for entry points)
    if let Some(UseRef::Hash(target_hash)) = &task_def.uses {
        let mut merged_props = task_def.props.clone();
        merged_props.extend(call_props);
        let virtual_module = Module {
            uses: Some(UseRef::Hash(*target_hash)),
            props: merged_props,
            ..Default::default()
        };
        let virtual_ctx = ModuleContext::new(
            virtual_module,
            ctx.store.clone(),
            ctx.visited.clone(),
            ctx.session_tasks.clone(),
        );
        return compile_task_internal(virtual_ctx, "main".to_string(), Props::default());
    }

    // 2. Normal Compilation
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
    serde_json::to_string(&effective_props)
        .unwrap()
        .hash(&mut hasher);
    let cache_key = hasher.finish();

    // 4. Cache Check (Global + Session)
    // Global Store Check
    if let Some(node) = ctx.store.tasks.get(&cache_key) {
        ctx.visited.lock().unwrap().insert(cache_key);
        return Ok(node.clone());
    }
    // Session Store Check (Recursion within this render pass)
    {
        let session = ctx.session_tasks.lock().unwrap();
        if let Some(node) = session.get(&cache_key) {
            ctx.visited.lock().unwrap().insert(cache_key);
            return Ok(Arc::new(node.clone()));
        }
    }

    // 5. Render
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

    // 6. Save to Session Store
    ctx.session_tasks
        .lock()
        .unwrap()
        .insert(cache_key, (*node).clone());

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
        let session_tasks = Arc::new(Mutex::new(IHashMap::default()));

        let ctx = ModuleContext::new(
            meta.module.clone(),
            store_arc.clone(),
            visited,
            session_tasks.clone(),
        );

        let node = compile_task_internal(ctx, task.to_string(), Props::default())?;

        self.stores = Arc::try_unwrap(store_arc).unwrap_or_default();

        // Merge session tasks back into global store so Emitter can find them.
        // Preserve the first alias (readable name) that referred to each task hash by
        // keeping a map from task_<hash> to alias (the alias is stored as the TaskNode.alias).
        let session = session_tasks.lock().unwrap();
        for (k, v) in session.iter() {
            // If the global store already has this task, skip overwriting to preserve
            // the original alias / canonical TaskNode that was stored earlier.
            if self.stores.tasks.get(k).is_some() {
                continue;
            }
            self.stores.tasks.insert(*k, v.clone());
        }

        Ok((*node).clone())
    }
}

#[cfg(test)]
mod tests {
    use crate::pipeline::{
        Config, Pipeline,
        ast::{MetaModule, Module, Props, Task},
    };
    use ahash::RandomState;

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
    fn register_module(p: &mut Pipeline, alias: &str, module: Module, hash: u64) {
        let meta = MetaModule { module, hash };
        p.stores.metamodules.insert(hash, meta);
        p.stores.aliases.insert(alias.to_string(), hash);
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

    #[test]
    fn test_task_ref_deduplication() {
        let mut p = create_pipeline();

        // 1. Utils Module (Common Base)
        let utils_mod = create_module(&[("color", "echo 'color'")], &[]);
        let utils_hash = 10;
        register_module(&mut p, "utils", utils_mod.clone(), utils_hash);

        // 2. Log Module (Imports Utils)
        // Uses {{ utils.tasks.color }} which should render to 'task_<hash>'
        let mut log_mod = create_module(&[("debug", "call {{ utils.tasks.color }}")], &[]);
        log_mod
            .modules
            .insert("utils".to_string(), utils_mod.clone());
        register_module(&mut p, "log", log_mod, 20);

        // 3. Root Module (Imports Log AND Utils)
        // Root calls log.debug (which refs utils.color)
        // Root also calls utils.color directly
        // We want to verify utils.color is deduplicated.
        let mut root_mod = create_module(
            &[(
                "main",
                "root calls {{ utils.tasks.color }} and {{ log.tasks.debug() }}",
            )],
            &[],
        );
        root_mod.modules.insert("utils".to_string(), utils_mod);
        root_mod
            .modules
            .insert("log".to_string(), create_module(&[], &[])); // Placeholder, resolving via 'uses' usually
        // Manually link log module in AST isn't full 'uses' simulation but works for this test logic
        // We need to register log as a submodule correctly or use global alias lookup.
        // For this test, let's just test that rendering 'log' from root context works if we construct context manually
        // But pipeline.render takes alias.

        // Let's just render log:debug and see the output.
        let color_node = p.render("utils", "color").unwrap();
        let color_ref_str = format!("task_{:x}", color_node.hash);

        let debug_node = p.render("log", "debug").unwrap();

        // "call task_abc..."
        assert!(debug_node.cmd.contains(&color_ref_str));

        // Check dependency tracking
        assert!(debug_node.deps.contains(&color_node.hash));
    }
}
