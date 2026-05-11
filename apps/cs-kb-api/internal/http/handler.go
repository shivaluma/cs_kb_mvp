package http

import (
	"bytes"
	"context"
	"encoding/json"
	"io"
	"log/slog"
	"net/http"
	"strings"
	"time"

	"cs-kb-api/internal/config"
	"cs-kb-api/internal/logging"
	"cs-kb-api/internal/model"
	"cs-kb-api/internal/service"
)

type Handler struct {
	store  *service.Store
	cfg    config.Config
	logger *slog.Logger
}

func NewHandler(store *service.Store, cfg config.Config, logger *slog.Logger) *Handler {
	return &Handler{store: store, cfg: cfg, logger: logger}
}

func (h *Handler) Routes() http.Handler {
	mux := http.NewServeMux()

	mux.HandleFunc("GET /healthz", h.health)
	mux.HandleFunc("GET /api/v1/system/health", h.systemHealth)
	mux.HandleFunc("GET /api/v1/sops", h.listSOPs)
	mux.HandleFunc("POST /api/v1/sops", h.createSOP)
	mux.HandleFunc("GET /api/v1/sops/{id}", h.getSOP)
	mux.HandleFunc("POST /api/v1/sops/{id}/versions", h.createSOPVersion)
	mux.HandleFunc("POST /api/v1/sops/{id}/archive", h.archiveSOP)
	mux.HandleFunc("POST /api/v1/sop-versions/{id}/submit-review", h.submitSOPVersionReview)
	mux.HandleFunc("POST /api/v1/sop-versions/{id}/publish", h.publishSOPVersion)
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
	mux.HandleFunc("POST /api/v1/ai/documents/metadata-preview", h.proxyAIDocumentMetadataPreview)
	mux.HandleFunc("POST /api/v1/ai/documents/upload", h.proxyAIDocumentUpload)
	mux.HandleFunc("POST /api/v1/ai/documents/upload-async", h.proxyAIDocumentUploadAsync)
	mux.HandleFunc("GET /api/v1/ai/documents/{id}/versions", h.proxyAIDocumentVersions)
	mux.HandleFunc("GET /api/v1/ai/documents/{id}/chunks", h.proxyAIDocumentChunks)
	mux.HandleFunc("GET /api/v1/ai/documents/{id}/extraction-units", h.proxyAIDocumentExtractionUnits)
	mux.HandleFunc("PATCH /api/v1/ai/extraction-units/{id}", h.proxyAIExtractionUnitUpdate)
	mux.HandleFunc("POST /api/v1/ai/extraction-units/{id}", h.proxyAIExtractionUnitUpdate)
	mux.HandleFunc("POST /api/v1/ai/documents/{id}/archive", h.proxyAIDocumentArchive)
	mux.HandleFunc("POST /api/v1/ai/versions/{id}/publish", h.proxyAIVersionPublish)
	mux.HandleFunc("POST /api/v1/ai/versions/{id}/bulk-review", h.proxyAIVersionBulkReview)
	mux.HandleFunc("POST /api/v1/ai/versions/{id}/extraction-units", h.proxyAIVersionExtractionUnitCreate)
	mux.HandleFunc("GET /api/v1/ai/versions/{id}/extraction-pipeline", h.proxyAIVersionExtractionPipeline)
	mux.HandleFunc("GET /api/v1/ai/versions/{id}/raw", h.proxyAIVersionRaw)
	mux.HandleFunc("GET /api/v1/ai/versions/{id}/source/pages/{page}", h.proxyAIVersionSourcePage)
	mux.HandleFunc("POST /api/v1/ai/retrieve", h.proxyAI("/ai/v1/retrieve"))
	mux.HandleFunc("GET /api/v1/ai/chat/model-routes", h.proxyAI("/ai/v1/chat/model-routes"))
	mux.HandleFunc("POST /api/v1/ai/chat", h.proxyAIChat)

	return logging.Middleware(h.logger, cors(mux))
}

func (h *Handler) health(w http.ResponseWriter, r *http.Request) {
	writeJSON(w, http.StatusOK, map[string]string{
		"status":  "ok",
		"service": "cs-kb-api",
	})
}

