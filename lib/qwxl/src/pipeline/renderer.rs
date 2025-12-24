use minijinja::Environment;

pub const SCRIPT_TEMPLATE_NAME: &str = "templates/script.sh.j2";

pub fn register_templates(env: &mut Environment) {
    let script_template = include_str!("templates/script.sh.j2");
    env.add_template(SCRIPT_TEMPLATE_NAME, script_template)
        .expect("Failed to add script_template");
}

#[cfg(test)]
mod tests {}
