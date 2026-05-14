package service

import (
	"bytes"
	"context"
	"crypto/rand"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"io"
	"log/slog"
	"net/http"
	"sort"
	"strings"
	"time"
	"unicode"

	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"

	"cs-kb-api/internal/config"
	"cs-kb-api/internal/model"
)

type Store struct {
	db     *pgxpool.Pool
	cfg    config.Config
	client *http.Client
	logger *slog.Logger
}

type meiliSearchResponse struct {
	Hits []meiliSOPDocument `json:"hits"`
}

type meiliSOPDocument struct {
	SOPID       string    `json:"sop_id"`
	Title       string    `json:"title"`
	Snippet     string    `json:"snippet"`
	Category    string    `json:"category"`
	Audience    []string  `json:"audience"`
	Vertical    string    `json:"vertical"`
	Tags        []string  `json:"tags"`
	CaseReasons []string  `json:"case_reasons"`
	UpdatedAt   time.Time `json:"updated_at"`
	Version     int       `json:"version"`
}

type aiChunkDocument struct {
	ChunkID       string         `json:"chunk_id"`
	DocumentID    string         `json:"document_id"`
	VersionID     string         `json:"version_id"`
	Title         string         `json:"title"`
	VersionNumber int            `json:"version_number"`
	Status        string         `json:"status"`
	PublishState  string         `json:"publish_state"`
	DocumentType  string         `json:"document_type"`
	ReviewStatus  string         `json:"review_status"`
	ChunkIndex    int            `json:"chunk_index"`
	Section       string         `json:"section"`
	Heading       string         `json:"heading"`
	Content       string         `json:"content"`
	TokenCount    int            `json:"token_count"`
	Metadata      map[string]any `json:"metadata"`
	Audience      any            `json:"audience"`
	Vertical      any            `json:"vertical"`
	Category      any            `json:"category"`
	Tags          any            `json:"tags"`
	CaseReasons   any            `json:"case_reasons"`
}

func NewStore(ctx context.Context, cfg config.Config, logger *slog.Logger) (*Store, error) {
	if strings.TrimSpace(cfg.DatabaseURL) == "" {
		return nil, fmt.Errorf("DATABASE_URL is required; set it in .env or .env.local before running the API")
	}
	logger.InfoContext(ctx, "postgres pool init started", "connect_timeout_seconds", int(cfg.DatabaseConnectTimeout.Seconds()))
	poolConfig, err := pgxpool.ParseConfig(cfg.DatabaseURL)
	if err != nil {
		return nil, fmt.Errorf("parse DATABASE_URL: %w", err)
	}
	if poolConfig.ConnConfig.ConnectTimeout == 0 {
		poolConfig.ConnConfig.ConnectTimeout = cfg.DatabaseConnectTimeout
	}
	pool, err := pgxpool.NewWithConfig(ctx, poolConfig)
	if err != nil {
		return nil, fmt.Errorf("create postgres pool: %w", err)
	}
	store := &Store{db: pool, cfg: cfg, client: &http.Client{Timeout: 10 * time.Second}, logger: logger}
	if err := pool.Ping(ctx); err != nil {
		pool.Close()
		return nil, fmt.Errorf("connect to postgres: %w", err)
	}
	logger.InfoContext(ctx, "postgres ping succeeded")
	if err := store.EnsureSchema(ctx); err != nil {
		pool.Close()
		return nil, fmt.Errorf("ensure postgres schema: %w", err)
	}
	logger.InfoContext(ctx, "postgres schema ensured")
	if cfg.SeedDemoSOPs {
		if err := store.Seed(ctx); err != nil {
			pool.Close()
			return nil, err
		}
		logger.InfoContext(ctx, "demo SOP seed completed")
	}
	if err := store.IndexPublishedSOPs(ctx); err != nil {
		logger.WarnContext(ctx, "initial meilisearch indexing failed", "error", err)
	} else {
		logger.InfoContext(ctx, "initial meilisearch indexing completed")
	}
	return store, nil
}

func (s *Store) Close() {
	s.db.Close()
}

func (s *Store) PostgresHealth(ctx context.Context) model.HealthStatus {
	start := time.Now()
	if err := s.db.Ping(ctx); err != nil {
		return model.HealthStatus{
			Name:      "postgres",
			Status:    "down",
			LatencyMS: time.Since(start).Milliseconds(),
			Detail:    err.Error(),
		}
	}
	return model.HealthStatus{
		Name:      "postgres",
		Status:    "healthy",
		LatencyMS: time.Since(start).Milliseconds(),
		Detail:    "Postgres pool ping succeeded",
	}
}

