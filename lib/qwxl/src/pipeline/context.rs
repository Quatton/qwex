use ahash::HashMap;
use minijinja::value::Object;

pub type Props = HashMap<String, minijinja::Value>;

#[derive(Debug)]
pub struct TaskContext {
    pub props: Props,
}

impl TaskContext {
    pub fn new(props: Props) -> TaskContext {
        TaskContext { props }
    }
}

impl TaskContext {}

impl Object for TaskContext {
    fn repr(self: &std::sync::Arc<Self>) -> minijinja::value::ObjectRepr {
        minijinja::value::ObjectRepr::Map
    }

    fn get_value(self: &std::sync::Arc<Self>, key: &minijinja::Value) -> Option<minijinja::Value> {
        let key_str = key.as_str()?;
        self.props.get(key_str).cloned()
    }
}