type systemHealthResponse struct {
	Status    string               `json:"status"`
	CheckedAt string               `json:"checked_at"`
	Services  []model.HealthStatus `json:"services"`
}

func (h *Handler) systemHealth(w http.ResponseWriter, r *http.Request) {
	ctx, cancel := context.WithTimeout(r.Context(), 5*time.Second)
	defer cancel()

	services := []model.HealthStatus{
		{Name: "api", Status: "healthy", LatencyMS: 0, Detail: "Go API process is serving requests"},
		h.store.PostgresHealth(ctx),
		h.store.MeiliHealth(ctx),
	}
	services = append(services, h.aiHealth(ctx)...)

	status := "healthy"
	for _, service := range services {
		if service.Status == "down" {
			status = "down"
			break
		}
		if service.Status == "degraded" || service.Status == "unknown" {
			status = "degraded"
		}
	}
	writeJSON(w, http.StatusOK, systemHealthResponse{
		Status:    status,
		CheckedAt: time.Now().UTC().Format(time.RFC3339),
		Services:  services,
	})
}

func (h *Handler) aiHealth(ctx context.Context) []model.HealthStatus {
	target := strings.TrimRight(h.cfg.AIBaseURL, "/") + "/healthz"
	start := time.Now()
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, target, nil)
	if err != nil {
		return []model.HealthStatus{{Name: "ai_service", Status: "down", Detail: err.Error()}}
	}
	resp, err := (&http.Client{Timeout: 4 * time.Second}).Do(req)
	if err != nil {
		return []model.HealthStatus{{
			Name:      "ai_service",
			Status:    "down",
			LatencyMS: time.Since(start).Milliseconds(),
			Detail:    err.Error(),
		}}
	}
	defer resp.Body.Close()
	body, _ := io.ReadAll(resp.Body)
	latency := time.Since(start).Milliseconds()
	if resp.StatusCode >= 300 {
		return []model.HealthStatus{{
			Name:      "ai_service",
			Status:    "down",
			LatencyMS: latency,
			Detail:    "HTTP " + resp.Status + ": " + truncateLogBody(body),
		}}
	}

	var decoded struct {
		Status   string               `json:"status"`
		Services []model.HealthStatus `json:"services"`
	}
	if err := json.Unmarshal(body, &decoded); err != nil {
		return []model.HealthStatus{{
			Name:      "ai_service",
			Status:    "unknown",
			LatencyMS: latency,
			Detail:    "AI health response is not JSON",
		}}
	}
	if len(decoded.Services) == 0 {
		status := decoded.Status
		if status == "" || status == "ok" {
			status = "healthy"
		}
		return []model.HealthStatus{{Name: "ai_service", Status: status, LatencyMS: latency, Detail: "AI service health endpoint reachable"}}
	}
	for index := range decoded.Services {
		if decoded.Services[index].LatencyMS == 0 && decoded.Services[index].Name == "ai_service" {
			decoded.Services[index].LatencyMS = latency
		}
	}
	return decoded.Services
}

func (h *Handler) listSOPs(w http.ResponseWriter, r *http.Request) {
	sops, err := h.store.ListSOPs(r.Context())
	if err != nil {
		writeJSON(w, http.StatusInternalServerError, map[string]string{"error": "sops_query_failed"})
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"items": sops})
}

func (h *Handler) getSOP(w http.ResponseWriter, r *http.Request) {
	sop, ok, err := h.store.GetSOP(r.Context(), r.PathValue("id"))
	if err != nil {
		writeJSON(w, http.StatusInternalServerError, map[string]string{"error": "sop_query_failed"})
		return
	}
	if !ok {
		writeJSON(w, http.StatusNotFound, map[string]string{"error": "sop_not_found"})
		return
	}
	writeJSON(w, http.StatusOK, sop)
}

func (h *Handler) createSOP(w http.ResponseWriter, r *http.Request) {
	var sop model.SOP
	if err := json.NewDecoder(r.Body).Decode(&sop); err != nil {
		writeJSON(w, http.StatusBadRequest, map[string]string{"error": "invalid_json"})
		return
	}
	created, err := h.store.CreateSOP(r.Context(), sop)
	if err != nil {
		writeJSON(w, http.StatusInternalServerError, map[string]string{"error": "sop_create_failed"})
		return
	}
	writeJSON(w, http.StatusCreated, created)
}