func (s *Store) MeiliHealth(ctx context.Context) model.HealthStatus {
	start := time.Now()
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, strings.TrimRight(s.cfg.MeiliHost, "/")+"/health", nil)
	if err != nil {
		return model.HealthStatus{Name: "meilisearch", Status: "down", Detail: err.Error()}
	}
	if s.cfg.MeiliMasterKey != "" {
		req.Header.Set("Authorization", "Bearer "+s.cfg.MeiliMasterKey)
	}
	resp, err := s.client.Do(req)
	if err != nil {
		return model.HealthStatus{
			Name:      "meilisearch",
			Status:    "down",
			LatencyMS: time.Since(start).Milliseconds(),
			Detail:    err.Error(),
		}
	}
	defer resp.Body.Close()
	status := "healthy"
	if resp.StatusCode >= 300 {
		status = "degraded"
	}
	return model.HealthStatus{
		Name:      "meilisearch",
		Status:    status,
		LatencyMS: time.Since(start).Milliseconds(),
		Detail:    resp.Status,
	}
}

func (s *Store) EnsureSchema(ctx context.Context) error {
	_, err := s.db.Exec(ctx, `
CREATE TABLE IF NOT EXISTS kb_sops (
  id text PRIMARY KEY,
  code text NOT NULL UNIQUE,
  title text NOT NULL,
  summary text NOT NULL,
  audience jsonb NOT NULL DEFAULT '[]'::jsonb,
  vertical text NOT NULL,
  category text NOT NULL,
  tags jsonb NOT NULL DEFAULT '[]'::jsonb,
  case_reasons jsonb NOT NULL DEFAULT '[]'::jsonb,
  status text NOT NULL DEFAULT 'active',
  current_version_id text,
  owner_team text NOT NULL,
  metrics jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS kb_sop_versions (
  id text PRIMARY KEY,
  sop_id text NOT NULL REFERENCES kb_sops(id) ON DELETE CASCADE,
  version_number integer NOT NULL,
  status text NOT NULL DEFAULT 'draft',
  effective_from timestamptz,
  created_by text NOT NULL DEFAULT 'system',
  approved_by text NOT NULL DEFAULT '',
  change_summary text NOT NULL DEFAULT '',
  sections jsonb NOT NULL DEFAULT '{}'::jsonb,
  published_at timestamptz,
  archived_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (sop_id, version_number)
);

CREATE INDEX IF NOT EXISTS idx_kb_sops_status ON kb_sops(status);
CREATE INDEX IF NOT EXISTS idx_kb_sop_versions_status ON kb_sop_versions(status);
CREATE INDEX IF NOT EXISTS idx_kb_sops_updated_at ON kb_sops(updated_at DESC);
`)
	return err
}

func (s *Store) Seed(ctx context.Context) error {
	var count int
	if err := s.db.QueryRow(ctx, "SELECT COUNT(*) FROM kb_sops").Scan(&count); err != nil {
		return err
	}
	if count > 0 {
		return nil
	}
	for _, sop := range seedSOPs() {
		if err := s.UpsertSOP(ctx, sop); err != nil {
			return err
		}
	}
	return nil
}

func (s *Store) UpsertSOP(ctx context.Context, sop model.SOP) error {
	audience, _ := json.Marshal(sop.Audience)
	tags, _ := json.Marshal(sop.Tags)
	caseReasons, _ := json.Marshal(sop.CaseReasons)
	metrics, _ := json.Marshal(sop.Analytics)
	sections, _ := json.Marshal(sop.CurrentVersion.Sections)

	tx, err := s.db.Begin(ctx)
	if err != nil {
		return err
	}
	defer tx.Rollback(ctx)

	_, err = tx.Exec(ctx, `
INSERT INTO kb_sops (
  id, code, title, summary, audience, vertical, category, tags, case_reasons,
  status, current_version_id, owner_team, metrics, updated_at
) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14)
ON CONFLICT (id) DO UPDATE SET
  code = EXCLUDED.code,
  title = EXCLUDED.title,
  summary = EXCLUDED.summary,
  audience = EXCLUDED.audience,
  vertical = EXCLUDED.vertical,
  category = EXCLUDED.category,
  tags = EXCLUDED.tags,
  case_reasons = EXCLUDED.case_reasons,
  status = EXCLUDED.status,
  current_version_id = EXCLUDED.current_version_id,
  owner_team = EXCLUDED.owner_team,
  metrics = EXCLUDED.metrics,
  updated_at = EXCLUDED.updated_at
`, sop.ID, sop.Code, sop.Title, sop.Summary, audience, sop.Vertical, sop.Category, tags, caseReasons,
		sop.Status, sop.CurrentVersionID, sop.OwnerTeam, metrics, sop.UpdatedAt)
	if err != nil {
		return err
	}

	_, err = tx.Exec(ctx, `
INSERT INTO kb_sop_versions (
  id, sop_id, version_number, status, effective_from, created_by, approved_by,
  change_summary, sections, published_at
) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10)
ON CONFLICT (id) DO UPDATE SET
  version_number = EXCLUDED.version_number,
  status = EXCLUDED.status,
  effective_from = EXCLUDED.effective_from,
  created_by = EXCLUDED.created_by,
  approved_by = EXCLUDED.approved_by,
  change_summary = EXCLUDED.change_summary,
  sections = EXCLUDED.sections,
  published_at = EXCLUDED.published_at
`, sop.CurrentVersion.ID, sop.ID, sop.CurrentVersion.VersionNumber, sop.CurrentVersion.Status,
		sop.CurrentVersion.EffectiveFrom, sop.CurrentVersion.CreatedBy, sop.CurrentVersion.ApprovedBy,
		sop.CurrentVersion.ChangeSummary, sections, sop.CurrentVersion.PublishedAt)
	if err != nil {
		return err
	}
	return tx.Commit(ctx)
}

