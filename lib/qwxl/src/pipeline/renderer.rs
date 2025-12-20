use minijinja::{Environment, context};

pub struct TaskNode {
    pub body: String,
    pub dependencies: Vec<String>,
}

pub const SCRIPT_TEMPLATE_NAME: &str = "templates/script.sh.j2";

pub fn register_templates(env: &mut Environment) {
    let script_template = include_str!("templates/script.sh.j2");
    env.add_template(SCRIPT_TEMPLATE_NAME, script_template)
        .expect("Failed to add script_template");
}

pub fn render(env: &Environment) -> Result<String, crate::pipeline::error::PipelineError> {
    let template = env.get_template(SCRIPT_TEMPLATE_NAME)?;

    let rendered = template.render(context! {
        tasks => vec![""],
    })?;

    Ok(rendered)
}

#[cfg(test)]
mod tests {

    use crate::pipeline::{
        context::{LazyProps, TaskContext},
        renderer::register_templates,
    };

    use ahash::HashMap;
    use minijinja::Environment;

    #[test]
    fn test_render_script() {
        let mut env = Environment::new();
        env.set_undefined_behavior(minijinja::UndefinedBehavior::Strict);
        register_templates(&mut env);

        let res = env.render_str(
            "hi {{ props.prop1 }}",
            TaskContext {
                props: LazyProps {
                    task: std::sync::Arc::new(HashMap::from_iter([(
                        "prop1".to_string(),
                        minijinja::Value::from("value1"),
                    )])),
                    task_overrides: std::sync::Arc::new(HashMap::from_iter([(
                        "prop1".to_string(),
                        minijinja::Value::from("override1"),
                    )])),
                    ..Default::default()
                },
            },
        );

        assert!(res.is_ok());
        let output = res.unwrap();
        assert_eq!(output, "hi override1");
    }
}
