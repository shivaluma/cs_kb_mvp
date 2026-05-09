package main

import (
	"log"
	"net/http"
	"time"

	"cs-kb-api/internal/config"
	apihttp "cs-kb-api/internal/http"
	"cs-kb-api/internal/service"
)

func main() {
	cfg := config.Load()
	store := service.NewMemoryStore()
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
