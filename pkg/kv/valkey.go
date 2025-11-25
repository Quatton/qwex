package kv

import (
	"context"
	"time"

	"github.com/redis/go-redis/v9"
)

// ValkeyStore implements Store using Valkey/Redis as the backend.
type ValkeyStore struct {
	client *redis.Client
}

// ValkeyConfig holds configuration for connecting to Valkey.
type ValkeyConfig struct {
	Addr     string // host:port
	Password string // optional
	DB       int    // database number
}

// NewValkeyStore creates a new ValkeyStore with the given configuration.
func NewValkeyStore(cfg ValkeyConfig) (*ValkeyStore, error) {
	client := redis.NewClient(&redis.Options{
		Addr:     cfg.Addr,
		Password: cfg.Password,
		DB:       cfg.DB,
	})

	// Test connection
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()

	if err := client.Ping(ctx).Err(); err != nil {
		return nil, err
	}

	return &ValkeyStore{client: client}, nil
}

// Set stores a value with the given key and TTL.
func (s *ValkeyStore) Set(ctx context.Context, key string, value []byte, ttl time.Duration) error {
	return s.client.Set(ctx, key, value, ttl).Err()
}

// Get retrieves a value by key.
func (s *ValkeyStore) Get(ctx context.Context, key string) ([]byte, error) {
	val, err := s.client.Get(ctx, key).Bytes()
	if err != nil {
		if err == redis.Nil {
			return nil, ErrNotFound
		}
		return nil, err
	}
	return val, nil
}

// Delete removes a key.
func (s *ValkeyStore) Delete(ctx context.Context, key string) error {
	return s.client.Del(ctx, key).Err()
}

// SetNX sets a value only if the key doesn't exist.
func (s *ValkeyStore) SetNX(ctx context.Context, key string, value []byte, ttl time.Duration) (bool, error) {
	return s.client.SetNX(ctx, key, value, ttl).Result()
}

// Close closes the connection to Valkey.
func (s *ValkeyStore) Close() error {
	return s.client.Close()
}

// Ensure ValkeyStore implements Store.
var _ Store = (*ValkeyStore)(nil)
