use ahash::{HashMap, HashMapExt as _};
use std::hash::Hash;

use crate::pipeline::error::PipelineError;

/// A simple, high-performance memory store for pipeline artifacts.
pub struct Store<K, V> {
    memory: HashMap<K, V>,
}

impl<K, V> Store<K, V>
where
    K: Eq + Hash + Clone,
    V: Clone,
{
    pub fn new() -> Self {
        Self {
            memory: HashMap::new(),
        }
    }

    /// Insert a value directly into the store.
    pub fn insert(&mut self, key: K, value: V) {
        self.memory.insert(key, value);
    }

    /// Get a reference to a value if it exists.
    pub fn get(&self, key: &K) -> Option<&V> {
        self.memory.get(key)
    }

    /// The primary interface: Query memory, or run the producer function on a miss.
    /// Propagates any error that can be converted into a PipelineError.
    pub fn query_or_compute_with<F, E>(&mut self, key: K, f: F) -> Result<&V, E>
    where
        F: FnOnce() -> Result<V, E>,
        E: From<PipelineError>,
    {
        // 1. Fast path: check if we already have it
        if self.memory.contains_key(&key) {
            return Ok(self.memory.get(&key).expect("infallible"));
        }

        // 2. Slow path: run the producer
        let value = f()?;

        // 3. Store and return reference
        self.memory.insert(key.clone(), value);
        Ok(self.memory.get(&key).expect("infallible"))
    }
}
