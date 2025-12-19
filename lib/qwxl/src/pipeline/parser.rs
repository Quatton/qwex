use crate::pipeline::{ast::ModuleFile, cache::Cache, error::PipelineError};

/// A parser for pipeline module files.
pub struct Parser {
    pub cache: Cache<String, ModuleFile>,
}

impl Parser {
    /// Create a parser with a fresh internal cache.
    pub fn new() -> Self {
        Self {
            cache: Cache::new(None),
        }
    }

    /// Create a parser that uses the provided cache manager.
    pub fn with_cache(cache: Cache<String, ModuleFile>) -> Self {
        Self { cache }
    }

    pub fn load_with<F>(&mut self, input: &str, parser: F) -> Result<&ModuleFile, PipelineError>
    where
        F: FnOnce(&str) -> Result<ModuleFile, PipelineError>,
    {
        let key = input.to_string();

        if self.cache.memory.contains_key(&key) {
            return Ok(self.cache.memory.get(&key).unwrap());
        }

        let module = parser(input)?;

        self.cache.insert(key.clone(), module);

        Ok(self
            .cache
            .memory
            .get(&key)
            .expect("Just inserted, should be there"))
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
        let mut parser = Parser::new();
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
            Task::Cmd { cmd, props } => {
                assert_eq!(cmd.trim(), r#"echo "Hello, World!""#);
                assert!(props.is_some());
            }
            _ => panic!("Expected Cmd task"),
        }
    }
}
