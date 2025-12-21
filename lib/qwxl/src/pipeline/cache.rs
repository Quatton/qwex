use ahash::AHashMap;
use serde::Serialize;
use std::hash::Hash;
use std::sync::Arc;

use crate::pipeline::error::PipelineError;

/// A simple, high-performance memory store for pipeline artifacts.
#[derive(Debug, Serialize)]
pub struct Store<K, V>
where
    K: Eq + Hash + Clone + Serialize,
{
    #[serde(flatten)]
    memory: AHashMap<K, Arc<V>>,
}

impl<K, V> Store<K, V>
where
    K: Eq + Hash + Clone + Serialize,
    V: Serialize,
{
    pub fn new() -> Self {
        Self {
            memory: AHashMap::new(),
        }
    }

    /// Insert a value directly into the store (wraps it in `Arc`).
    pub fn insert(&mut self, key: K, value: V) -> Option<Arc<V>> {
        self.memory.insert(key, Arc::new(value))
    }

    /// Get a cloned `Arc` to a value if it exists.
    pub fn get(&self, key: &K) -> Option<Arc<V>> {
        self.memory.get(key).cloned()
    }

    /// The primary interface: Query memory, or run the producer function on a miss.
    /// Returns an `Arc` to the value and propagates any error that can be converted into a PipelineError.
    pub fn query_or_compute_with<F, E>(&mut self, key: K, f: F) -> Result<Arc<V>, E>
    where
        F: FnOnce() -> Result<V, E>,
        E: From<PipelineError>,
    {
        // 1. Fast path: check if we already have it
        if let Some(v) = self.memory.get(&key) {
            return Ok(v.clone());
        }

        // 2. Slow path: run the producer
        let value = f()?;

        // 3. Store and return Arc
        let arc = Arc::new(value);
        self.memory.insert(key.clone(), arc.clone());
        Ok(arc)
    }

    pub fn query_or_compute_as_arc<F, E>(&mut self, key: K, f: F) -> Result<Arc<V>, E>
    where
        F: FnOnce() -> Result<Arc<V>, E>,
        E: From<PipelineError>,
    {
        // 1. Fast path: check if we already have it
        if let Some(v) = self.memory.get(&key) {
            return Ok(v.clone());
        }

        // 2. Slow path: run the producer
        let arc = f()?;

        // 3. Store (but no need to create a new Arc) and return Arc
        self.memory.insert(key.clone(), arc.clone());
        Ok(arc)
    }
}
