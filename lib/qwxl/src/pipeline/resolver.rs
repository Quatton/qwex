use crate::pipeline::{ast::Task, cache::Store};

struct EnvironmentContext {
    module_context: Store<String, String>,
}

pub fn normalize_task(task: Task) -> Task {
    match task {
        Task::Uses { props, uses } => Task::Cmd {
            props: None,
            cmd: format!(
                "{{{{ {}({}) }}}}",
                uses,
                props.map_or("{}".to_string(), |p| {
                    serde_json::to_string(&p).unwrap_or_else(|_| "{}".to_string())
                })
            ),
        },
        _ => task,
    }
}

#[cfg(test)]
mod tests {
    use crate::pipeline::{ast::Task, resolver::normalize_task};

    #[test]
    fn test_normalize_task() {
        let task = Task::Uses {
            uses: "moduleA.tasks.task".to_string(),
            props: None,
        };

        let normalized = normalize_task(task);

        match normalized {
            Task::Cmd { cmd, .. } => {
                assert_eq!(cmd, "{{ moduleA.tasks.task({}) }}");
            }
            _ => panic!("Expected Cmd task"),
        }
    }
}
