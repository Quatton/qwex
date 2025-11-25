package kv

import "errors"

// ErrNotFound is returned when a key does not exist in the store.
var ErrNotFound = errors.New("kv: key not found")
