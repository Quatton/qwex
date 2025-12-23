use ahash::RandomState;
use std::hash::{BuildHasher, Hasher};
use std::{path::PathBuf, sync::Arc};

use ahash::{HashMap, HashMapExt as _, HashSet};

use crate::pipeline::ast::{MetaModule, UseRef};
use crate::pipeline::{
    Pipeline,
    ast::{Module, PROP_PREFIX, TASK_PREFIX},
    error::PipelineError,
};

pub fn load_with<F>(input: &str, parser: F) -> Result<Module, PipelineError>
where
    F: FnOnce(&str) -> Result<Module, PipelineError>,
{
    parser(input)
}

pub fn str_hash(t: &str) -> u64 {
    let mut h = RandomState::with_seed(0).build_hasher();
    h.write(t.as_bytes());
    h.finish()
}

pub fn load_yaml(input: &str) -> Result<Module, PipelineError> {
    load_with(input, |i| serde_saphyr::from_str(i).map_err(Into::into))
}

pub fn load_ron(input: &str) -> Result<Module, PipelineError> {
    load_with(input, |i| ron::from_str(i).map_err(Into::into))
}

pub fn load_source(input: &str, ext: &str) -> Result<Module, PipelineError> {
    match ext {
        "yaml" | "yml" => load_yaml(input),
        "ron" => load_ron(input),
        other => load_yaml(input).map_err(|_| {
            PipelineError::UnsupportedFormat(format!("Unsupported file format: {}", other))
        }),
    }
}

pub fn parse_feature(full_name: &str) -> (String, Option<String>) {
    if let Some((name, feature_box)) = full_name.split_once('[') {
        let feature_cleaned = feature_box.trim_matches(|c| c == '[' || c == ']');
        (name.to_string(), Some(feature_cleaned.to_string()))
    } else {
        (full_name.to_string(), None)
    }
}

pub fn get_parent_alias(alias: &str) -> Option<&str> {
    let parts: Vec<&str> = alias.rsplitn(2, '.').collect();
    if parts.is_empty() {
        return None;
    }
    Some(if parts.len() == 2 { parts[1] } else { "" })
}

fn merge_module_in_place(base: &mut Module, addition: &Module) {
    for (task_name, task) in &addition.tasks {
        base.tasks.insert(task_name.clone(), task.clone());
    }

    for (prop_key, prop_value) in &addition.props {
        base.props.insert(prop_key.clone(), prop_value.clone());
    }
}

fn merge_features(mf: Module, is_src: bool, features: String) -> Module {
    let mut default_module = Module {
        uses: mf.uses.clone(),
        props: mf.props.clone(),
        tasks: mf.tasks.clone(),
        modules: HashMap::new(),
    };

    let included_features = features.split(',').collect::<HashSet<_>>();

    if is_src {
        for (module_full_name, feature_module) in mf.modules.iter() {
            let (name, feature_opt) = parse_feature(module_full_name);

            if let Some(feature) = feature_opt {
                if !included_features.contains(feature.as_str()) {
                    continue;
                }
            }

            if name == TASK_PREFIX || name == PROP_PREFIX {
                merge_module_in_place(&mut default_module, feature_module);
                continue;
            }

            default_module
                .modules
                .entry(name)
                .and_modify(|existing_module| {
                    merge_module_in_place(existing_module, feature_module);
                })
                .or_insert_with(|| feature_module.clone());
        }
    }

    default_module
}

/// A nicer job type for the module/file queue.
pub struct ModuleJob {
    pub path: String,
    pub from: Option<String>,
    pub alias: String,
}

impl Pipeline {
    pub fn load_source(&mut self, content: &str, path_str: &str) -> Result<Module, PipelineError> {
        let path_string = PathBuf::from(path_str);
        let ext = path_string
            .extension()
            .and_then(|s| s.to_str())
            .unwrap_or("");
        let module = load_source(content, ext)?;

        Ok(module)
    }

