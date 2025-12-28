use ahash::AHashMap;
use derive_more::{Deref, DerefMut, IntoIterator};
use serde::Serialize;
use std::{hash::Hash, sync::Arc};

use crate::pipeline::error::PipelineError;
/// A simple, high-performance memory store for pipeline artifacts.
#[derive(Debug, Serialize, IntoIterator, Deref, DerefMut, Clone)]
#[into_iterator(owned, ref, ref_mut)]
pub struct Store<K, V>(pub AHashMap<K, Arc<V>>)
where
    K: Eq + Hash + Clone + Serialize;

impl<K, V> Store<K, V>
where
    K: Eq + Hash + Clone + Serialize,
    V: Serialize,
{
    pub fn new() -> Self {
        Self(AHashMap::new())
    }

    /// Insert a value directly into the store (wraps it in `Arc`).
    pub fn insert(&mut self, key: K, value: V) -> Option<Arc<V>> {
        self.0.insert(key, Arc::new(value))
    }

    pub fn insert_as_arc(&mut self, key: K, value: Arc<V>) -> Option<Arc<V>> {
        self.0.insert(key, value)
    }

    // Get a cloned `Arc` to a value if it exists.
    // pub fn get<Q>(&self, key: &Q) -> Option<Arc<V>>
    // where
    //     K: std::borrow::Borrow<Q>,
    //     Q: Hash + Eq + ?Sized,
    // {
    //     self.0.get(key).cloned()
    // }

    /// The primary interface: Query memory, or run the producer function on a miss.
    /// Returns an `Arc` to the value and propagates any error that can be converted into a PipelineError.
    pub fn query_or_compute_with<F, E>(&mut self, key: K, f: F) -> Result<Arc<V>, E>
    where
        F: FnOnce() -> Result<V, E>,
        E: From<PipelineError>,
    {
        // 1. Fast path: check if we already have it
        if let Some(v) = self.0.get(&key) {
            return Ok(v.clone());
        }

        // 2. Slow path: run the producer
        let value = f()?;

        // 3. Store and return Arc
        let arc = Arc::new(value);
        self.0.insert(key.clone(), arc.clone());
        Ok(arc)
    }

    pub fn query_or_compute_as_arc<F, E>(&mut self, key: K, f: F) -> Result<Arc<V>, E>
    where
        F: FnOnce() -> Result<Arc<V>, E>,
        E: From<PipelineError>,
    {
        // 1. Fast path: check if we already have it
        if let Some(v) = self.0.get(&key) {
            return Ok(v.clone());
        }

        // 2. Slow path: run the producer
        let arc = f()?;

        // 3. Store (but no need to create a new Arc) and return Arc
        self.0.insert(key.clone(), arc.clone());
        Ok(arc)
    }
}

impl Default for Store<(), ()> {
    fn default() -> Self {
        Self::new()
    }
}