func (h *Handler) createSOPVersion(w http.ResponseWriter, r *http.Request) {
	var version model.SOPVersion
	if err := json.NewDecoder(r.Body).Decode(&version); err != nil {
		writeJSON(w, http.StatusBadRequest, map[string]string{"error": "invalid_json"})
		return
	}
	created, err := h.store.CreateVersion(r.Context(), r.PathValue("id"), version)
	if err != nil {
		writeJSON(w, http.StatusInternalServerError, map[string]string{"error": "sop_version_create_failed"})
		return
	}
	writeJSON(w, http.StatusCreated, created)
}

func (h *Handler) submitSOPVersionReview(w http.ResponseWriter, r *http.Request) {
	updated, err := h.store.SetVersionStatus(r.Context(), r.PathValue("id"), "in_review", "cs-ops-ui")
	if err != nil {
		writeJSON(w, http.StatusInternalServerError, map[string]string{"error": "sop_version_submit_failed"})
		return
	}
	writeJSON(w, http.StatusOK, updated)
}

func (h *Handler) publishSOPVersion(w http.ResponseWriter, r *http.Request) {
	published, err := h.store.PublishVersion(r.Context(), r.PathValue("id"), "cs-lead-ui")
	if err != nil {
		writeJSON(w, http.StatusInternalServerError, map[string]string{"error": "sop_version_publish_failed"})
		return
	}
	writeJSON(w, http.StatusOK, published)
}

func (h *Handler) archiveSOP(w http.ResponseWriter, r *http.Request) {
	if err := h.store.ArchiveSOP(r.Context(), r.PathValue("id")); err != nil {
		writeJSON(w, http.StatusInternalServerError, map[string]string{"error": "sop_archive_failed"})
		return
	}
	writeJSON(w, http.StatusOK, map[string]string{"archived": "true", "sop_id": r.PathValue("id")})
}