func (s *Store) ListSOPs(ctx context.Context) ([]model.SOP, error) {
	rows, err := s.db.Query(ctx, `
SELECT s.id, s.code, s.title, s.summary, s.audience, s.vertical, s.category,
       s.tags, s.case_reasons, s.status, s.current_version_id, s.owner_team,
       s.updated_at, s.metrics,
       v.id, v.version_number, v.status, v.effective_from, v.created_by,
       v.approved_by, v.change_summary, v.sections, v.published_at
FROM kb_sops s
JOIN kb_sop_versions v ON v.id = s.current_version_id
WHERE s.status = 'active' AND v.status = 'published'
ORDER BY s.updated_at DESC
`)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	var output []model.SOP
	for rows.Next() {
		sop, err := scanSOP(rows)
		if err != nil {
			return nil, err
		}
		output = append(output, sop)
	}
	return output, rows.Err()
}

func (s *Store) GetSOP(ctx context.Context, id string) (model.SOP, bool, error) {
	row := s.db.QueryRow(ctx, `
SELECT s.id, s.code, s.title, s.summary, s.audience, s.vertical, s.category,
       s.tags, s.case_reasons, s.status, s.current_version_id, s.owner_team,
       s.updated_at, s.metrics,
       v.id, v.version_number, v.status, v.effective_from, v.created_by,
       v.approved_by, v.change_summary, v.sections, v.published_at
FROM kb_sops s
JOIN kb_sop_versions v ON v.id = s.current_version_id
WHERE s.id = $1 AND s.status = 'active' AND v.status = 'published'
`, id)
	sop, err := scanSOP(row)
	if err != nil {
		if err == pgx.ErrNoRows {
			return model.SOP{}, false, nil
		}
		return model.SOP{}, false, err
	}
	return sop, true, nil
}

func (s *Store) CreateSOP(ctx context.Context, input model.SOP) (model.SOP, error) {
	now := time.Now().UTC()
	if input.ID == "" {
		input.ID = "sop_" + randomID()
	}
	if input.Code == "" {
		input.Code = strings.ToUpper(strings.ReplaceAll(input.ID, "_", "-"))
	}
	if input.Status == "" {
		input.Status = "active"
	}
	if input.OwnerTeam == "" {
		input.OwnerTeam = "CS Ops"
	}
	if input.UpdatedAt.IsZero() {
		input.UpdatedAt = now
	}
	if input.CurrentVersion.ID == "" {
		input.CurrentVersion.ID = "ver_" + randomID()
	}
	if input.CurrentVersion.Status == "" {
		input.CurrentVersion.Status = "draft"
	}
	if input.CurrentVersion.VersionNumber == 0 {
		input.CurrentVersion.VersionNumber = 1
	}
	if input.CurrentVersion.EffectiveFrom.IsZero() {
		input.CurrentVersion.EffectiveFrom = now
	}
	if input.CurrentVersion.CreatedBy == "" {
		input.CurrentVersion.CreatedBy = "api"
	}
	if input.CurrentVersion.PublishedAt.IsZero() && input.CurrentVersion.Status == "published" {
		input.CurrentVersion.PublishedAt = now
	}
	input.CurrentVersion.SOPID = input.ID
	input.CurrentVersionID = input.CurrentVersion.ID
	if err := s.UpsertSOP(ctx, input); err != nil {
		return model.SOP{}, err
	}
	if input.CurrentVersion.Status == "published" {
		_ = s.IndexPublishedSOPs(ctx)
		_ = s.indexSOPVersionAI(ctx, input)
	}
	return input, nil
}

func (s *Store) CreateVersion(ctx context.Context, sopID string, input model.SOPVersion) (model.SOPVersion, error) {
	now := time.Now().UTC()
	var nextVersion int
	if err := s.db.QueryRow(ctx, "SELECT COALESCE(MAX(version_number), 0) + 1 FROM kb_sop_versions WHERE sop_id = $1", sopID).Scan(&nextVersion); err != nil {
		return model.SOPVersion{}, err
	}
	if input.ID == "" {
		input.ID = "ver_" + randomID()
	}
	input.SOPID = sopID
	input.VersionNumber = nextVersion
	if input.Status == "" {
		input.Status = "draft"
	}
	if input.EffectiveFrom.IsZero() {
		input.EffectiveFrom = now
	}
	if input.CreatedBy == "" {
		input.CreatedBy = "api"
	}
	sections, _ := json.Marshal(input.Sections)
	_, err := s.db.Exec(ctx, `
INSERT INTO kb_sop_versions (
  id, sop_id, version_number, status, effective_from, created_by,
  approved_by, change_summary, sections, published_at
) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10)
`, input.ID, input.SOPID, input.VersionNumber, input.Status, input.EffectiveFrom,
		input.CreatedBy, input.ApprovedBy, input.ChangeSummary, sections, input.PublishedAt)
	if err != nil {
		return model.SOPVersion{}, err
	}
	return input, nil
}

