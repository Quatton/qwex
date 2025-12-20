use std::fmt::format;

use minijinja::Environment;

use crate::pipeline::{
    ast::{Module, TASK_INLINE_KEYWORD, Task},
    cache::Store,
};

pub enum ReferenceType {
    Task(Task),
    Module(Module),
    Prop,
    Alias(String),
}

pub type ReferenceTree = Store<String, ReferenceType>;

pub fn normalize_task(task: Task) -> Task {
    match task {
        Task::Uses { props, uses } => Task::Cmd {
            props,
            cmd: format!("{{{{ {}.{} }}}}", uses, TASK_INLINE_KEYWORD),
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
                assert_eq!(cmd, "{{ moduleA.tasks.task.cmd }}");
            }
            _ => panic!("Expected Cmd task"),
        }
    }
}