func (h *Handler) homepage(w http.ResponseWriter, r *http.Request) {
	recent, err := h.store.RecentlyUpdated(r.Context(), 5)
	if err != nil {
		writeJSON(w, http.StatusInternalServerError, map[string]string{"error": "homepage_recent_failed"})
		return
	}
	if recent == nil {
		recent = []model.SOP{}
	}
	popular, err := h.store.Popular(r.Context(), 5)
	if err != nil {
		writeJSON(w, http.StatusInternalServerError, map[string]string{"error": "homepage_popular_failed"})
		return
	}
	if popular == nil {
		popular = []model.SOP{}
	}
	writeJSON(w, http.StatusOK, map[string]any{
		"recently_updated": recent,
		"most_viewed":      popular,
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

	results, modes, err := h.store.Search(r.Context(), req)
	if err != nil {
		writeJSON(w, http.StatusInternalServerError, map[string]string{"error": "search_failed"})
		return
	}
	semanticResults := []model.SemanticResult{}
	if req.IncludeSemantic {
		semanticResults, err = h.retrieveAI(r.Context(), req)
		if err == nil {
			modes = append(modes, "ai_hybrid_retrieval")
		} else {
			modes = append(modes, "ai_hybrid_unavailable")
		}
	}

	writeJSON(w, http.StatusOK, model.SearchResponse{
		Query:           req.Query,
		Results:         results,
		SemanticResults: semanticResults,
		Total:           len(results),
		LatencyMS:       time.Since(start).Milliseconds(),
		UsedModes:       modes,
		Suggestions:     suggestions(req.Query, len(results)+len(semanticResults)),
	})
}

func (h *Handler) aiSuggest(w http.ResponseWriter, r *http.Request) {
	var req model.AISuggestRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		writeJSON(w, http.StatusBadRequest, map[string]string{"error": "invalid_json"})
		return
	}

	searchResults, _, err := h.store.Search(r.Context(), model.SearchRequest{Query: req.Query})
	if err != nil {
		writeJSON(w, http.StatusInternalServerError, map[string]string{"error": "search_failed"})
		return
	}
	if len(searchResults) == 0 {
		writeJSON(w, http.StatusOK, model.AISuggestResponse{
			Answer:   "Khong tim thay SOP published du tin cay de tra loi. Vui long thu query khac hoac escalate Lead.",
			Warnings: []string{"no_reliable_source"},
		})
		return
	}

	top := searchResults[0]
	sop, ok, err := h.store.GetSOP(r.Context(), top.SOPID)
	if err != nil || !ok {
		writeJSON(w, http.StatusNotFound, map[string]string{"error": "sop_not_found"})
		return
	}
	writeJSON(w, http.StatusOK, model.AISuggestResponse{
		Answer: "Nen tham chieu SOP \"" + sop.Title + "\" va lam theo noi dung published moi nhat. Khong cam ket hanh dong ngoai noi dung SOP.",
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

func (h *Handler) proxyAIDocumentChunks(w http.ResponseWriter, r *http.Request) {
	h.proxyAI("/ai/v1/documents/"+r.PathValue("id")+"/chunks")(w, r)
}

func (h *Handler) proxyAIDocumentExtractionUnits(w http.ResponseWriter, r *http.Request) {
	h.proxyAI("/ai/v1/documents/"+r.PathValue("id")+"/extraction-units")(w, r)
}

func (h *Handler) proxyAIExtractionUnitUpdate(w http.ResponseWriter, r *http.Request) {
	h.proxyAIWithMethod("/ai/v1/extraction-units/"+r.PathValue("id"), http.MethodPatch, 30*time.Second)(w, r)
}

func (h *Handler) proxyAIVersionRaw(w http.ResponseWriter, r *http.Request) {
	h.proxyAI("/ai/v1/versions/"+r.PathValue("id")+"/raw")(w, r)
}

func (h *Handler) proxyAIVersionExtractionPipeline(w http.ResponseWriter, r *http.Request) {
	h.proxyAI("/ai/v1/versions/"+r.PathValue("id")+"/extraction-pipeline")(w, r)
}

func (h *Handler) proxyAIVersionSourcePage(w http.ResponseWriter, r *http.Request) {
	h.proxyAI("/ai/v1/versions/"+r.PathValue("id")+"/source/pages/"+r.PathValue("page"))(w, r)
}

func (h *Handler) proxyAIDocumentUpload(w http.ResponseWriter, r *http.Request) {
	h.proxyAIWithBody("/ai/v1/documents/upload", 120*time.Second, func(ctx context.Context, status int, body []byte) {
		if status < 200 || status >= 300 {
			return
		}
		var payload map[string]any
		if json.Unmarshal(body, &payload) == nil {
			if payload["status"] == "published" {
				_ = h.store.IndexAIDocument(ctx, payload)
			}
		}
	})(w, r)
}

func (h *Handler) proxyAIDocumentUploadAsync(w http.ResponseWriter, r *http.Request) {
	h.proxyAIWithBody("/ai/v1/documents/upload-async", 30*time.Second, nil)(w, r)
}

func (h *Handler) proxyAIDocumentMetadataPreview(w http.ResponseWriter, r *http.Request) {
	h.proxyAIWithBody("/ai/v1/documents/metadata-preview", 90*time.Second, nil)(w, r)
}

func (h *Handler) proxyAIDocumentArchive(w http.ResponseWriter, r *http.Request) {
	documentID := r.PathValue("id")
	h.proxyAIWithBody("/ai/v1/documents/"+documentID+"/archive", 30*time.Second, func(ctx context.Context, status int, _ []byte) {
		if status >= 200 && status < 300 {
			_ = h.store.DeleteAIDocumentFromMeili(ctx, documentID)
			_ = h.store.DeleteAIChunksFromMeili(ctx, documentID)
		}
	})(w, r)
}

func (h *Handler) proxyAIVersionPublish(w http.ResponseWriter, r *http.Request) {
	h.proxyAIWithBody("/ai/v1/versions/"+r.PathValue("id")+"/publish", 45*time.Second, func(ctx context.Context, status int, body []byte) {
		if status < 200 || status >= 300 {
			return
		}
		var payload map[string]any
		if json.Unmarshal(body, &payload) == nil {
			_ = h.store.IndexAIDocument(ctx, payload)
		}
	})(w, r)
}

func (h *Handler) proxyAIVersionBulkReview(w http.ResponseWriter, r *http.Request) {
	h.proxyAIWithBody("/ai/v1/versions/"+r.PathValue("id")+"/bulk-review", 45*time.Second, nil)(w, r)
}

func (h *Handler) proxyAIVersionExtractionUnitCreate(w http.ResponseWriter, r *http.Request) {
	h.proxyAIWithBody("/ai/v1/versions/"+r.PathValue("id")+"/extraction-units", 45*time.Second, nil)(w, r)
}

func (h *Handler) proxyAIChat(w http.ResponseWriter, r *http.Request) {
	h.proxyAIWithBody("/ai/v1/chat", 120*time.Second, nil)(w, r)
}

func (h *Handler) proxyAISynonymAction(action string) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		h.proxyAI("/ai/v1/search/synonyms/"+r.PathValue("id")+"/"+action)(w, r)
	}
}

func (h *Handler) proxyAISynonymSuggestionAccept(w http.ResponseWriter, r *http.Request) {
	h.proxyAI("/ai/v1/search/synonym-suggestions/"+r.PathValue("id")+"/accept")(w, r)
}

func (h *Handler) syncMeilisearchSynonyms(w http.ResponseWriter, r *http.Request) {
	payloadURL := strings.TrimRight(h.cfg.AIBaseURL, "/") + "/ai/v1/search/synonyms/meilisearch"
	client := &http.Client{Timeout: 30 * time.Second}
	start := time.Now()
	h.logger.InfoContext(r.Context(), "synonym sync payload fetch started", "target", payloadURL)
	resp, err := client.Get(payloadURL)
	if err != nil {
		h.logger.ErrorContext(r.Context(), "synonym sync payload fetch failed", "target", payloadURL, "duration_ms", time.Since(start).Milliseconds(), "error", err)
		writeJSON(w, http.StatusBadGateway, map[string]string{"error": "ai_service_unavailable"})
		return
	}
	defer resp.Body.Close()
	if resp.StatusCode >= 300 {
		h.logger.ErrorContext(r.Context(), "synonym sync payload fetch returned non-2xx", "target", payloadURL, "status", resp.StatusCode, "duration_ms", time.Since(start).Milliseconds())
		w.WriteHeader(resp.StatusCode)
		_, _ = io.Copy(w, resp.Body)
		return
	}

	body, err := io.ReadAll(resp.Body)
	if err != nil {
		writeJSON(w, http.StatusInternalServerError, map[string]string{"error": "synonym_payload_read_failed"})
		return
	}

	indexes := []string{"sops", "ai_documents", "ai_chunks"}
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
			h.logger.ErrorContext(r.Context(), "synonym sync meili update failed", "index", index, "target", target, "error", err)
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
	h.logger.InfoContext(r.Context(), "synonym sync completed", "synonym_count", len(synonyms), "duration_ms", time.Since(start).Milliseconds())
}

func (h *Handler) retrieveAI(ctx context.Context, req model.SearchRequest) ([]model.SemanticResult, error) {
	payload := map[string]any{
		"query": req.Query,
		"mode":  "hybrid",
		"limit": 6,
		"filters": map[string]any{
			"audience":     emptySlice(req.Filters.Audience),
			"vertical":     emptySlice(req.Filters.Vertical),
			"category":     emptySlice(req.Filters.Category),
			"tags":         emptySlice(req.Filters.Tags),
			"case_reasons": emptySlice(req.Filters.CaseReasons),
			"status":       []string{"published"},
		},
	}
	var decoded struct {
		Results []model.SemanticResult `json:"results"`
	}
	data, err := json.Marshal(payload)
	if err != nil {
		return nil, err
	}
	target := strings.TrimRight(h.cfg.AIBaseURL, "/") + "/ai/v1/retrieve"
	httpReq, err := http.NewRequestWithContext(ctx, http.MethodPost, target, bytes.NewReader(data))
	if err != nil {
		return nil, err
	}
	httpReq.Header.Set("Content-Type", "application/json")
	resp, err := (&http.Client{Timeout: 15 * time.Second}).Do(httpReq)
	if err != nil {
		h.logger.WarnContext(ctx, "AI retrieve unavailable", "target", target, "error", err)
		return nil, err
	}
	defer resp.Body.Close()
	if resp.StatusCode >= 300 {
		body, _ := io.ReadAll(resp.Body)
		h.logger.WarnContext(ctx, "AI retrieve returned non-2xx", "target", target, "status", resp.StatusCode, "body", truncateLogBody(body))
		return nil, http.ErrAbortHandler
	}
	if err := json.NewDecoder(resp.Body).Decode(&decoded); err != nil {
		return nil, err
	}
	return decoded.Results, nil
}

func (h *Handler) proxyAIWithBody(path string, timeout time.Duration, after func(context.Context, int, []byte)) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		start := time.Now()
		target := strings.TrimRight(h.cfg.AIBaseURL, "/") + path
		if r.URL.RawQuery != "" {
			target += "?" + r.URL.RawQuery
		}
		h.logger.InfoContext(r.Context(), "AI proxy request started",
			"request_id", logging.RequestID(r.Context()),
			"method", r.Method,
			"path", r.URL.Path,
			"target", target,
			"timeout_ms", timeout.Milliseconds(),
		)

		req, err := http.NewRequestWithContext(r.Context(), r.Method, target, r.Body)
		if err != nil {
			h.logger.ErrorContext(r.Context(), "AI proxy request build failed", "target", target, "error", err)
			writeJSON(w, http.StatusInternalServerError, map[string]string{"error": "ai_proxy_request_failed"})
			return
		}
		req.Header = r.Header.Clone()
		req.Header.Del("Host")

		resp, err := (&http.Client{Timeout: timeout}).Do(req)
		if err != nil {
			h.logger.ErrorContext(r.Context(), "AI proxy request failed", "target", target, "duration_ms", time.Since(start).Milliseconds(), "error", err)
			writeJSON(w, http.StatusBadGateway, map[string]string{"error": "ai_service_unavailable"})
			return
		}
		defer resp.Body.Close()

		body, err := io.ReadAll(resp.Body)
		if err != nil {
			h.logger.ErrorContext(r.Context(), "AI proxy response read failed", "target", target, "status", resp.StatusCode, "duration_ms", time.Since(start).Milliseconds(), "error", err)
			writeJSON(w, http.StatusBadGateway, map[string]string{"error": "ai_proxy_read_failed"})
			return
		}
		if after != nil {
			after(r.Context(), resp.StatusCode, body)
		}

		for key, values := range resp.Header {
			if strings.EqualFold(key, "Content-Length") {
				continue
			}
			for _, value := range values {
				w.Header().Add(key, value)
			}
		}
		w.WriteHeader(resp.StatusCode)
		_, _ = w.Write(body)
		h.logProxyCompletion(r.Context(), "AI proxy request completed", target, resp.StatusCode, time.Since(start), body)
	}
}