func (s *Store) SetVersionStatus(ctx context.Context, versionID string, status string, actor string) (model.SOPVersion, error) {
	if actor == "" {
		actor = "api"
	}
	var approvedBy any
	if status == "published" {
		approvedBy = actor
	} else {
		approvedBy = nil
	}
	row := s.db.QueryRow(ctx, `
UPDATE kb_sop_versions
SET status = $2, approved_by = COALESCE($3::text, approved_by)
WHERE id = $1
RETURNING id, sop_id, version_number, status, effective_from, created_by, approved_by,
          change_summary, sections, COALESCE(published_at, effective_from, now())
`, versionID, status, approvedBy)
	return scanVersion(row)
}

func (s *Store) PublishVersion(ctx context.Context, versionID string, actor string) (model.SOP, error) {
	if actor == "" {
		actor = "api"
	}
	tx, err := s.db.Begin(ctx)
	if err != nil {
		return model.SOP{}, err
	}
	defer tx.Rollback(ctx)

	var sopID string
	if err := tx.QueryRow(ctx, "SELECT sop_id FROM kb_sop_versions WHERE id = $1 FOR UPDATE", versionID).Scan(&sopID); err != nil {
		return model.SOP{}, err
	}
	if _, err := tx.Exec(ctx, `
UPDATE kb_sop_versions
SET status = 'archived', archived_at = now()
WHERE sop_id = $1 AND status = 'published' AND id <> $2
`, sopID, versionID); err != nil {
		return model.SOP{}, err
	}
	if _, err := tx.Exec(ctx, `
UPDATE kb_sop_versions
SET status = 'published', approved_by = $2, published_at = COALESCE(published_at, now()), archived_at = NULL
WHERE id = $1
`, versionID, actor); err != nil {
		return model.SOP{}, err
	}
	if _, err := tx.Exec(ctx, "UPDATE kb_sops SET current_version_id = $1, status = 'active', updated_at = now() WHERE id = $2", versionID, sopID); err != nil {
		return model.SOP{}, err
	}
	if err := tx.Commit(ctx); err != nil {
		return model.SOP{}, err
	}

	sop, ok, err := s.GetSOP(ctx, sopID)
	if err != nil {
		return model.SOP{}, err
	}
	if !ok {
		return model.SOP{}, pgx.ErrNoRows
	}
	_ = s.IndexPublishedSOPs(ctx)
	_ = s.indexSOPVersionAI(ctx, sop)
	return sop, nil
}

func (s *Store) ArchiveSOP(ctx context.Context, sopID string) error {
	_, err := s.db.Exec(ctx, "UPDATE kb_sops SET status = 'archived', updated_at = now() WHERE id = $1", sopID)
	if err != nil {
		return err
	}
	_ = s.DeleteSOPFromMeili(ctx, sopID)
	return nil
}

func (s *Store) Search(ctx context.Context, req model.SearchRequest) ([]model.SearchResult, []string, error) {
	results, err := s.searchMeili(ctx, req)
	if err == nil {
		return results, []string{"meilisearch", "filters"}, nil
	}
	results, fallbackErr := s.searchPostgres(ctx, req)
	if fallbackErr != nil {
		return nil, nil, fallbackErr
	}
	return results, []string{"postgres_fallback", "filters"}, nil
}

func (s *Store) Popular(ctx context.Context, limit int) ([]model.SOP, error) {
	sops, err := s.ListSOPs(ctx)
	if err != nil {
		return nil, err
	}
	sort.Slice(sops, func(i, j int) bool {
		return sops[i].Analytics.Views > sops[j].Analytics.Views
	})
	if len(sops) > limit {
		return sops[:limit], nil
	}
	return sops, nil
}

func (s *Store) RecentlyUpdated(ctx context.Context, limit int) ([]model.SOP, error) {
	sops, err := s.ListSOPs(ctx)
	if err != nil {
		return nil, err
	}
	if len(sops) > limit {
		return sops[:limit], nil
	}
	return sops, nil
}

func (s *Store) IndexPublishedSOPs(ctx context.Context) error {
	sops, err := s.ListSOPs(ctx)
	if err != nil {
		return err
	}
	s.logger.InfoContext(ctx, "index published SOPs started", "count", len(sops))
	docs := make([]meiliSOPDocument, 0, len(sops))
	for _, sop := range sops {
		docs = append(docs, sopToMeiliDocument(sop))
	}
	if err := s.ensureMeiliIndex(ctx, "sops", []string{"audience", "vertical", "category", "tags", "case_reasons"}); err != nil {
		return err
	}
	return s.meiliRequest(ctx, http.MethodPost, "/indexes/sops/documents?primaryKey=sop_id", docs, nil)
}

