package qlog

import (
	"context"
	"fmt"
	"io"
	"log/slog"
	"os"
	"strings"
	"unicode/utf8"
)

const (
	// ANSI color codes
	colorReset  = "\033[0m"
	colorRed    = "\033[31m"
	colorYellow = "\033[33m"
	colorCyan   = "\033[36m"
	colorGray   = "\033[90m"
)

// Logger wraps slog.Logger with convenience methods
type Logger struct {
	*slog.Logger
}

// isUnicodeSupported checks if the terminal supports unicode
func isUnicodeSupported() bool {
	// Check TERM environment variable
	term := os.Getenv("TERM")
	if term == "dumb" {
		return false
	}

	// Check for NO_COLOR or other unicode-unfriendly environments
	if os.Getenv("NO_COLOR") != "" {
		return false
	}

	// Test if we can properly measure a unicode character
	return utf8.RuneCountInString("✓") == 1
}

// shouldUseColor checks if ANSI colors should be used
func shouldUseColor() bool {
	// Respect NO_COLOR environment variable
	if os.Getenv("NO_COLOR") != "" {
		return false
	}

	// Check if TERM is set (usually means a capable terminal)
	term := os.Getenv("TERM")
	if term == "" || term == "dumb" {
		return false
	}

	return true
}

// simpleHandler formats logs in a clean, CLI-friendly way following consola's approach:
// - Unicode symbols with ASCII fallbacks
// - ANSI colors with graceful degradation
type simpleHandler struct {
	level      slog.Level
	output     io.Writer
	useColor   bool
	useUnicode bool
}

func (h *simpleHandler) Enabled(_ context.Context, level slog.Level) bool {
	return level >= h.level
}

func (h *simpleHandler) Handle(_ context.Context, r slog.Record) error {
	var b strings.Builder

	// Select symbol and color based on level
	var symbol string
	var color string

	if h.useUnicode {
		switch r.Level {
		case slog.LevelDebug:
			symbol = "⚙"
			color = colorGray
		case slog.LevelInfo:
			symbol = "ℹ"
			color = colorCyan
		case slog.LevelWarn:
			symbol = "⚠"
			color = colorYellow
		case slog.LevelError:
			symbol = "✖"
			color = colorRed
		default:
			symbol = " "
		}
	} else {
		// ASCII fallbacks (consola-style)
		switch r.Level {
		case slog.LevelDebug:
			symbol = "D"
			color = colorGray
		case slog.LevelInfo:
			symbol = "i"
			color = colorCyan
		case slog.LevelWarn:
			symbol = "‼"
			color = colorYellow
		case slog.LevelError:
			symbol = "×"
			color = colorRed
		default:
			symbol = " "
		}
	}

	// Apply color if enabled
	if h.useColor && color != "" {
		b.WriteString(color)
		b.WriteString(symbol)
		b.WriteString(colorReset)
	} else {
		b.WriteString(symbol)
	}

	b.WriteString("  ")
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
		level:      level,
		output:     output,
		useColor:   shouldUseColor(),
		useUnicode: isUnicodeSupported(),
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
