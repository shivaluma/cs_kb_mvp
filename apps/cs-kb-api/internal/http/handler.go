package http

import (
	"bytes"
	"encoding/json"
	"io"
	"net/http"
	"strings"
	"time"

	"cs-kb-api/internal/config"
	"cs-kb-api/internal/model"
	"cs-kb-api/internal/service"
)

type Handler struct {
	store *service.MemoryStore
	cfg   config.Config
}

func NewHandler(store *service.MemoryStore, cfg config.Config) *Handler {
	return &Handler{store: store, cfg: cfg}
}

func (h *Handler) Routes() http.Handler {
	mux := http.NewServeMux()

	mux.HandleFunc("GET /healthz", h.health)
	mux.HandleFunc("GET /api/v1/sops", h.listSOPs)
	mux.HandleFunc("GET /api/v1/sops/{id}", h.getSOP)
	mux.HandleFunc("GET /api/v1/homepage", h.homepage)
	mux.HandleFunc("POST /api/v1/search", h.search)
	mux.HandleFunc("GET /api/v1/search/taxonomy/intents", h.proxyAI("/ai/v1/search/taxonomy/intents"))
	mux.HandleFunc("GET /api/v1/search/synonyms", h.proxyAI("/ai/v1/search/synonyms"))
	mux.HandleFunc("POST /api/v1/search/synonyms", h.proxyAI("/ai/v1/search/synonyms"))
	mux.HandleFunc("GET /api/v1/search/synonyms/active", h.proxyAI("/ai/v1/search/synonyms/active"))
	mux.HandleFunc("POST /api/v1/search/synonyms/{id}/submit-review", h.proxyAISynonymAction("submit-review"))
	mux.HandleFunc("POST /api/v1/search/synonyms/{id}/approve", h.proxyAISynonymAction("approve"))
	mux.HandleFunc("POST /api/v1/search/synonyms/{id}/archive", h.proxyAISynonymAction("archive"))
	mux.HandleFunc("POST /api/v1/search/synonyms/sync", h.syncMeilisearchSynonyms)
	mux.HandleFunc("GET /api/v1/search/synonym-suggestions", h.proxyAI("/ai/v1/search/synonym-suggestions"))
	mux.HandleFunc("POST /api/v1/search/synonym-suggestions/generate", h.proxyAI("/ai/v1/search/synonym-suggestions/generate"))
	mux.HandleFunc("POST /api/v1/search/synonym-suggestions/{id}/accept", h.proxyAISynonymSuggestionAccept)
	mux.HandleFunc("POST /api/v1/ai/suggest", h.aiSuggest)
	mux.HandleFunc("GET /api/v1/ai/documents", h.proxyAI("/ai/v1/documents"))
	mux.HandleFunc("POST /api/v1/ai/documents/upload", h.proxyAI("/ai/v1/documents/upload"))
	mux.HandleFunc("GET /api/v1/ai/documents/{id}/versions", h.proxyAIDocumentVersions)
	mux.HandleFunc("POST /api/v1/ai/documents/{id}/archive", h.proxyAIDocumentArchive)
	mux.HandleFunc("POST /api/v1/ai/versions/{id}/publish", h.proxyAIVersionPublish)
	mux.HandleFunc("POST /api/v1/ai/retrieve", h.proxyAI("/ai/v1/retrieve"))

	return cors(mux)
}

func (h *Handler) health(w http.ResponseWriter, r *http.Request) {
	writeJSON(w, http.StatusOK, map[string]string{
		"status":  "ok",
		"service": "cs-kb-api",
	})
}

func (h *Handler) listSOPs(w http.ResponseWriter, r *http.Request) {
	writeJSON(w, http.StatusOK, map[string]any{"items": h.store.ListSOPs()})
}

func (h *Handler) getSOP(w http.ResponseWriter, r *http.Request) {
	sop, ok := h.store.GetSOP(r.PathValue("id"))
	if !ok {
		writeJSON(w, http.StatusNotFound, map[string]string{"error": "sop_not_found"})
		return
	}
	writeJSON(w, http.StatusOK, sop)
}