func (h *Handler) proxyAI(path string) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		start := time.Now()
		target := strings.TrimRight(h.cfg.AIBaseURL, "/") + path
		if r.URL.RawQuery != "" {
			target += "?" + r.URL.RawQuery
		}
		h.logger.InfoContext(r.Context(), "AI proxy request started",
			"request_id", logging.RequestID(r.Context()),
			"method", r.Method,
			"path", r.URL.Path,
			"target", target,
			"timeout_ms", int64(30*time.Second/time.Millisecond),
		)

		req, err := http.NewRequestWithContext(r.Context(), r.Method, target, r.Body)
		if err != nil {
			h.logger.ErrorContext(r.Context(), "AI proxy request build failed", "target", target, "error", err)
			writeJSON(w, http.StatusInternalServerError, map[string]string{"error": "ai_proxy_request_failed"})
			return
		}
		req.Header = r.Header.Clone()
		req.Header.Del("Host")

		client := &http.Client{Timeout: 30 * time.Second}
		resp, err := client.Do(req)
		if err != nil {
			h.logger.ErrorContext(r.Context(), "AI proxy request failed", "target", target, "duration_ms", time.Since(start).Milliseconds(), "error", err)
			writeJSON(w, http.StatusBadGateway, map[string]string{"error": "ai_service_unavailable"})
			return
		}
		defer resp.Body.Close()
		body, err := io.ReadAll(resp.Body)
		if err != nil {
			h.logger.ErrorContext(r.Context(), "AI proxy response read failed", "target", target, "status", resp.StatusCode, "duration_ms", time.Since(start).Milliseconds(), "error", err)
			writeJSON(w, http.StatusBadGateway, map[string]string{"error": "ai_proxy_read_failed"})
			return
		}

		for key, values := range resp.Header {
			if strings.EqualFold(key, "Content-Length") {
				continue
			}
			for _, value := range values {
				w.Header().Add(key, value)
			}
		}
		w.WriteHeader(resp.StatusCode)
		_, _ = w.Write(body)
		h.logProxyCompletion(r.Context(), "AI proxy request completed", target, resp.StatusCode, time.Since(start), body)
	}
}