func (s *Store) IndexAIDocument(ctx context.Context, payload map[string]any) error {
	documentID, _ := payload["document_id"].(string)
	if documentID == "" {
		return nil
	}
	s.logger.InfoContext(ctx, "index AI document started",
		"document_id", documentID,
		"version_id", payload["version_id"],
		"status", payload["status"],
		"title", payload["title"],
	)
	if err := s.DeleteAIChunksFromMeili(ctx, documentID); err != nil {
		s.logger.WarnContext(ctx, "delete existing AI chunks from meili failed", "document_id", documentID, "error", err)
	}
	if err := s.ensureMeiliIndex(ctx, "ai_documents", []string{"status", "publish_state", "vertical", "category", "tags", "case_reasons"}); err != nil {
		return err
	}
	metadata, _ := payload["metadata"].(map[string]any)
	doc := map[string]any{
		"document_id":    documentID,
		"version_id":     payload["version_id"],
		"external_id":    payload["external_id"],
		"title":          payload["title"],
		"version_number": payload["version_number"],
		"status":         payload["status"],
		"publish_state":  payload["publish_state"],
		"document_type":  payload["document_type"],
		"review_status":  payload["review_status"],
		"chunk_count":    payload["chunk_count"],
		"metadata":       metadata,
		"audience":       metadata["audience"],
		"vertical":       metadata["vertical"],
		"category":       metadata["category"],
		"tags":           metadata["tags"],
		"case_reasons":   metadata["case_reasons"],
	}
	if err := s.meiliRequest(ctx, http.MethodPost, "/indexes/ai_documents/documents?primaryKey=document_id", []map[string]any{doc}, nil); err != nil {
		return err
	}
	if err := s.indexAIChunks(ctx, payload, metadata); err != nil {
		return err
	}
	s.logger.InfoContext(ctx, "index AI document completed", "document_id", documentID)
	return nil
}

func (s *Store) DeleteAIDocumentFromMeili(ctx context.Context, documentID string) error {
	if documentID == "" {
		return nil
	}
	return s.meiliRequest(ctx, http.MethodDelete, "/indexes/ai_documents/documents/"+documentID, nil, nil)
}

func (s *Store) DeleteAIChunksFromMeili(ctx context.Context, documentID string) error {
	if documentID == "" {
		return nil
	}
	_ = s.ensureMeiliIndex(ctx, "ai_chunks", []string{"document_id", "version_id", "status", "publish_state", "vertical", "category", "tags", "case_reasons"})
	payload := map[string]string{"filter": `document_id = "` + documentID + `"`}
	return s.meiliRequest(ctx, http.MethodPost, "/indexes/ai_chunks/documents/delete", payload, nil)
}

func (s *Store) indexAIChunks(ctx context.Context, payload map[string]any, metadata map[string]any) error {
	documentID, _ := payload["document_id"].(string)
	versionID, _ := payload["version_id"].(string)
	if documentID == "" || versionID == "" {
		return nil
	}
	target := strings.TrimRight(s.cfg.AIBaseURL, "/") + "/ai/v1/documents/" + documentID + "/chunks?version_id=" + versionID
	s.logger.DebugContext(ctx, "AI chunks fetch started", "document_id", documentID, "version_id", versionID, "target", target)
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, target, nil)
	if err != nil {
		return err
	}
	resp, err := s.client.Do(req)
	if err != nil {
		s.logger.ErrorContext(ctx, "AI chunks fetch failed", "document_id", documentID, "version_id", versionID, "target", target, "error", err)
		return err
	}
	defer resp.Body.Close()
	if resp.StatusCode >= 300 {
		data, _ := io.ReadAll(resp.Body)
		s.logger.ErrorContext(ctx, "AI chunks fetch returned non-2xx", "document_id", documentID, "version_id", versionID, "target", target, "status", resp.StatusCode, "body", truncateLogBody(data))
		return fmt.Errorf("ai chunk read failed: %s", strings.TrimSpace(string(data)))
	}
	var chunks []struct {
		ChunkID    string         `json:"chunk_id"`
		ChunkIndex int            `json:"chunk_index"`
		Section    string         `json:"section"`
		Heading    string         `json:"heading"`
		Content    string         `json:"content"`
		TokenCount int            `json:"token_count"`
		Metadata   map[string]any `json:"metadata"`
	}
	if err := json.NewDecoder(resp.Body).Decode(&chunks); err != nil {
		return err
	}
	docs := make([]aiChunkDocument, 0, len(chunks))
	for _, chunk := range chunks {
		chunkMetadata := metadata
		if len(chunk.Metadata) > 0 {
			chunkMetadata = chunk.Metadata
		}
		docs = append(docs, aiChunkDocument{
			ChunkID:       chunk.ChunkID,
			DocumentID:    documentID,
			VersionID:     versionID,
			Title:         fmt.Sprint(payload["title"]),
			VersionNumber: intFromAny(payload["version_number"]),
			Status:        fmt.Sprint(payload["status"]),
			PublishState:  fmt.Sprint(payload["publish_state"]),
			DocumentType:  fmt.Sprint(payload["document_type"]),
			ReviewStatus:  fmt.Sprint(payload["review_status"]),
			Metadata:      chunkMetadata,
			ChunkIndex:    chunk.ChunkIndex,
			Section:       chunk.Section,
			Heading:       chunk.Heading,
			Content:       chunk.Content,
			TokenCount:    chunk.TokenCount,
			Audience:      chunkMetadata["audience"],
			Vertical:      chunkMetadata["vertical"],
			Category:      chunkMetadata["category"],
			Tags:          chunkMetadata["tags"],
			CaseReasons:   chunkMetadata["case_reasons"],
		})
	}
	if len(docs) == 0 {
		s.logger.WarnContext(ctx, "AI chunks fetch returned no chunks", "document_id", documentID, "version_id", versionID)
		return nil
	}
	if err := s.ensureMeiliIndex(ctx, "ai_chunks", []string{"document_id", "version_id", "status", "publish_state", "vertical", "category", "tags", "case_reasons"}); err != nil {
		return err
	}
	if err := s.meiliRequest(ctx, http.MethodPost, "/indexes/ai_chunks/documents?primaryKey=chunk_id", docs, nil); err != nil {
		return err
	}
	s.logger.InfoContext(ctx, "AI chunks indexed", "document_id", documentID, "version_id", versionID, "chunk_count", len(docs))
	return nil
}

