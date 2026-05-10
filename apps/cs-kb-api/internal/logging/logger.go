package logging

import (
	"context"
	"crypto/rand"
	"encoding/hex"
	"io"
	"log/slog"
	"net/http"
	"os"
	"runtime/debug"
	"strings"
	"time"
)

type contextKey string

const requestIDKey contextKey = "request_id"

func New(service string, level string) *slog.Logger {
	handlerOptions := &slog.HandlerOptions{Level: parseLevel(level)}
	logger := slog.New(slog.NewJSONHandler(os.Stdout, handlerOptions)).With("service", service)
	slog.SetDefault(logger)
	return logger
}

func RequestID(ctx context.Context) string {
	if value, ok := ctx.Value(requestIDKey).(string); ok {
		return value
	}
	return ""
}

func WithRequestID(ctx context.Context, requestID string) context.Context {
	return context.WithValue(ctx, requestIDKey, requestID)
}

func Middleware(logger *slog.Logger, next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		start := time.Now()
		requestID := requestIDFromRequest(r)
		ctx := WithRequestID(r.Context(), requestID)
		r = r.WithContext(ctx)

		recorder := &responseRecorder{ResponseWriter: w, status: http.StatusOK}
		recorder.Header().Set("X-Request-Id", requestID)

		defer func() {
			if recovered := recover(); recovered != nil {
				logger.ErrorContext(ctx, "http request panic",
					"request_id", requestID,
					"method", r.Method,
					"path", r.URL.Path,
					"error", recovered,
					"stack", string(debug.Stack()),
				)
				http.Error(recorder, http.StatusText(http.StatusInternalServerError), http.StatusInternalServerError)
			}

			duration := time.Since(start)
			attrs := []any{
				"request_id", requestID,
				"method", r.Method,
				"path", r.URL.Path,
				"query", r.URL.RawQuery,
				"status", recorder.status,
				"bytes", recorder.bytes,
				"duration_ms", duration.Milliseconds(),
				"remote_addr", r.RemoteAddr,
				"user_agent", r.UserAgent(),
			}
			if recorder.status >= 500 {
				logger.ErrorContext(ctx, "http request completed", attrs...)
			} else if recorder.status >= 400 {
				logger.WarnContext(ctx, "http request completed", attrs...)
			} else {
				logger.InfoContext(ctx, "http request completed", attrs...)
			}
		}()

		next.ServeHTTP(recorder, r)
	})
}

type responseRecorder struct {
	http.ResponseWriter
	status int
	bytes  int
}

func (r *responseRecorder) WriteHeader(status int) {
	r.status = status
	r.ResponseWriter.WriteHeader(status)
}

func (r *responseRecorder) Write(data []byte) (int, error) {
	written, err := r.ResponseWriter.Write(data)
	r.bytes += written
	return written, err
}

func (r *responseRecorder) Flush() {
	if flusher, ok := r.ResponseWriter.(http.Flusher); ok {
		flusher.Flush()
	}
}

func requestIDFromRequest(r *http.Request) string {
	for _, header := range []string{"X-Request-Id", "X-Correlation-Id", "Cf-Ray"} {
		value := strings.TrimSpace(r.Header.Get(header))
		if value != "" {
			return value
		}
	}
	var bytes [12]byte
	if _, err := io.ReadFull(rand.Reader, bytes[:]); err != nil {
		return hex.EncodeToString([]byte(time.Now().Format(time.RFC3339Nano)))
	}
	return hex.EncodeToString(bytes[:])
}

func parseLevel(value string) slog.Level {
	switch strings.ToLower(strings.TrimSpace(value)) {
	case "debug":
		return slog.LevelDebug
	case "warn", "warning":
		return slog.LevelWarn
	case "error":
		return slog.LevelError
	default:
		return slog.LevelInfo
	}
}
