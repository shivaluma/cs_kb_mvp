package main

import (
	"context"
	"net/http"
	"os"
	"time"

	"cs-kb-api/internal/config"
	apihttp "cs-kb-api/internal/http"
	"cs-kb-api/internal/logging"
	"cs-kb-api/internal/service"
)

func main() {
	cfg := config.Load()
	logger := logging.New("cs-kb-api", cfg.LogLevel)
	logger.Info("starting cs-kb-api",
		"addr", cfg.APIAddr,
		"database_configured", cfg.DatabaseURL != "",
		"database_connect_timeout_seconds", int(cfg.DatabaseConnectTimeout.Seconds()),
		"meili_host", cfg.MeiliHost,
		"ai_base_url", cfg.AIBaseURL,
		"seed_demo_sops", cfg.SeedDemoSOPs,
		"log_level", cfg.LogLevel,
	)

	ctx, cancel := context.WithTimeout(context.Background(), cfg.DatabaseConnectTimeout+2*time.Second)
	defer cancel()

	store, err := service.NewStore(ctx, cfg, logger)
	if err != nil {
		logger.Error("store init failed", "error", err)
		os.Exit(1)
	}
	defer store.Close()
	handler := apihttp.NewHandler(store, cfg, logger)

	server := &http.Server{
		Addr:              cfg.APIAddr,
		Handler:           handler.Routes(),
		ReadHeaderTimeout: 5 * time.Second,
	}

	logger.Info("cs-kb-api listening", "addr", cfg.APIAddr)
	if err := server.ListenAndServe(); err != nil && err != http.ErrServerClosed {
		logger.Error("server failed", "error", err)
		os.Exit(1)
	}
}
