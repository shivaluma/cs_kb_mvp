package config

import "os"

type Config struct {
	APIAddr        string
	DatabaseURL    string
	MeiliHost      string
	MeiliMasterKey string
	AIBaseURL      string
}

func Load() Config {
	return Config{
		APIAddr:        getEnv("API_ADDR", ":8080"),
		DatabaseURL:    getEnv("DATABASE_URL", ""),
		MeiliHost:      getEnv("MEILI_HOST", "http://localhost:7700"),
		MeiliMasterKey: getEnv("MEILI_MASTER_KEY", "dev_master_key"),
		AIBaseURL:      getEnv("AI_BASE_URL", "http://localhost:8090"),
	}
}

func getEnv(key string, fallback string) string {
	if value := os.Getenv(key); value != "" {
		return value
	}
	return fallback
}
