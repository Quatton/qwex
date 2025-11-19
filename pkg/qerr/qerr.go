package qerr

import "fmt"

// Code represents a stable error category that callers can switch on.
type Code string

const (
	CodeUnknown       Code = "unknown"
	CodeUnauthorized  Code = "unauthorized"
	CodeExpiredToken  Code = "expired_token"
	CodeRefreshFailed Code = "refresh_failed"
)

// Error is a simple value type that carries a Code plus the underlying error.
type Error struct {
	Code Code
	err  error
}

func (e *Error) Error() string {
	if e == nil {
		return "<nil>"
	}
	if e.err == nil {
		return string(e.Code)
	}
	return fmt.Sprintf("%s: %v", e.Code, e.err)
}

func (e *Error) Unwrap() error {
	if e == nil {
		return nil
	}
	return e.err
}

// New wraps an error with the provided code. If err is nil a nil is returned.
func New(code Code, err error) error {
	if err == nil {
		return nil
	}
	return &Error{Code: code, err: err}
}

// IsCode helps callers compare codes without type assertions.
func IsCode(err error, code Code) bool {
	if err == nil {
		return false
	}
	if e, ok := err.(*Error); ok {
		return e.Code == code
	}
	return false
}