func (s *Store) DeleteSOPFromMeili(ctx context.Context, sopID string) error {
	if sopID == "" {
		return nil
	}
	return s.meiliRequest(ctx, http.MethodDelete, "/indexes/sops/documents/"+sopID, nil, nil)
}

func scanSOP(row pgx.Row) (model.SOP, error) {
	var sop model.SOP
	var audienceJSON, tagsJSON, caseReasonsJSON, metricsJSON, sectionsJSON []byte
	var version model.SOPVersion
	err := row.Scan(
		&sop.ID, &sop.Code, &sop.Title, &sop.Summary, &audienceJSON, &sop.Vertical, &sop.Category,
		&tagsJSON, &caseReasonsJSON, &sop.Status, &sop.CurrentVersionID, &sop.OwnerTeam,
		&sop.UpdatedAt, &metricsJSON,
		&version.ID, &version.VersionNumber, &version.Status, &version.EffectiveFrom, &version.CreatedBy,
		&version.ApprovedBy, &version.ChangeSummary, &sectionsJSON, &version.PublishedAt,
	)
	if err != nil {
		return model.SOP{}, err
	}
	version.SOPID = sop.ID
	_ = json.Unmarshal(audienceJSON, &sop.Audience)
	_ = json.Unmarshal(tagsJSON, &sop.Tags)
	_ = json.Unmarshal(caseReasonsJSON, &sop.CaseReasons)
	_ = json.Unmarshal(metricsJSON, &sop.Analytics)
	_ = json.Unmarshal(sectionsJSON, &version.Sections)
	sop.CurrentVersion = version
	return sop, nil
}

func scanVersion(row pgx.Row) (model.SOPVersion, error) {
	var version model.SOPVersion
	var sectionsJSON []byte
	err := row.Scan(
		&version.ID, &version.SOPID, &version.VersionNumber, &version.Status,
		&version.EffectiveFrom, &version.CreatedBy, &version.ApprovedBy,
		&version.ChangeSummary, &sectionsJSON, &version.PublishedAt,
	)
	if err != nil {
		return model.SOPVersion{}, err
	}
	_ = json.Unmarshal(sectionsJSON, &version.Sections)
	return version, nil
}

