package qart

import "errors"

// Common errors
var (
	ErrNotFound      = errors.New("artifact not found")
	ErrBucketMissing = errors.New("bucket does not exist")
)