func (h *Handler) proxyAIWithMethod(path string, method string, timeout time.Duration) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		start := time.Now()
		target := strings.TrimRight(h.cfg.AIBaseURL, "/") + path
		if r.URL.RawQuery != "" {
			target += "?" + r.URL.RawQuery
		}
		h.logger.InfoContext(r.Context(), "AI proxy request started",
			"request_id", logging.RequestID(r.Context()),
			"method", method,
			"original_method", r.Method,
			"path", r.URL.Path,
			"target", target,
			"timeout_ms", timeout.Milliseconds(),
		)

		req, err := http.NewRequestWithContext(r.Context(), method, target, r.Body)
		if err != nil {
			h.logger.ErrorContext(r.Context(), "AI proxy request build failed", "target", target, "method", method, "error", err)
			writeJSON(w, http.StatusInternalServerError, map[string]string{"error": "ai_proxy_request_failed"})
			return
		}
		req.Header = r.Header.Clone()
		req.Header.Del("Host")

		resp, err := (&http.Client{Timeout: timeout}).Do(req)
		if err != nil {
			h.logger.ErrorContext(r.Context(), "AI proxy request failed", "target", target, "method", method, "duration_ms", time.Since(start).Milliseconds(), "error", err)
			writeJSON(w, http.StatusBadGateway, map[string]string{"error": "ai_service_unavailable"})
			return
		}
		defer resp.Body.Close()
		body, err := io.ReadAll(resp.Body)
		if err != nil {
			h.logger.ErrorContext(r.Context(), "AI proxy response read failed", "target", target, "method", method, "status", resp.StatusCode, "duration_ms", time.Since(start).Milliseconds(), "error", err)
			writeJSON(w, http.StatusBadGateway, map[string]string{"error": "ai_proxy_read_failed"})
			return
		}

		for key, values := range resp.Header {
			if strings.EqualFold(key, "Content-Length") {
				continue
			}
			for _, value := range values {
				w.Header().Add(key, value)
			}
		}
		w.WriteHeader(resp.StatusCode)
		_, _ = w.Write(body)
		h.logProxyCompletion(r.Context(), "AI proxy request completed", target, resp.StatusCode, time.Since(start), body)
	}
}

