// Package kv provides a key-value store abstraction for token storage.
// This allows swapping backends (Valkey/Redis, in-memory, etc.) without
// changing the auth service implementation.
package kv

import (
	"context"
	"time"
)

// Store defines a minimal key-value interface for token storage.
// Keys are strings, values are byte slices. All operations support TTL.
type Store interface {
	// Set stores a value with the given key and TTL.
	// If TTL is 0, the key does not expire.
	Set(ctx context.Context, key string, value []byte, ttl time.Duration) error

	// Get retrieves a value by key. Returns ErrNotFound if key doesn't exist.
	Get(ctx context.Context, key string) ([]byte, error)

	// Delete removes a key. Returns nil if key doesn't exist.
	Delete(ctx context.Context, key string) error

	// SetNX sets a value only if the key doesn't exist (atomic).
	// Returns true if the key was set, false if it already existed.
	SetNX(ctx context.Context, key string, value []byte, ttl time.Duration) (bool, error)

	// Close closes the connection to the store.
	Close() error
}
