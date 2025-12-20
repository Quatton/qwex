use std::path::PathBuf;

use ahash::{HashMap, HashMapExt as _, HashSet};

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

pub fn load_yaml(input: &str) -> Result<Module, PipelineError> {
    load_with(input, |i| serde_saphyr::from_str(i).map_err(Into::into))
}

pub fn load_ron(input: &str) -> Result<Module, PipelineError> {
    load_with(input, |i| ron::de::from_str(i).map_err(Into::into))
}

pub fn load_source(input: &str, ext: &str) -> Result<Module, PipelineError> {
    match ext {
        "yaml" | "yml" => load_yaml(input),
        "ron" => load_ron(input),
        other => Err(PipelineError::UnsupportedFormat(other.to_string())),
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

fn merge_module(base: &mut Module, addition: &Module) {
    for (task_name, task) in &addition.tasks {
        base.tasks.insert(task_name.clone(), task.clone());
    }

    for (prop_key, prop_value) in &addition.props {
        base.props.insert(prop_key.clone(), prop_value.clone());
    }
}

impl Pipeline {
    pub fn merge_features(&self, mf: Module, is_src: bool) -> Module {
        let mut default_module = Module {
            uses: mf.uses.clone(),
            props: mf.props.clone(),
            tasks: mf.tasks.clone(),
            modules: HashMap::new(),
        };

        let included_features = self.config.features.split(',').collect::<HashSet<_>>();

        if is_src {
            for (module_full_name, feature_module) in mf.modules.iter() {
                let (name, feature_opt) = parse_feature(module_full_name);

                if let Some(feature) = feature_opt {
                    if !included_features.contains(feature.as_str()) {
                        continue;
                    }
                }

                if name == TASK_PREFIX || name == PROP_PREFIX {
                    merge_module(&mut default_module, feature_module);
                    continue;
                }

                default_module
                    .modules
                    .entry(name)
                    .and_modify(|existing_module| {
                        merge_module(existing_module, feature_module);
                    })
                    .or_insert_with(|| feature_module.clone());
            }
        }

        default_module
    }

    pub fn parse(&mut self, path: PathBuf, is_src: bool) -> Result<Module, PipelineError> {
        let content = self.load_file(path.clone())?;
        let mf = load_source(
            content,
            path.extension().unwrap_or_default().to_str().unwrap_or(""),
        )?;
        Ok(self.merge_features(mf, is_src))
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
        match task1 {
            Task::Cmd { cmd, props, .. } => {
                assert_eq!(cmd.trim(), r#"echo "Hello, World!""#);
                assert!(props.is_some());
            }
            _ => panic!("Expected Cmd task"),
        }
    }

    #[test]
    fn test_load_multi_features() {
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
        feature1:
            tasks:
                task2:
                    cmd: |
                        echo "Feature 1"
        "#;

        let module = load_yaml(input);
        assert!(module.is_ok());
        let module = module.unwrap();
        assert!(module.modules.contains_key("feature1"));
    }
}