func (h *Handler) logProxyCompletion(ctx context.Context, message string, target string, status int, duration time.Duration, body []byte) {
	attrs := []any{
		"request_id", logging.RequestID(ctx),
		"target", target,
		"upstream_status", status,
		"duration_ms", duration.Milliseconds(),
	}
	if status >= 500 {
		h.logger.ErrorContext(ctx, message, append(attrs, "body", truncateLogBody(body))...)
		return
	}
	if status >= 400 {
		h.logger.WarnContext(ctx, message, append(attrs, "body", truncateLogBody(body))...)
		return
	}
	h.logger.InfoContext(ctx, message, attrs...)
}

func suggestions(query string, resultCount int) []string {
	if resultCount > 0 {
		return nil
	}
	if query == "" {
		return []string{"thu tu khoa cu the hon", "kiem tra tag/category", "hoi Lead neu chua co SOP published"}
	}
	return []string{"thu tag khac", "kiem tra case reason", "escalate CS Lead neu khong co SOP"}
}

func emptySlice(values []string) []string {
	if values == nil {
		return []string{}
	}
	return values
}

func writeJSON(w http.ResponseWriter, status int, payload any) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	_ = json.NewEncoder(w).Encode(payload)
}

func truncateLogBody(data []byte) string {
	text := strings.TrimSpace(string(data))
	if len(text) > 1000 {
		return text[:1000] + "...(truncated)"
	}
	return text
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