func (s *Store) indexSOPVersionAI(ctx context.Context, sop model.SOP) error {
	payload := map[string]any{
		"sop_id":     sop.ID,
		"version_id": sop.CurrentVersion.ID,
		"status":     sop.CurrentVersion.Status,
		"title":      sop.Title,
		"sections": map[string]any{
			"when_to_apply":      sop.CurrentVersion.Sections.WhenToApply,
			"input_requirements": sop.CurrentVersion.Sections.InputRequirement,
			"handling_checklist": sop.CurrentVersion.Sections.Checklist,
			"agent_script":       sop.CurrentVersion.Sections.AgentScript,
			"macro_response":     sop.CurrentVersion.Sections.MacroResponses,
			"sla":                sop.CurrentVersion.Sections.SLA,
			"escalation":         sop.CurrentVersion.Sections.Escalation,
			"related_policies":   sop.CurrentVersion.Sections.RelatedPolicies,
			"change_summary":     sop.CurrentVersion.ChangeSummary,
		},
		"metadata": map[string]any{
			"audience": sop.Audience,
			"vertical": sop.Vertical,
			"category": sop.Category,
			"tags":     sop.Tags,
		},
	}
	data, err := json.Marshal(payload)
	if err != nil {
		return err
	}
	req, err := http.NewRequestWithContext(ctx, http.MethodPost, strings.TrimRight(s.cfg.AIBaseURL, "/")+"/ai/v1/index/sop-version", bytes.NewReader(data))
	if err != nil {
		return err
	}
	req.Header.Set("Content-Type", "application/json")
	resp, err := s.client.Do(req)
	if err != nil {
		s.logger.ErrorContext(ctx, "AI SOP version index request failed", "sop_id", sop.ID, "version_id", sop.CurrentVersion.ID, "error", err)
		return err
	}
	defer resp.Body.Close()
	if resp.StatusCode >= 300 {
		body, _ := io.ReadAll(resp.Body)
		s.logger.ErrorContext(ctx, "AI SOP version index returned non-2xx", "sop_id", sop.ID, "version_id", sop.CurrentVersion.ID, "status", resp.StatusCode, "body", truncateLogBody(body))
		return fmt.Errorf("ai sop index failed: %s", strings.TrimSpace(string(body)))
	}
	s.logger.InfoContext(ctx, "AI SOP version index completed", "sop_id", sop.ID, "version_id", sop.CurrentVersion.ID)
	return nil
}

func (s *Store) searchPostgres(ctx context.Context, req model.SearchRequest) ([]model.SearchResult, error) {
	sops, err := s.ListSOPs(ctx)
	if err != nil {
		return nil, err
	}
	query := normalize(req.Query)
	results := make([]model.SearchResult, 0)
	for _, sop := range sops {
		if !matchesFilters(sop, req.Filters) {
			continue
		}
		score := scoreSOP(sop, query)
		if query == "" {
			score = float64(sop.Analytics.Views) / 1000
		}
		if score <= 0 {
			continue
		}
		results = append(results, sopToSearchResult(sop, clamp(score/12)))
	}
	sort.Slice(results, func(i, j int) bool {
		return results[i].Confidence > results[j].Confidence
	})
	return results, nil
}

func (s *Store) searchMeili(ctx context.Context, req model.SearchRequest) ([]model.SearchResult, error) {
	payload := map[string]any{
		"q":     req.Query,
		"limit": 20,
	}
	if filter := meiliFilter(req.Filters); filter != "" {
		payload["filter"] = filter
	}
	var decoded meiliSearchResponse
	if err := s.meiliRequest(ctx, http.MethodPost, "/indexes/sops/search", payload, &decoded); err != nil {
		return nil, err
	}
	results := make([]model.SearchResult, 0, len(decoded.Hits))
	for index, hit := range decoded.Hits {
		confidence := 1 - float64(index)*0.06
		if confidence < 0.18 {
			confidence = 0.18
		}
		results = append(results, model.SearchResult{
			SOPID: hit.SOPID, Title: hit.Title, Snippet: hit.Snippet, Category: hit.Category,
			Audience: hit.Audience, Vertical: hit.Vertical, Tags: hit.Tags, UpdatedAt: hit.UpdatedAt,
			Version: hit.Version, Confidence: confidence,
		})
	}
	return results, nil
}

func (s *Store) ensureMeiliIndex(ctx context.Context, index string, filterable []string) error {
	_ = s.meiliRequest(ctx, http.MethodPost, "/indexes", map[string]string{"uid": index}, nil)
	settings := map[string]any{
		"filterableAttributes": filterable,
		"sortableAttributes":   []string{"updated_at"},
	}
	return s.meiliRequest(ctx, http.MethodPatch, "/indexes/"+index+"/settings", settings, nil)
}

func (s *Store) meiliRequest(ctx context.Context, method, path string, payload any, target any) error {
	start := time.Now()
	var body io.Reader
	if payload != nil {
		data, err := json.Marshal(payload)
		if err != nil {
			return err
		}
		body = bytes.NewReader(data)
	}
	url := strings.TrimRight(s.cfg.MeiliHost, "/") + path
	req, err := http.NewRequestWithContext(ctx, method, url, body)
	if err != nil {
		return err
	}
	req.Header.Set("Content-Type", "application/json")
	if s.cfg.MeiliMasterKey != "" {
		req.Header.Set("Authorization", "Bearer "+s.cfg.MeiliMasterKey)
	}
	resp, err := s.client.Do(req)
	if err != nil {
		s.logger.ErrorContext(ctx, "meilisearch request failed", "method", method, "path", path, "duration_ms", time.Since(start).Milliseconds(), "error", err)
		return err
	}
	defer resp.Body.Close()
	if resp.StatusCode >= 300 && !(method == http.MethodPost && resp.StatusCode == http.StatusConflict) {
		data, _ := io.ReadAll(resp.Body)
		s.logger.ErrorContext(ctx, "meilisearch returned non-2xx", "method", method, "path", path, "status", resp.StatusCode, "duration_ms", time.Since(start).Milliseconds(), "body", truncateLogBody(data))
		return fmt.Errorf("meili %s %s failed: %s", method, path, strings.TrimSpace(string(data)))
	}
	s.logger.DebugContext(ctx, "meilisearch request completed", "method", method, "path", path, "status", resp.StatusCode, "duration_ms", time.Since(start).Milliseconds())
	if target != nil {
		return json.NewDecoder(resp.Body).Decode(target)
	}
	return nil
}

