use std::sync::{Arc, Mutex, RwLock};

use ahash::{HashMap, HashSet, HashSetExt as _};
use minijinja::{Value, context, value::Object};
use serde::Serialize;

use crate::pipeline::{
    PipelineStore,
    ast::{IHashMap, IHashSet, Module, UseRef},
    error::PipelineError,
};

pub const SCRIPT_TEMPLATE_NAME: &str = "script.sh.j2";
pub const SCRIPT_TEMPLATE_SOURCE: &str = include_str!("templates/script.sh.j2");

#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
pub enum Resource {
    Task { 
        cmd: String, 
        props: IHashMap<String, Value>, 
        rendered: String,

    
    
     },
    Prop { value: Value },
}


#[derive(Debug, Clone, PartialEq, Eq, Hash, Serialize)]
pub enum ResourceType {
    Props,
    Tasks,
    Modules(String),
}

impl ToString for ResourceType {
    fn to_string(&self) -> String {
        match self {
            ResourceType::Props => "props".to_string(),
            ResourceType::Tasks => "tasks".to_string(),
            ResourceType::Modules(name) => name.to_string(),
        }
    }
}

#[derive(Debug, Clone, PartialEq, Eq, Hash, Serialize)]
pub struct RenderTarget {
    hash: u64,
    resource: ResourceType,
    name: String,
}

impl ToString for RenderTarget {
    fn to_string(&self) -> String {
        format!("{}.{}.{}", self.hash, self.resource.to_string(), self.name)
    }
}

#[derive(Debug, Serialize)]
struct DependencyCollector {
    pub target: RenderTarget,
    pub store: Arc<PipelineStore>,
    pub hard_deps: Arc<RwLock<HashMap<RenderTarget, HashSet<RenderTarget>>>>,
    pub soft_deps: Arc<RwLock<HashMap<RenderTarget, HashSet<RenderTarget>>>>,
}

impl DependencyCollector {
    pub fn new(
        target: RenderTarget,
        store: Arc<PipelineStore>,
        hard_deps: Arc<RwLock<HashMap<RenderTarget, HashSet<RenderTarget>>>>,
        soft_deps: Arc<RwLock<HashMap<RenderTarget, HashSet<RenderTarget>>>>,
    ) -> Self {
        Self {
            target,
            store,
            hard_deps,
            soft_deps,
        }
    }
}

fn grab_use_hash(uses: &Option<UseRef>) -> Option<u64> {
    match uses {
        Some(UseRef::Hash(hash)) => Some(*hash),
        Some(UseRef::Define(_)) => unreachable!("Define use entries should not appear in resolved modules"),
        None => None,
    }
}

fn check_is_valid_target(store: &PipelineStore, target: &RenderTarget) -> bool {
    let module = match store.metamodules.get(&target.hash) {
        Some(m) => m,
        None => return false,
    };

    match &target.resource {
        ResourceType::Props => {
            if let Some(props) = &module.module.props {
                if props.contains_key(&target.name) {
                    return true;
                }
            }

            grab_use_hash(&module.module.uses)
                .and_then(|use_hash| check_is_valid_target(store, &RenderTarget {
                    hash: use_hash,
                    resource: ResourceType::Props,
                    name: target.name.clone(),
                }).then(|| true))
                .unwrap_or(false)
        }

        ResourceType::Tasks => {
            if module.module.tasks.contains_key(&target.name) {
                return true;
            }

            grab_use_hash(&module.module.uses)
                .and_then(|use_hash| check_is_valid_target(store, &RenderTarget {
                    hash: use_hash,
                    resource: ResourceType::Tasks,
                    name: target.name.clone(),
                }).then(|| true))
                .unwrap_or(false)
        }

        ResourceType::Modules(submodule_name) => {
            let submodule = match module.module.modules.get(submodule_name) {
                Some(sub) => sub,
                None => return false, 
            };

            if submodule.tasks.contains_key(&target.name) {
                return true;
            }

            grab_use_hash(&submodule.uses)
                .and_then(|use_hash| check_is_valid_target(store, &RenderTarget {
                    hash: use_hash,
                    resource: ResourceType::Tasks,
                    name: target.name.clone(),
                }).then(|| true))
                .unwrap_or(false)
        }
    }
}

impl Object for DependencyCollector  {
    fn get_value(self: &Arc<Self>, key: &minijinja::Value) -> Option<minijinja::Value> {
        let target = RenderTarget {
            hash: self.target.hash,
            resource: self.target.resource.clone(),
            name: key.as_str()?.to_string(),
        };

        
        if !check_is_valid_target(&self.store, &target) {
            return None;
        }
        

        if let Some(rendered) = self.store.rendered.get(&target) {
            match rendered {
                Resource::Prop { value } => {
                    return Some(value.clone());
                }
                Resource::Task { .. } => {
                    return Some(format!("{}:{}", self.store.aliases.get(&target.hash)?.to_string(), target.name).into());
                }
            }
        }

        let deps_store = if let ResourceType::Props = self.target.resource {
           &mut self.hard_deps.write().unwrap()
        } else {
            &mut self.soft_deps.write().unwrap()
        };

        let entry = deps_store.entry(self.target.clone()).or_insert_with(HashSet::new);
        entry.insert(target.clone());

        Some(minijinja::Value::from("<resolving>"))
    }
    
}

fn render_resource<'a>(
    env: &minijinja::Environment<'a>,
    dc: &DependencyCollector,
    target: &RenderTarget,
) -> Result<Arc<String>, PipelineError> {
    let rendered = dc.store.rendered.get(target);
    if let Some(content) = rendered {
        return Ok(content.clone());
    }

    let result = env.render_named_str(&target.to_string(), source, ctx)
}

// store, module hash, submodule name, props/tasks, name

impl Pipeline {
    pub fn render(&self) -> Result<(), PipelineError> {}

    fn render_body(&self, body: &str) -> Result<String, PipelineError> {
        /*
           {{ tasks.name }}
           {{ props.name }}
           {{ module.name}}
        */
    }
}
