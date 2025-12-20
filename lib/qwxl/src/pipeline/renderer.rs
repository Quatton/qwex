use minijinja::Environment;

pub struct ScriptNode {
    pub preamble: String,
}

pub struct TaskNode {
    pub body: String,
    pub dependencies: Vec<String>,
}

pub const SCRIPT_TEMPLATE_NAME: &str = "__internal__/script";

pub fn register_templates(env: &mut Environment) {
    let script_template = include_str!("templates/script.sh.j2");
    env.add_template(SCRIPT_TEMPLATE_NAME, script_template)
        .expect("Failed to add script_template");
}

pub fn render(env: &Environment) -> Result<String, crate::pipeline::error::PipelineError> {
    let template = env.get_template(SCRIPT_TEMPLATE_NAME)?;

    let rendered = template.render(())?;

    Ok(rendered)
}