    pub fn resolve_path_and_alias(
        &mut self,
        job: &ModuleJob,
    ) -> Result<(String, String), PipelineError> {
        if job.from.is_none() && job.alias != self.config.root_alias {
            return Err(PipelineError::InvalidAliasFormat(
                "my fault bro this should not happen".to_string(),
            ));
        }

        if job.alias.contains('.') {
            return Err(PipelineError::InvalidAliasFormat(format!(
                "Alias '{}' cannot contain '.' characters",
                job.alias
            )));
        }

        let joined_alias = if let Some(from_alias) = &job.from {
            format!("{}.{}", from_alias, job.alias)
        } else {
            job.alias.clone()
        };

        if job.path.starts_with("@std") {
            return Ok((job.path.clone(), joined_alias));
        }

        let from_path = if let Some(from_alias) = &job.from {
            let source_path = self.stores.source_paths.get(from_alias).ok_or(
                PipelineError::ImportAliasNotFound(
                    "this is probably my fault. please report".to_string(),
                ),
            )?;
            (*source_path).clone()
        } else {
            job.path.clone()
        };

        let parent_path = PathBuf::from(from_path)
            .parent()
            .ok_or(PipelineError::Io(std::io::Error::new(
                std::io::ErrorKind::NotFound,
                "parent path not found",
            )))?
            .to_path_buf();

        let resolved_path = parent_path.join(&job.path);

        let alias = joined_alias.clone();
        let path = resolved_path.to_string_lossy().to_string();

        self.stores.source_paths.insert(alias.clone(), path.clone());

        Ok((path, joined_alias))
    }

    pub fn parse_root(&mut self) -> Result<Arc<MetaModule>, PipelineError> {
        let source_path = self.config.source_path.clone();

        let job = ModuleJob {
            path: std::fs::canonicalize(&source_path)
                .map_err(PipelineError::from)?
                .to_string_lossy()
                .to_string(),
            from: None,
            alias: self.config.root_alias.clone(),
        };

        let metamodule = self.parse(&job)?;

        Ok(metamodule)
    }

    pub fn parse(&mut self, job: &ModuleJob) -> Result<Arc<MetaModule>, PipelineError> {
        let (path, alias) = self.resolve_path_and_alias(job)?;

        let content_arc = self.load_file(&path)?;

        let content_hash = str_hash(&content_arc);

        if let Some(module) = self.stores.metamodules.get(&content_hash) {
            return Ok(module);
        }

        let mut module = self.load_source(&content_arc, &path)?;

        let is_src = job.from.is_none();

        module = merge_features(module, is_src, self.config.features.clone());

        if let Some(use_entry) = &mut module.uses {
            match use_entry {
                UseRef::Define(path) => {
                    let use_job = ModuleJob {
                        alias: alias.clone(),
                        from: job.from.clone(),
                        path: path.clone(),
                    };

                    // will scream if it is already visited before, signaling cyclic dependencies
                    let module = self.parse(&use_job)?;

                    *use_entry = UseRef::Hash(module.hash);
                }
                UseRef::Hash(_) => {
                    unreachable!("Module seen for the first time already has its `uses` hashed?")
                }
            }
        }

        for (_, submodule) in module.modules.iter_mut() {
            if let Some(use_entry) = &mut submodule.uses {
                match use_entry {
                    UseRef::Define(path) => {
                        let use_job = ModuleJob {
                            alias: alias.clone(),
                            from: job.from.clone(),
                            path: path.clone(),
                        };

                        // will scream if it is already visited before, signaling cyclic dependencies
                        let module = self.parse(&use_job)?;

                        *use_entry = UseRef::Hash(module.hash);
                    }
                    UseRef::Hash(_) => {
                        unreachable!(
                            "Module seen for the first time already has its `uses` hashed?"
                        )
                    }
                }
            }
        }

        let metamodule = MetaModule {
            module,
            hash: content_hash,
        };

        let metamodule_arc = Arc::new(metamodule);

        self.stores
            .metamodules
            .insert_as_arc(content_hash, metamodule_arc.clone());

        self.stores
            .aliases
            .insert_as_arc(alias.clone(), metamodule_arc.clone());

        Ok(metamodule_arc)
    }
}

#[cfg(test)]
mod tests {
    use crate::pipeline::{ast::Task, parser::load_yaml};

    #[test]
    fn test_load_yaml() {
        let input = r#"
            tasks:
                task1: 
                    props:
                        foo: "bar"
                        nested:
                        - 1
                        - 2
                        - 3
                    cmd: |
                        echo "Hello, World!"
            "#;
        let module = load_yaml(input);
        assert!(module.is_ok());
        let module = module.unwrap();
        let default = &module;
        let task1 = default.tasks.get("task1");
        assert!(task1.is_some());
        let task1 = task1.unwrap();
        let Task { cmd, props, .. } = task1;
        assert_eq!(cmd.trim(), r#"echo "Hello, World!""#);
        assert!(props.get("foo").is_some());
    }

    #[test]
    fn test_load_multi_modules() {
        let input = r#"
            tasks:
                task1: 
                    props:
                        foo: "bar"
                        nested:
                        - 1
                        - 2
                        - 3
                    cmd: |
                        echo "Hello, World!"
            module1:
                tasks:
                    task2:
                        cmd: |
                            echo "Feature 1"
            "#;

        let module = load_yaml(input);
        assert!(module.is_ok());
        let module = module.unwrap();
        assert!(module.modules.contains_key("module1"));
    }
}