func truncateLogBody(data []byte) string {
	text := strings.TrimSpace(string(data))
	if len(text) > 1000 {
		return text[:1000] + "...(truncated)"
	}
	return text
}

func sopToMeiliDocument(sop model.SOP) meiliSOPDocument {
	return meiliSOPDocument{
		SOPID: sop.ID, Title: sop.Title, Snippet: sop.Summary, Category: sop.Category,
		Audience: sop.Audience, Vertical: sop.Vertical, Tags: sop.Tags, CaseReasons: sop.CaseReasons,
		UpdatedAt: sop.UpdatedAt, Version: sop.CurrentVersion.VersionNumber,
	}
}

func sopToSearchResult(sop model.SOP, confidence float64) model.SearchResult {
	return model.SearchResult{
		SOPID: sop.ID, Title: sop.Title, Snippet: sop.Summary, Category: sop.Category,
		Audience: sop.Audience, Vertical: sop.Vertical, Tags: sop.Tags, UpdatedAt: sop.UpdatedAt,
		Version: sop.CurrentVersion.VersionNumber, Confidence: confidence,
	}
}

func meiliFilter(filters model.SearchFilters) string {
	parts := []string{}
	add := func(field string, values []string) {
		if len(values) == 0 {
			return
		}
		quoted := make([]string, 0, len(values))
		for _, value := range values {
			quoted = append(quoted, fmt.Sprintf("%s = %q", field, value))
		}
		parts = append(parts, "("+strings.Join(quoted, " OR ")+")")
	}
	add("audience", filters.Audience)
	add("vertical", filters.Vertical)
	add("category", filters.Category)
	add("tags", filters.Tags)
	add("case_reasons", filters.CaseReasons)
	return strings.Join(parts, " AND ")
}

func matchesFilters(sop model.SOP, filters model.SearchFilters) bool {
	return containsAnyOrEmpty(sop.Audience, filters.Audience) &&
		containsAnyOrEmpty([]string{sop.Vertical}, filters.Vertical) &&
		containsAnyOrEmpty([]string{sop.Category}, filters.Category) &&
		containsAnyOrEmpty(sop.Tags, filters.Tags) &&
		containsAnyOrEmpty(sop.CaseReasons, filters.CaseReasons)
}

func scoreSOP(sop model.SOP, query string) float64 {
	if query == "" {
		return 1
	}
	haystack := normalize(strings.Join([]string{
		sop.Code, sop.Title, sop.Summary, sop.Vertical, sop.Category,
		strings.Join(sop.Tags, " "), strings.Join(sop.CaseReasons, " "),
		sop.CurrentVersion.Sections.WhenToApply, sop.CurrentVersion.Sections.InputRequirement,
		strings.Join(sop.CurrentVersion.Sections.Checklist, " "),
	}, " "))
	score := 0.0
	if strings.Contains(normalize(sop.Title), query) {
		score += 6
	}
	if strings.Contains(normalize(strings.Join(sop.Tags, " ")), query) {
		score += 5
	}
	if strings.Contains(normalize(strings.Join(sop.CaseReasons, " ")), query) {
		score += 5
	}
	for _, token := range strings.Fields(query) {
		if strings.Contains(haystack, token) {
			score += 1.5
		}
	}
	score += float64(sop.Analytics.Views) / 1500
	return score
}

func normalize(value string) string {
	value = strings.ToLower(value)
	var builder strings.Builder
	for _, r := range value {
		if unicode.IsLetter(r) || unicode.IsNumber(r) {
			builder.WriteRune(r)
			continue
		}
		builder.WriteRune(' ')
	}
	return strings.Join(strings.Fields(builder.String()), " ")
}

func containsAnyOrEmpty(values []string, filters []string) bool {
	if len(filters) == 0 {
		return true
	}
	valueSet := map[string]bool{}
	for _, value := range values {
		valueSet[normalize(value)] = true
	}
	for _, filter := range filters {
		if valueSet[normalize(filter)] {
			return true
		}
	}
	return false
}

func clamp(value float64) float64 {
	if value < 0 {
		return 0
	}
	if value > 1 {
		return 1
	}
	return value
}

func randomID() string {
	var data [8]byte
	if _, err := rand.Read(data[:]); err != nil {
		return fmt.Sprintf("%d", time.Now().UnixNano())
	}
	return hex.EncodeToString(data[:])
}

func intFromAny(value any) int {
	switch typed := value.(type) {
	case int:
		return typed
	case int64:
		return int(typed)
	case float64:
		return int(typed)
	case json.Number:
		output, _ := typed.Int64()
		return int(output)
	default:
		return 0
	}
}
