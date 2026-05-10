package config

import (
	"os"
	"strconv"
	"time"
)

type Config struct {
	APIAddr                string
	DatabaseURL            string
	DatabaseConnectTimeout time.Duration
	LogLevel               string
	MeiliHost              string
	MeiliMasterKey         string
	AIBaseURL              string
	SeedDemoSOPs           bool
}

func Load() Config {
	return Config{
		APIAddr:                getEnv("API_ADDR", ":8080"),
		DatabaseURL:            getEnv("DATABASE_URL", ""),
		DatabaseConnectTimeout: getEnvDurationSeconds("DATABASE_CONNECT_TIMEOUT_SECONDS", 5*time.Second),
		LogLevel:               getEnv("LOG_LEVEL", "info"),
		MeiliHost:              getEnv("MEILI_HOST", "http://localhost:7700"),
		MeiliMasterKey:         getEnv("MEILI_MASTER_KEY", "dev_master_key"),
		AIBaseURL:              getEnv("AI_BASE_URL", "http://localhost:8090"),
		SeedDemoSOPs:           getEnv("SEED_DEMO_SOPS", "false") == "true",
	}
}

func getEnv(key string, fallback string) string {
	if value := os.Getenv(key); value != "" {
		return value
	}
	return fallback
}

func getEnvDurationSeconds(key string, fallback time.Duration) time.Duration {
	value := os.Getenv(key)
	if value == "" {
		return fallback
	}
	seconds, err := strconv.Atoi(value)
	if err != nil || seconds <= 0 {
		return fallback
	}
	return time.Duration(seconds) * time.Second
}