func (h *Handler) homepage(w http.ResponseWriter, r *http.Request) {
	writeJSON(w, http.StatusOK, map[string]any{
		"recently_updated": h.store.RecentlyUpdated(5),
		"most_viewed":      h.store.Popular(5),
		"category_shortcuts": []map[string]string{
			{"key": "case_handling", "label": "Case handling"},
			{"key": "verification", "label": "Verification"},
			{"key": "escalation", "label": "Escalation"},
			{"key": "policy", "label": "Policy"},
		},
	})
}

func (h *Handler) search(w http.ResponseWriter, r *http.Request) {
	start := time.Now()

	var req model.SearchRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		writeJSON(w, http.StatusBadRequest, map[string]string{"error": "invalid_json"})
		return
	}

	results := h.store.Search(req)
	modes := []string{"keyword", "filters"}
	if req.IncludeSemantic {
		modes = append(modes, "semantic_contract")
	}

	writeJSON(w, http.StatusOK, model.SearchResponse{
		Query:       req.Query,
		Results:     results,
		Total:       len(results),
		LatencyMS:   time.Since(start).Milliseconds(),
		UsedModes:   modes,
		Suggestions: suggestions(req.Query, len(results)),
	})
}

func (h *Handler) aiSuggest(w http.ResponseWriter, r *http.Request) {
	var req model.AISuggestRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		writeJSON(w, http.StatusBadRequest, map[string]string{"error": "invalid_json"})
		return
	}

	searchResults := h.store.Search(model.SearchRequest{Query: req.Query})
	if len(searchResults) == 0 {
		writeJSON(w, http.StatusOK, model.AISuggestResponse{
			Answer:   "Khong tim thay SOP published du tin cay de tra loi. Vui long thu query khac hoac escalate Lead.",
			Warnings: []string{"no_reliable_source"},
		})
		return
	}

	top := searchResults[0]
	sop, _ := h.store.GetSOP(top.SOPID)
	writeJSON(w, http.StatusOK, model.AISuggestResponse{
		Answer: "Nen tham chieu SOP \"" + sop.Title + "\" va lam theo checklist published moi nhat. Khong cam ket refund/compensation ngoai noi dung SOP.",
		SuggestedSOPs: []model.AISuggestedSOP{
			{
				SOPID:      sop.ID,
				Title:      sop.Title,
				Version:    sop.CurrentVersion.VersionNumber,
				Confidence: top.Confidence,
			},
		},
		Citations: []model.Citation{
			{
				SOPID:     sop.ID,
				VersionID: sop.CurrentVersion.ID,
				Section:   "handling_checklist",
			},
		},
	})
}

func (h *Handler) proxyAIDocumentVersions(w http.ResponseWriter, r *http.Request) {
	h.proxyAI("/ai/v1/documents/"+r.PathValue("id")+"/versions")(w, r)
}

func (h *Handler) proxyAIDocumentArchive(w http.ResponseWriter, r *http.Request) {
	h.proxyAI("/ai/v1/documents/"+r.PathValue("id")+"/archive")(w, r)
}

func (h *Handler) proxyAIVersionPublish(w http.ResponseWriter, r *http.Request) {
	h.proxyAI("/ai/v1/versions/"+r.PathValue("id")+"/publish")(w, r)
}

func (h *Handler) proxyAISynonymAction(action string) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		h.proxyAI("/ai/v1/search/synonyms/" + r.PathValue("id") + "/" + action)(w, r)
	}
}

func (h *Handler) proxyAISynonymSuggestionAccept(w http.ResponseWriter, r *http.Request) {
	h.proxyAI("/ai/v1/search/synonym-suggestions/"+r.PathValue("id")+"/accept")(w, r)
}

