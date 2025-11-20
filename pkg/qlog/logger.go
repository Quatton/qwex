package qlog

import (
	"io"
	"log/slog"
	"os"
)

// Logger wraps slog.Logger with convenience methods
type Logger struct {
	*slog.Logger
}

// NewLogger creates a new logger with the specified level and output
func NewLogger(level slog.Level, output io.Writer) *Logger {
	if output == nil {
		output = os.Stdout
	}

	opts := &slog.HandlerOptions{
		Level: level,
	}

	handler := slog.NewTextHandler(output, opts)
	return &Logger{
		Logger: slog.New(handler),
	}
}

// NewDefault creates a logger with INFO level
func NewDefault() *Logger {
	return NewLogger(slog.LevelInfo, os.Stdout)
}

// NewQuiet creates a logger with WARN level (suppresses info/debug)
func NewQuiet() *Logger {
	return NewLogger(slog.LevelWarn, os.Stdout)
}

// NewVerbose creates a logger with DEBUG level
func NewVerbose() *Logger {
	return NewLogger(slog.LevelDebug, os.Stdout)
}

// Fatal logs at ERROR level and exits with code 1
func (l *Logger) Fatal(msg string, args ...any) {
	l.Error(msg, args...)
	os.Exit(1)
}
