use crate::pipeline::{ast::ModuleFile, error::PipelineError};

fn load_with<F>(input: &str, parser: F) -> Result<ModuleFile, PipelineError>
where
    F: FnOnce(&str) -> Result<ModuleFile, PipelineError>,
{
    parser(input)
}

pub fn load_yaml(input: &str) -> Result<ModuleFile, PipelineError> {
    load_with(input, |i| serde_saphyr::from_str(i).map_err(Into::into))
}

pub fn load_ron(input: &str) -> Result<ModuleFile, PipelineError> {
    load_with(input, |i| ron::from_str(i).map_err(PipelineError::from))
}

#[cfg(test)]
mod tests {
    use crate::pipeline::{ast::Task, parser::load_yaml};

    #[test]
    fn test_load_yaml() {
        let input = r#"
        default: 
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
        let default = &module.default;
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
        default: 
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
        assert!(module.features.contains_key("feature1"));
    }
}
