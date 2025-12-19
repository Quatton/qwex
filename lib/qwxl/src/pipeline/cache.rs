use ahash::{AHasher, HashMap, HashMapExt as _};
use serde::{Serialize, de::DeserializeOwned};
use std::hash::Hasher as _;

use std::fs;
use std::hash::Hash as _;
use std::path::PathBuf;

#[derive(Debug, Clone)]
pub struct Cache<K, V> {
    pub cache_dir: Option<PathBuf>,
    pub memory: HashMap<K, V>,
}

impl<K, V> Cache<K, V>
where
    K: Eq + std::hash::Hash + Clone + ToString,
    V: Serialize + DeserializeOwned + Clone,
{
    pub fn new(dir: Option<PathBuf>) -> Self {
        if let Some(ref path) = dir {
            let _ = fs::create_dir_all(path);
        }
        Self {
            cache_dir: dir,
            memory: HashMap::new(),
        }
    }

    pub fn with_dir(dir: PathBuf) -> Self {
        Self::new(Some(dir))
    }

    fn get_path_for_key(&self, key: &K) -> Option<PathBuf> {
        self.cache_dir.as_ref().map(|dir| {
            let mut hasher = AHasher::default();
            key.to_string().hash(&mut hasher);
            let hash = hasher.finish();
            dir.join(format!("{:x}.ron", hash))
        })
    }

    /// Private helper to handle disk persistence
    fn save_to_disk(&self, key: &K, value: &V) {
        if let Some(path) = self.get_path_for_key(key) {
            if let Ok(serialized) = ron::to_string(value) {
                let _ = fs::write(path, serialized);
            }
        }
    }

    pub fn insert(&mut self, key: K, value: V) {
        self.save_to_disk(&key, &value);
        self.memory.insert(key, value);
    }

    pub fn get(&mut self, key: &K) -> Option<&V> {
        // 1. If it's in memory, return it immediately
        if self.memory.contains_key(key) {
            return self.memory.get(key);
        }

        // 2. If not, try disk
        let disk_value = if let Some(path) = self.get_path_for_key(key) {
            if let Ok(contents) = fs::read_to_string(path) {
                match ron::from_str(&contents) {
                    Ok(v) => Some(v),
                    Err(_) => None,
                }
            } else {
                None
            }
        } else {
            None
        };

        // 3. If we found it on disk, put it in memory
        if let Some(v) = disk_value {
            self.memory.insert(key.clone(), v);
            // Now that it's inserted, we can return the reference from memory
            return self.memory.get(key);
        }

        None
    }
}
