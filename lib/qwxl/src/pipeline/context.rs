use std::sync::Arc;

use ahash::{HashMap, HashMapExt as _};
use minijinja::value::Object;
use serde::Serialize;

pub type Props = HashMap<String, minijinja::Value>;

#[derive(Debug, Clone, Default)]
pub struct LazyProps {
    pub module: Arc<Props>,
    pub task: Arc<Props>,
    pub module_overrides: Arc<Props>,
    pub task_overrides: Arc<Props>,
}

impl LazyProps {
    pub fn module(mut self, module: Arc<Props>) -> Self {
        self.module = module;
        self
    }

    pub fn task(mut self, task: Arc<Props>) -> Self {
        self.task = task;
        self
    }

    pub fn module_overrides(mut self, module_overrides: Arc<Props>) -> Self {
        self.module_overrides = module_overrides;
        self
    }

    pub fn task_overrides(mut self, task_overrides: Arc<Props>) -> Self {
        self.task_overrides = task_overrides;
        self
    }

    pub fn new(
        module: Arc<Props>,
        module_overrides: Arc<Props>,
        task: Arc<Props>,
        task_overrides: Arc<Props>,
    ) -> Self {
        LazyProps {
            module,
            task,
            module_overrides,
            task_overrides,
        }
    }

    pub fn get(&self, key: &str) -> Option<minijinja::Value> {
        self.task_overrides
            .get(key)
            .cloned()
            .or_else(|| self.module_overrides.get(key).cloned())
            .or_else(|| self.task.get(key).cloned())
            .or_else(|| self.module.get(key).cloned())
    }
}

impl Serialize for LazyProps {
    fn serialize<S>(&self, serializer: S) -> Result<S::Ok, S::Error>
    where
        S: serde::Serializer,
    {
        let mut combined = HashMap::new();

        for (k, v) in self.module.iter() {
            combined.insert(k.clone(), v.clone());
        }
        for (k, v) in self.module_overrides.iter() {
            combined.insert(k.clone(), v.clone());
        }
        for (k, v) in self.task.iter() {
            combined.insert(k.clone(), v.clone());
        }
        for (k, v) in self.task_overrides.iter() {
            combined.insert(k.clone(), v.clone());
        }

        combined.serialize(serializer)
    }
}

impl Object for LazyProps {
    fn repr(self: &Arc<Self>) -> minijinja::value::ObjectRepr {
        minijinja::value::ObjectRepr::Map
    }

    fn get_value(self: &Arc<Self>, key: &minijinja::Value) -> Option<minijinja::Value> {
        self.get(key.as_str()?)
    }
}

#[derive(Debug, Serialize)]
pub struct TaskContext {
    pub props: LazyProps,
}

impl Object for TaskContext {
    fn repr(self: &std::sync::Arc<Self>) -> minijinja::value::ObjectRepr {
        minijinja::value::ObjectRepr::Map
    }

    fn get_value(self: &std::sync::Arc<Self>, key: &minijinja::Value) -> Option<minijinja::Value> {
        let key_str = key.as_str()?;
        let (namespace, key) = key_str.split_once('.')?;
        match namespace {
            "props" => self.props.get(key),
            _ => None,
        }
    }
}
