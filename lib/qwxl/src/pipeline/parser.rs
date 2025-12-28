use ahash::{HashSet, RandomState};
use std::hash::{BuildHasher, Hasher};
use std::path::{Path, PathBuf};
use std::sync::Arc;

use crate::pipeline::ast::{IHashMap, MetaModule, UseRef};
use crate::pipeline::{
    Pipeline,
    ast::{Module, PROP_PREFIX, TASK_PREFIX},
    error::PipelineError,
};

// --- Hashing Utility ---
pub fn str_hash(t: &str) -> u64 {
    let mut h = RandomState::with_seed(0).build_hasher();
    h.write(t.as_bytes());
    h.finish()
}

// --- Loaders ---

pub fn load_with<F>(input: &str, parser: F) -> Result<Module, PipelineError>
where
    F: FnOnce(&str) -> Result<Module, PipelineError>,
{
    parser(input)
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

// --- Feature Logic ---

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
    if let Some(add_props) = &addition.props {
        if base.props.is_none() {
            base.props = Some(IHashMap::default());
            base.props.as_mut().unwrap().extend(add_props.clone());
        }
    }
}

/// Recursively merges features into a flat module structure based on the active feature set.
pub fn merge_features(mf: Module, is_src: bool, features: String) -> Module {
    let mut clean_module = Module {
        uses: mf.uses.clone(),
        props: mf.props.clone(),
        tasks: mf.tasks.clone(),
        modules: IHashMap::default(),
    };

    let active_features: HashSet<&str> = features.split(',').collect();

    if is_src {
        for (module_full_name, feature_module) in mf.modules.iter() {
            let (name, feature_opt) = parse_feature(module_full_name);

            // 1. Check if we should process this block
            if let Some(feature) = &feature_opt {
                if !active_features.contains(feature.as_str()) {
                    continue; // Skip inactive features
                }
            }

            // 2. Recursively process children first (deep merge preparation)
            // We pass 'true' to is_src because we are strictly inside the source definition
            let processed_submodule =
                merge_features(feature_module.clone(), true, features.clone());

            // 3. Merge Logic
            if name == TASK_PREFIX || name == PROP_PREFIX {
                // Merge into the current module (Overwrite behavior)
                merge_module_in_place(&mut clean_module, &processed_submodule);
            } else {
                // It's a submodule or a namespaced feature block
                clean_module
                    .modules
                    .entry(name)
                    .and_modify(|existing| merge_module_in_place(existing, &processed_submodule))
                    .or_insert(processed_submodule);
            }
        }
    } else {
        // If not source (e.g. imported), we generally just take it as is,
        // but we still might want to clean up if the imported module had internal features.
        // For now, simply copy submodules.
        clean_module.modules = mf.modules.clone();
    }

    clean_module
}

// --- Pipeline Integration ---

pub struct ModuleJob {
    pub path: PathBuf,
    pub alias: Option<String>,
    pub parent_alias: Option<String>,
}

impl Pipeline {
    fn resolve_import_path(&self, parent: &Path, import: &str) -> Result<PathBuf, PipelineError> {
        if import.starts_with("@std/") {
            return Ok(PathBuf::from(import));
        }
        let parent_dir = parent.parent().ok_or_else(|| {
            std::io::Error::new(std::io::ErrorKind::NotFound, "Parent path has no directory")
        })?;
        let joined = parent_dir.join(import);
        std::fs::canonicalize(&joined).map_err(|e| {
            PipelineError::Io(std::io::Error::new(
                e.kind(),
                format!("Failed to resolve import '{}': {}", import, e),
            ))
        })
    }

    pub fn parse(&mut self) -> Result<Arc<MetaModule>, PipelineError> {
        let path = std::fs::canonicalize(self.config.get_source_path())?;
        let job = ModuleJob {
            path,
            alias: Some(self.config.root_alias.clone()),
            parent_alias: None,
        };
        self.parse_one(job)
    }

    fn parse_one(&mut self, job: ModuleJob) -> Result<Arc<MetaModule>, PipelineError> {
        let content_arc = self.load_file(&job.path)?;
        let content_hash = str_hash(&content_arc);

        if let Some(alias) = &job.alias {
            self.stores.aliases.insert(alias.clone(), content_hash);
        }

        if let Some(module) = self.stores.metamodules.get(&content_hash) {
            return Ok(module.clone());
        }

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

        // Apply Feature Logic
        let is_src = job.parent_alias.is_none(); // Only apply to root source for now, or based on logic
        module = merge_features(module, is_src, self.config.features.clone());

        // Resolve Uses
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
                let dep_path = self.resolve_import_path(&job.path, rel_path)?;
                let dep_module = self.parse_one(ModuleJob {
                    path: dep_path,
                    alias: None,
                    parent_alias: job.alias.clone(),
                })?;
                *use_ref = UseRef::Hash(dep_module.hash);
            }
        }

        let metamodule = MetaModule {
            module,
            hash: content_hash,
            path_buf: job.path.clone(),
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

    fn get_cmd(m: &Module, task: &str) -> Option<String> {
        m.tasks.get(task).map(|t| t.cmd.trim().to_string())
    }

    #[test]
    fn test_feature_override_logic() {
        let input = r#"
            props: { env: "dev" }
            tasks: { build: { cmd: "cargo build" } }
            
            tasks[prod]:
                tasks:
                    build: { cmd: "cargo build --release" }
                    sign: { cmd: "gpg --sign" }
                props:
                    env: "prod"
        "#;

        let raw = load_yaml(input).unwrap();

        // 1. Default (Dev)
        let dev_mod = merge_features(raw.clone(), true, "default".to_string());
        assert_eq!(get_cmd(&dev_mod, "build").unwrap(), "cargo build");
        assert!(dev_mod.tasks.get("sign").is_none());
        assert_eq!(
            dev_mod.props.unwrap().get("env").unwrap().as_str().unwrap(),
            "dev"
        );

        // 2. Prod
        let prod_mod = merge_features(raw, true, "prod".to_string());
        assert_eq!(
            get_cmd(&prod_mod, "build").unwrap(),
            "cargo build --release"
        );
        assert!(prod_mod.tasks.get("sign").is_some());
        assert_eq!(
            prod_mod
                .props
                .unwrap()
                .get("env")
                .unwrap()
                .as_str()
                .unwrap(),
            "prod"
        );
    }

    #[test]
    fn test_feature_exclusion() {
        let input = r#"
            tasks[exp]:
                tasks: { secret: { cmd: "echo secret" } }
        "#;
        let raw = load_yaml(input).unwrap();
        let merged = merge_features(raw, true, "default".to_string());
        assert!(
            merged.tasks.get("secret").is_none(),
            "Experimental task should be excluded"
        );
    }
}
