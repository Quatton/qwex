// Package qart provides artifact storage for job runs using S3-compatible storage.
package qart

import (
	"context"
	"io"
	"time"
)

// Artifact represents a stored artifact with metadata.
type Artifact struct {
	Key          string            `json:"key"`           // S3 key (e.g., "runs/abc123/stdout.log")
	Bucket       string            `json:"bucket"`        // Bucket name
	Size         int64             `json:"size"`          // Size in bytes
	ContentType  string            `json:"content_type"`  // MIME type
	LastModified time.Time         `json:"last_modified"` // Last modification time
	Metadata     map[string]string `json:"metadata"`      // Custom metadata
	URL          string            `json:"url,omitempty"` // Presigned URL (when requested)
}

// Store defines the interface for artifact storage operations.
type Store interface {
	// Upload uploads data to the artifact store.
	// key should be in format "runs/{runID}/{filename}"
	Upload(ctx context.Context, key string, reader io.Reader, contentType string, metadata map[string]string) (*Artifact, error)

	// Download retrieves an artifact by key.
	Download(ctx context.Context, key string) (io.ReadCloser, error)

	// GetPresignedURL generates a presigned URL for downloading an artifact.
	GetPresignedURL(ctx context.Context, key string, expiry time.Duration) (string, error)

	// List lists all artifacts with the given prefix.
	// prefix should be "runs/{runID}/" to list all artifacts for a run.
	List(ctx context.Context, prefix string) ([]*Artifact, error)

	// Delete removes an artifact by key.
	Delete(ctx context.Context, key string) error

	// DeletePrefix removes all artifacts with the given prefix.
	// Useful for cleaning up all artifacts for a run.
	DeletePrefix(ctx context.Context, prefix string) error

	// EnsureBucket ensures the bucket exists, creating it if necessary.
	EnsureBucket(ctx context.Context) error
}

// RunArtifactPrefix returns the S3 prefix for a run's artifacts.
func RunArtifactPrefix(runID string) string {
	return "runs/" + runID + "/"
}

// RunArtifactKey returns the full S3 key for an artifact.
func RunArtifactKey(runID, filename string) string {
	return RunArtifactPrefix(runID) + filename
}
