use ahash::RandomState;
use std::hash::{BuildHasher, Hasher};
use std::path::{Path, PathBuf};
use std::sync::Arc;

use ahash::HashSet;

use crate::pipeline::ast::{IHashMap, MetaModule, UseRef};
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
        modules: IHashMap::with_hasher(RandomState::with_seed(0)),
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
    pub path: PathBuf,
    /// The alias to register this module under (e.g., "root.backend").
    /// If None, the module is parsed and hashed but not aliased (anonymous dependency).
    pub alias: Option<String>,
    /// The alias of the module that imported this one (for relative path resolution).
    pub parent_alias: Option<String>,
}
impl Pipeline {
    fn resolve_import_path(&self, parent: &Path, import: &str) -> Result<PathBuf, PipelineError> {
        // 1. Virtual Import (e.g., "uses: @std/log")
        if import.starts_with("@std/") {
            return Ok(PathBuf::from(import));
        }

        // 2. Parent is Physical (File System)
        let parent_dir = parent.parent().ok_or_else(|| {
            std::io::Error::new(std::io::ErrorKind::NotFound, "Parent path has no directory")
        })?;

        let joined = parent_dir.join(import);

        // Canonicalize only physical paths to resolve symlinks and ".."
        std::fs::canonicalize(&joined).map_err(|e| {
            PipelineError::Io(std::io::Error::new(
                e.kind(),
                format!(
                    "Failed to resolve import '{}' from '{:?}': {}",
                    import, parent, e
                ),
            ))
        })
    }

    /// Entry point for the root file
    pub fn parse(&mut self) -> Result<Arc<MetaModule>, PipelineError> {
        let path = std::fs::canonicalize(&self.config.source_path)?;

        let job = ModuleJob {
            path,
            alias: Some(self.config.root_alias.clone()),
            parent_alias: None,
        };

        self.parse_one(job)
    }

    fn parse_one(&mut self, job: ModuleJob) -> Result<Arc<MetaModule>, PipelineError> {
        // 1. Load & Hash
        let content_arc = self.load_file(&job.path)?;
        let content_hash = str_hash(&content_arc);

        // 2. Update Stores
        self.stores.sources.insert(content_hash, job.path.clone());
        if let Some(alias) = &job.alias {
            self.stores.aliases.insert(alias.clone(), content_hash);
        }

        // 3. Cache Hit
        if let Some(module) = self.stores.metamodules.get(&content_hash) {
            return Ok(module.clone());
        }

        // 4. Parse AST
        let path_str = job.path.to_string_lossy();
        let ext = if path_str.starts_with("@std") {
            "yaml"
        } else {
            job.path
                .extension()
                .and_then(|s| s.to_str())
                .unwrap_or("yaml")
        };

        let mut module = load_source(&content_arc, ext)?;

        // 5. Merge Features
        let is_src = job.parent_alias.is_none();
        module = merge_features(module, is_src, self.config.features.clone());

        // 6. Resolve Dependencies
        let mut references: Vec<&mut UseRef> = vec![];
        if let Some(u) = module.uses.as_mut() {
            references.push(u);
        }
        for sub in module.modules.values_mut() {
            if let Some(u) = sub.uses.as_mut() {
                references.push(u);
            }
        }

        for use_ref in references {
            if let UseRef::Define(rel_path) = use_ref {
                // This handles "./utils" inside "@std/log" correctly
                let dep_path = self.resolve_import_path(&job.path, rel_path)?;

                let dep_module = self.parse_one(ModuleJob {
                    path: dep_path,
                    alias: None, // Implicit imports are anonymous
                    parent_alias: job.alias.clone(),
                })?;

                *use_ref = UseRef::Hash(dep_module.hash);
            }
        }

        // 7. Store
        let metamodule = MetaModule {
            module,
            hash: content_hash,
        };
        let arc = Arc::new(metamodule);
        self.stores
            .metamodules
            .insert_as_arc(content_hash, arc.clone());

        Ok(arc)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_parse_feature_string() {
        assert_eq!(parse_feature("mod"), ("mod".to_string(), None));
        assert_eq!(
            parse_feature("mod[foo]"),
            ("mod".to_string(), Some("foo".to_string()))
        );
        assert_eq!(
            parse_feature("mod[foo-bar]"),
            ("mod".to_string(), Some("foo-bar".to_string()))
        );
    }

    #[test]
    fn test_feature_flag_merging() {
        // Test AST:
        // root:
        //   tasks[featA]: { t1: "A" }
        //   tasks[featB]: { t1: "B" }
        //   sub[featA]: { ... }
        let input = r#"
            tasks[featA]:
                t1: { cmd: "A" }
            tasks[featB]:
                t1: { cmd: "B" }
        "#;

        let raw_mod = load_yaml(input).unwrap();

        // Case 1: Enable featA
        let mod_a = merge_features(raw_mod.clone(), true, "featA".to_string());
        let t1_a = mod_a.tasks.get("t1").unwrap();
        assert_eq!(t1_a.cmd, "A");

        // Case 2: Enable featB
        // Note: Logic in merge_features iterates map. Since Order is preserved (IndexMap),
        // latter overrides former if both features enabled, or if just one enabled.
        let mod_b = merge_features(raw_mod.clone(), true, "featB".to_string());
        let t1_b = mod_b.tasks.get("t1").unwrap();
        assert_eq!(t1_b.cmd, "B");
    }

    #[test]
    fn test_load_yaml() {
        let input = r#"
            tasks:
                task1: 
                    props:
                        foo: "bar"
                    cmd: |
                        echo "Hello"
            "#;
        let module = load_yaml(input);
        assert!(module.is_ok());
        let t = module.unwrap().tasks.get("task1").unwrap().clone();
        assert_eq!(t.cmd.trim(), r#"echo "Hello""#);
    }
}