func (h *Handler) syncMeilisearchSynonyms(w http.ResponseWriter, r *http.Request) {
	payloadURL := strings.TrimRight(h.cfg.AIBaseURL, "/") + "/ai/v1/search/synonyms/meilisearch"
	client := &http.Client{Timeout: 30 * time.Second}
	resp, err := client.Get(payloadURL)
	if err != nil {
		writeJSON(w, http.StatusBadGateway, map[string]string{"error": "ai_service_unavailable"})
		return
	}
	defer resp.Body.Close()
	if resp.StatusCode >= 300 {
		w.WriteHeader(resp.StatusCode)
		_, _ = io.Copy(w, resp.Body)
		return
	}

	body, err := io.ReadAll(resp.Body)
	if err != nil {
		writeJSON(w, http.StatusInternalServerError, map[string]string{"error": "synonym_payload_read_failed"})
		return
	}

	indexes := []string{"sops", "ai_documents"}
	results := make([]map[string]any, 0, len(indexes))
	for _, index := range indexes {
		target := strings.TrimRight(h.cfg.MeiliHost, "/") + "/indexes/" + index + "/settings/synonyms"
		req, err := http.NewRequestWithContext(r.Context(), http.MethodPut, target, bytes.NewReader(body))
		if err != nil {
			writeJSON(w, http.StatusInternalServerError, map[string]string{"error": "meili_request_failed"})
			return
		}
		req.Header.Set("Content-Type", "application/json")
		if h.cfg.MeiliMasterKey != "" {
			req.Header.Set("Authorization", "Bearer "+h.cfg.MeiliMasterKey)
		}

		meiliResp, err := client.Do(req)
		if err != nil {
			writeJSON(w, http.StatusBadGateway, map[string]string{"error": "meilisearch_unavailable"})
			return
		}
		responseBody, _ := io.ReadAll(meiliResp.Body)
		meiliResp.Body.Close()

		var decoded any
		if len(responseBody) > 0 {
			_ = json.Unmarshal(responseBody, &decoded)
		}
		results = append(results, map[string]any{
			"index":       index,
			"status_code": meiliResp.StatusCode,
			"response":    decoded,
		})
	}

	var synonyms map[string][]string
	_ = json.Unmarshal(body, &synonyms)
	writeJSON(w, http.StatusOK, map[string]any{
		"synonym_count": len(synonyms),
		"indexes":       results,
	})
}

func (h *Handler) proxyAI(path string) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		target := strings.TrimRight(h.cfg.AIBaseURL, "/") + path
		if r.URL.RawQuery != "" {
			target += "?" + r.URL.RawQuery
		}

		req, err := http.NewRequestWithContext(r.Context(), r.Method, target, r.Body)
		if err != nil {
			writeJSON(w, http.StatusInternalServerError, map[string]string{"error": "ai_proxy_request_failed"})
			return
		}
		req.Header = r.Header.Clone()
		req.Header.Del("Host")

		client := &http.Client{Timeout: 30 * time.Second}
		resp, err := client.Do(req)
		if err != nil {
			writeJSON(w, http.StatusBadGateway, map[string]string{"error": "ai_service_unavailable"})
			return
		}
		defer resp.Body.Close()

		for key, values := range resp.Header {
			if strings.EqualFold(key, "Content-Length") {
				continue
			}
			for _, value := range values {
				w.Header().Add(key, value)
			}
		}
		w.WriteHeader(resp.StatusCode)
		_, _ = io.Copy(w, resp.Body)
	}
}

func suggestions(query string, resultCount int) []string {
	if resultCount > 0 {
		return nil
	}
	if query == "" {
		return []string{"missing item", "double charge", "safety incident"}
	}
	return []string{"thu tag khac", "kiem tra case reason", "escalate CS Lead neu khong co SOP"}
}

func writeJSON(w http.ResponseWriter, status int, payload any) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	_ = json.NewEncoder(w).Encode(payload)
}

func cors(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Access-Control-Allow-Origin", "*")
		w.Header().Set("Access-Control-Allow-Headers", "Content-Type, Authorization")
		w.Header().Set("Access-Control-Allow-Methods", "GET, POST, PUT, PATCH, DELETE, OPTIONS")
		if r.Method == http.MethodOptions {
			w.WriteHeader(http.StatusNoContent)
			return
		}
		next.ServeHTTP(w, r)
	})
}
