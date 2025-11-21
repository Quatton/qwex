package qlog

import (
	"context"
	"fmt"
	"io"
	"log/slog"
	"os"
	"strings"
)

// Logger wraps slog.Logger with convenience methods
type Logger struct {
	*slog.Logger
}

// simpleHandler formats logs in a clean, CLI-friendly way
type simpleHandler struct {
	level  slog.Level
	output io.Writer
}

func (h *simpleHandler) Enabled(_ context.Context, level slog.Level) bool {
	return level >= h.level
}

func (h *simpleHandler) Handle(_ context.Context, r slog.Record) error {
	// Format: [LEVEL] message key=value key=value
	var b strings.Builder
	
	// Level prefix with emoji
	switch r.Level {
	case slog.LevelDebug:
		b.WriteString("🔍 ")
	case slog.LevelInfo:
		b.WriteString("ℹ️  ")
	case slog.LevelWarn:
		b.WriteString("⚠️  ")
	case slog.LevelError:
		b.WriteString("❌ ")
	}
	
	// Message
	b.WriteString(r.Message)
	
	// Attributes
	if r.NumAttrs() > 0 {
		first := true
		r.Attrs(func(a slog.Attr) bool {
			if first {
				b.WriteString(" ")
				first = false
			} else {
				b.WriteString(", ")
			}
			b.WriteString(a.Key)
			b.WriteString("=")
			b.WriteString(a.Value.String())
			return true
		})
	}
	
	b.WriteString("\n")
	_, err := h.output.Write([]byte(b.String()))
	return err
}

func (h *simpleHandler) WithAttrs(attrs []slog.Attr) slog.Handler {
	// For simplicity, we don't support persistent attrs in this handler
	return h
}

func (h *simpleHandler) WithGroup(name string) slog.Handler {
	// For simplicity, we don't support groups in this handler
	return h
}

// NewLogger creates a new logger with the specified level and output
func NewLogger(level slog.Level, output io.Writer) *Logger {
	if output == nil {
		output = os.Stdout
	}

	handler := &simpleHandler{
		level:  level,
		output: output,
	}

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

// Fatalf formats and logs at ERROR level, then exits with code 1
func (l *Logger) Fatalf(format string, args ...any) {
	l.Error(fmt.Sprintf(format, args...))
	os.Exit(1)
}

