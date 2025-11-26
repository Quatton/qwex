package qart

import (
	"context"
	"io"
	"time"

	"github.com/minio/minio-go/v7"
	"github.com/minio/minio-go/v7/pkg/credentials"
)

// S3Store implements Store using MinIO/S3-compatible storage.
type S3Store struct {
	client *minio.Client
	bucket string
	region string
}

// S3Config holds configuration for S3-compatible storage.
type S3Config struct {
	Endpoint  string // host:port (e.g., "localhost:9000")
	AccessKey string
	SecretKey string
	Bucket    string
	Region    string
	UseSSL    bool
}

// NewS3Store creates a new S3Store with the given configuration.
func NewS3Store(cfg S3Config) (*S3Store, error) {
	client, err := minio.New(cfg.Endpoint, &minio.Options{
		Creds:  credentials.NewStaticV4(cfg.AccessKey, cfg.SecretKey, ""),
		Secure: cfg.UseSSL,
		Region: cfg.Region,
	})
	if err != nil {
		return nil, err
	}

	return &S3Store{
		client: client,
		bucket: cfg.Bucket,
		region: cfg.Region,
	}, nil
}

// EnsureBucket ensures the bucket exists, creating it if necessary.
func (s *S3Store) EnsureBucket(ctx context.Context) error {
	exists, err := s.client.BucketExists(ctx, s.bucket)
	if err != nil {
		return err
	}
	if exists {
		return nil
	}

	return s.client.MakeBucket(ctx, s.bucket, minio.MakeBucketOptions{
		Region: s.region,
	})
}

// Upload uploads data to the artifact store.
func (s *S3Store) Upload(ctx context.Context, key string, reader io.Reader, contentType string, metadata map[string]string) (*Artifact, error) {
	opts := minio.PutObjectOptions{
		ContentType:  contentType,
		UserMetadata: metadata,
	}

	info, err := s.client.PutObject(ctx, s.bucket, key, reader, -1, opts)
	if err != nil {
		return nil, err
	}

	return &Artifact{
		Key:          info.Key,
		Bucket:       info.Bucket,
		Size:         info.Size,
		ContentType:  contentType,
		LastModified: time.Now(),
		Metadata:     metadata,
	}, nil
}

// Download retrieves an artifact by key.
func (s *S3Store) Download(ctx context.Context, key string) (io.ReadCloser, error) {
	obj, err := s.client.GetObject(ctx, s.bucket, key, minio.GetObjectOptions{})
	if err != nil {
		return nil, err
	}

	// Check if object exists by getting stat
	_, err = obj.Stat()
	if err != nil {
		obj.Close()
		errResp := minio.ToErrorResponse(err)
		if errResp.Code == "NoSuchKey" {
			return nil, ErrNotFound
		}
		return nil, err
	}

	return obj, nil
}

// GetPresignedURL generates a presigned URL for downloading an artifact.
func (s *S3Store) GetPresignedURL(ctx context.Context, key string, expiry time.Duration) (string, error) {
	url, err := s.client.PresignedGetObject(ctx, s.bucket, key, expiry, nil)
	if err != nil {
		return "", err
	}
	return url.String(), nil
}

// List lists all artifacts with the given prefix.
func (s *S3Store) List(ctx context.Context, prefix string) ([]*Artifact, error) {
	var artifacts []*Artifact

	opts := minio.ListObjectsOptions{
		Prefix:    prefix,
		Recursive: true,
	}

	for obj := range s.client.ListObjects(ctx, s.bucket, opts) {
		if obj.Err != nil {
			return nil, obj.Err
		}

		artifacts = append(artifacts, &Artifact{
			Key:          obj.Key,
			Bucket:       s.bucket,
			Size:         obj.Size,
			ContentType:  obj.ContentType,
			LastModified: obj.LastModified,
		})
	}

	return artifacts, nil
}

// Delete removes an artifact by key.
func (s *S3Store) Delete(ctx context.Context, key string) error {
	return s.client.RemoveObject(ctx, s.bucket, key, minio.RemoveObjectOptions{})
}

// DeletePrefix removes all artifacts with the given prefix.
func (s *S3Store) DeletePrefix(ctx context.Context, prefix string) error {
	opts := minio.ListObjectsOptions{
		Prefix:    prefix,
		Recursive: true,
	}

	// Collect all objects to delete
	objectsCh := make(chan minio.ObjectInfo)
	go func() {
		defer close(objectsCh)
		for obj := range s.client.ListObjects(ctx, s.bucket, opts) {
			if obj.Err != nil {
				return
			}
			objectsCh <- obj
		}
	}()

	// Delete objects
	for obj := range objectsCh {
		err := s.client.RemoveObject(ctx, s.bucket, obj.Key, minio.RemoveObjectOptions{})
		if err != nil {
			return err
		}
	}

	return nil
}

// Ensure S3Store implements Store.
var _ Store = (*S3Store)(nil)
