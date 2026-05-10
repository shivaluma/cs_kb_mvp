package main

import (
	"context"
	"log"
	"net/http"
	"time"

	"cs-kb-api/internal/config"
	apihttp "cs-kb-api/internal/http"
	"cs-kb-api/internal/service"
)

func main() {
	cfg := config.Load()
	ctx, cancel := context.WithTimeout(context.Background(), cfg.DatabaseConnectTimeout+2*time.Second)
	defer cancel()

	store, err := service.NewStore(ctx, cfg)
	if err != nil {
		log.Fatalf("store init failed: %v", err)
	}
	defer store.Close()
	handler := apihttp.NewHandler(store, cfg)

	server := &http.Server{
		Addr:              cfg.APIAddr,
		Handler:           handler.Routes(),
		ReadHeaderTimeout: 5 * time.Second,
	}

	log.Printf("cs-kb-api listening on %s", cfg.APIAddr)
	if err := server.ListenAndServe(); err != nil && err != http.ErrServerClosed {
		log.Fatalf("server failed: %v", err)
	}
}
