use ahash::HashMap;

use crate::pipeline::{ast::ModuleFile, error::PipelineError};

#[derive(Default)]
struct Parser {
    ast_cache: HashMap<String, ModuleFile>,
}

impl Parser {
    fn load_with<F>(&mut self, input: &str, parser: F) -> Result<&ModuleFile, PipelineError>
    where
        F: FnOnce(&str) -> Result<ModuleFile, PipelineError>,
    {
        use std::collections::hash_map::Entry;

        match self.ast_cache.entry(input.to_string()) {
            Entry::Occupied(e) => Ok(e.into_mut()),
            Entry::Vacant(e) => Ok(e.insert(parser(input)?)),
        }
    }

    pub fn load_yaml(&mut self, input: &str) -> Result<&ModuleFile, PipelineError> {
        self.load_with(input, |i| serde_saphyr::from_str(i).map_err(Into::into))
    }

    pub fn load_ron(&mut self, input: &str) -> Result<&ModuleFile, PipelineError> {
        self.load_with(input, |i| {
            ron::from_str(i).map_err(|e| PipelineError::ParseError(e.to_string()))
        })
    }
}

#[cfg(test)]
mod tests {
    use crate::pipeline::ast::Task;

    use super::*;
    #[test]
    fn test_load_yaml() {
        let mut parser = Parser::default();
        let input = r#"
        default: 
          tasks:
            task1:
              cmd: |
                echo "Hello, World!"
        "#;
        let module = parser.load_yaml(input);
        assert!(module.is_ok());
        let module = module.unwrap();
        println!("{:#?}", module);
        let default = module.get("default");
        assert!(default.is_some());
        let default = default.unwrap();
        let task1 = default.tasks.get("task1");
        assert!(task1.is_some());
        let task1 = task1.unwrap();
        match task1 {
            Task::Cmd { cmd, .. } => {
                assert_eq!(cmd.trim(), r#"echo "Hello, World!""#);
            }
            _ => panic!("Expected Cmd task"),
        }
    }
}
