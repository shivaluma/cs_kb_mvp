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

type meiliSOPSearchResponse struct {
	Hits []meiliSOPDocument `json:"hits"`
}

type meiliChunkSearchResponse struct {
	Hits []aiChunkDocument `json:"hits"`
}

type meiliSOPDocument struct {
	SOPID               string         `json:"sop_id"`
	Title               string         `json:"title"`
	Snippet             string         `json:"snippet"`
	Category            string         `json:"category"`
	Audience            []string       `json:"audience"`
	Vertical            string         `json:"vertical"`
	Tags                []string       `json:"tags"`
	CaseReasons         []string       `json:"case_reasons"`
	UpdatedAt           time.Time      `json:"updated_at"`
	Version             int            `json:"version"`
	RankingScore        float64        `json:"_rankingScore,omitempty"`
	RankingScoreDetails map[string]any `json:"_rankingScoreDetails,omitempty"`
}

type aiChunkDocument struct {
	ChunkID             string         `json:"chunk_id"`
	ID                  string         `json:"id"`
	DocumentID          string         `json:"document_id"`
	VersionID           string         `json:"version_id"`
	DocumentVersionID   string         `json:"document_version_id"`
	Title               string         `json:"title"`
	NormalizedTitle     string         `json:"normalized_title"`
	VersionNumber       int            `json:"version_number"`
	Status              string         `json:"status"`
	PublishState        string         `json:"publish_state"`
	DocumentType        string         `json:"document_type"`
	ReviewStatus        string         `json:"review_status"`
	IsCurrentVersion    bool           `json:"is_current_version"`
	ChunkIndex          int            `json:"chunk_index"`
	Section             string         `json:"section"`
	SectionPath         any            `json:"section_path"`
	Heading             string         `json:"heading"`
	Content             string         `json:"content"`
	DisplayText         string         `json:"display_text"`
	RetrievalText       string         `json:"retrieval_text"`
	SourceText          string         `json:"source_text"`
	TokenCount          int            `json:"token_count"`
	Metadata            map[string]any `json:"metadata"`
	UnitType            string         `json:"unit_type"`
	ChunkType           string         `json:"chunk_type"`
	StepCode            string         `json:"step_code"`
	Phase               string         `json:"phase"`
	Lane                string         `json:"lane"`
	PathTitle           string         `json:"path_title"`
	PathSteps           any            `json:"path_steps"`
	RiskLevel           string         `json:"risk_level"`
	RiskPriority        int            `json:"risk_priority"`
	SourceRefQuality    string         `json:"source_ref_quality"`
	SourceRefs          any            `json:"source_refs"`
	ParentSectionID     string         `json:"parent_section_id"`
	ParentChunkID       string         `json:"parent_chunk_id"`
	Audience            any            `json:"audience"`
	Visibility          string         `json:"visibility"`
	Scope               string         `json:"scope"`
	PolicyType          string         `json:"policy_type"`
	AuthorityLevel      string         `json:"authority_level"`
	AuthorityPriority   int            `json:"authority_priority"`
	Vertical            any            `json:"vertical"`
	Category            any            `json:"category"`
	Collections         any            `json:"collections"`
	Tags                any            `json:"tags"`
	CaseReasons         any            `json:"case_reasons"`
	MacroText           string         `json:"macro_text"`
	ForbiddenPhrases    any            `json:"forbidden_phrases"`
	Keywords            any            `json:"keywords"`
	EffectiveFrom       any            `json:"effective_from"`
	RequiresReview      bool           `json:"requires_review"`
	PublishBlocked      bool           `json:"publish_blocked"`
	SourceEvidenceOnly  bool           `json:"source_evidence_only"`
	UpdatedAt           any            `json:"updated_at"`
	RankingScore        float64        `json:"_rankingScore,omitempty"`
	RankingScoreDetails map[string]any `json:"_rankingScoreDetails,omitempty"`
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

func (s *Store) AutocompleteSuggestions(ctx context.Context, query string, limit int) ([]string, error) {
	limit = max(1, min(limit, 12))
	normalized := normalize(query)
	static := []string{
		"quy định nội dung phản hồi",
		"mẫu câu email mở đầu",
		"không cung cấp quy trình nội bộ",
		"khi nào dùng xin lỗi",
		"bộ phận chuyên môn",
	}
	output := make([]string, 0, limit)
	add := func(value string) {
		value = strings.TrimSpace(value)
		if value == "" {
			return
		}
		for _, existing := range output {
			if strings.EqualFold(existing, value) {
				return
			}
		}
		output = append(output, value)
	}
	for _, item := range static {
		if normalized == "" || strings.Contains(normalize(item), normalized) {
			add(item)
		}
		if len(output) >= limit {
			return output, nil
		}
	}

	like := "%" + normalized + "%"
	rows, err := s.db.Query(ctx, `
SELECT DISTINCT s.title
FROM kb_sops s
JOIN kb_sop_versions v ON v.id = s.current_version_id
WHERE s.status = 'active'
  AND v.status = 'published'
  AND ($1 = '' OR lower(s.title) LIKE $2 OR lower(s.category) LIKE $2)
ORDER BY s.title
LIMIT $3
`, normalized, like, limit)
	if err != nil {
		return output, err
	}
	defer rows.Close()
	for rows.Next() {
		var title string
		if err := rows.Scan(&title); err != nil {
			return output, err
		}
		add(title)
		if len(output) >= limit {
			break
		}
	}
	return output, rows.Err()
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
	if err := s.ensureMeiliIndex(ctx, "ai_documents", aiDocumentFilterableAttributes()); err != nil {
		return err
	}
	if err := s.ensureMeiliIndex(ctx, "sop_documents", sopDocumentFilterableAttributes()); err != nil {
		return err
	}
	metadata, _ := payload["metadata"].(map[string]any)
	versionID, _ := payload["version_id"].(string)
	updatedAt := time.Now().UTC()
	doc := map[string]any{
		"id":                  documentID,
		"document_id":         documentID,
		"document_version_id": versionID,
		"version_id":          versionID,
		"external_id":         payload["external_id"],
		"title":               payload["title"],
		"summary":             firstAny(metadata["summary"], metadata["description"], payload["title"]),
		"section_titles":      firstAny(metadata["section_titles"], metadata["headings"], []string{}),
		"version_number":      payload["version_number"],
		"status":              payload["status"],
		"publish_state":       payload["publish_state"],
		"is_current_version":  true,
		"document_type":       payload["document_type"],
		"review_status":       payload["review_status"],
		"chunk_count":         payload["chunk_count"],
		"metadata":            metadata,
		"audience":            metadata["audience"],
		"visibility":          stringFromAny(firstAny(metadata["visibility"], "internal_only")),
		"scope":               stringFromAny(firstAny(metadata["scope"], metadata["retrieval_scope"], "generic")),
		"policy_type":         stringFromAny(firstAny(metadata["policy_type"], metadata["document_type"], payload["document_type"])),
		"authority_level":     stringFromAny(firstAny(metadata["authority_level"], "policy")),
		"authority_priority":  authorityPriority(stringFromAny(firstAny(metadata["authority_level"], "policy"))),
		"vertical":            metadata["vertical"],
		"category":            metadata["category"],
		"collections":         firstAny(metadata["collections"], metadata["collection_slug"]),
		"tags":                metadata["tags"],
		"case_reasons":        metadata["case_reasons"],
		"risk_level":          metadata["risk_level"],
		"risk_priority":       riskPriority(stringFromAny(metadata["risk_level"])),
		"effective_from":      metadata["effective_from"],
		"updated_at":          updatedAt,
	}
	if err := s.meiliRequest(ctx, http.MethodPost, "/indexes/ai_documents/documents?primaryKey=document_id", []map[string]any{doc}, nil); err != nil {
		return err
	}
	if err := s.meiliRequest(ctx, http.MethodPost, "/indexes/sop_documents/documents?primaryKey=document_id", []map[string]any{doc}, nil); err != nil {
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
	if err := s.meiliRequest(ctx, http.MethodDelete, "/indexes/ai_documents/documents/"+documentID, nil, nil); err != nil {
		return err
	}
	return s.meiliRequest(ctx, http.MethodDelete, "/indexes/sop_documents/documents/"+documentID, nil, nil)
}

func (s *Store) DeleteAIChunksFromMeili(ctx context.Context, documentID string) error {
	if documentID == "" {
		return nil
	}
	_ = s.ensureMeiliIndex(ctx, "ai_chunks", aiChunkFilterableAttributes())
	_ = s.ensureMeiliIndex(ctx, "sop_chunks", sopChunkFilterableAttributes())
	payload := map[string]string{"filter": `document_id = "` + documentID + `"`}
	if err := s.meiliRequest(ctx, http.MethodPost, "/indexes/ai_chunks/documents/delete", payload, nil); err != nil {
		return err
	}
	return s.meiliRequest(ctx, http.MethodPost, "/indexes/sop_chunks/documents/delete", payload, nil)
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
		if !indexableAIChunk(chunkMetadata) {
			continue
		}
		chunkType := stringFromAny(firstAny(chunkMetadata["chunk_type"], chunkMetadata["unit_type"], chunk.Section))
		authorityLevel := stringFromAny(firstAny(chunkMetadata["authority_level"], "policy"))
		riskLevel := stringFromAny(chunkMetadata["risk_level"])
		docs = append(docs, aiChunkDocument{
			ChunkID:            chunk.ChunkID,
			ID:                 chunk.ChunkID,
			DocumentID:         documentID,
			VersionID:          versionID,
			DocumentVersionID:  versionID,
			Title:              fmt.Sprint(payload["title"]),
			NormalizedTitle:    normalize(fmt.Sprint(firstAny(chunk.Heading, payload["title"]))),
			VersionNumber:      intFromAny(payload["version_number"]),
			Status:             fmt.Sprint(payload["status"]),
			PublishState:       fmt.Sprint(payload["publish_state"]),
			DocumentType:       fmt.Sprint(payload["document_type"]),
			ReviewStatus:       fmt.Sprint(payload["review_status"]),
			IsCurrentVersion:   true,
			Metadata:           chunkMetadata,
			ChunkIndex:         chunk.ChunkIndex,
			Section:            chunk.Section,
			SectionPath:        firstAny(chunkMetadata["section_path"], []string{}),
			Heading:            chunk.Heading,
			Content:            chunk.Content,
			DisplayText:        stringFromAny(firstAny(chunkMetadata["display_text"], chunk.Content)),
			RetrievalText:      stringFromAny(firstAny(chunkMetadata["retrieval_text"], chunk.Content)),
			SourceText:         stringFromAny(firstAny(chunkMetadata["source_text"], chunk.Content)),
			TokenCount:         chunk.TokenCount,
			UnitType:           stringFromAny(firstAny(chunkMetadata["unit_type"], chunk.Section)),
			ChunkType:          chunkType,
			StepCode:           stringFromAny(chunkMetadata["step_code"]),
			Phase:              stringFromAny(chunkMetadata["phase"]),
			Lane:               stringFromAny(firstAny(chunkMetadata["lane"], chunkMetadata["actor"])),
			PathTitle:          stringFromAny(firstAny(chunkMetadata["path_title"], chunkMetadata["section_title"])),
			PathSteps:          firstAny(chunkMetadata["path_steps"], chunkMetadata["step_codes"], []string{}),
			RiskLevel:          riskLevel,
			RiskPriority:       riskPriority(riskLevel),
			SourceRefQuality:   stringFromAny(chunkMetadata["source_ref_quality"]),
			SourceRefs:         firstAny(chunkMetadata["source_refs"], []map[string]any{}),
			ParentSectionID:    stringFromAny(chunkMetadata["parent_section_id"]),
			ParentChunkID:      stringFromAny(chunkMetadata["parent_chunk_id"]),
			Audience:           chunkMetadata["audience"],
			Visibility:         stringFromAny(firstAny(chunkMetadata["visibility"], "internal_only")),
			Scope:              stringFromAny(firstAny(chunkMetadata["scope"], chunkMetadata["retrieval_scope"], "generic")),
			PolicyType:         stringFromAny(firstAny(chunkMetadata["policy_type"], chunkType)),
			AuthorityLevel:     authorityLevel,
			AuthorityPriority:  authorityPriority(authorityLevel),
			Vertical:           chunkMetadata["vertical"],
			Category:           chunkMetadata["category"],
			Collections:        firstAny(chunkMetadata["collections"], chunkMetadata["collection_slug"]),
			Tags:               chunkMetadata["tags"],
			CaseReasons:        chunkMetadata["case_reasons"],
			MacroText:          stringFromAny(firstAny(chunkMetadata["macro_text"], conditionalText(chunkType, chunk.Content, "macro"))),
			ForbiddenPhrases:   firstAny(chunkMetadata["forbidden_phrases"], []string{}),
			Keywords:           firstAny(chunkMetadata["keywords"], chunkMetadata["aliases"], []string{}),
			EffectiveFrom:      firstAny(chunkMetadata["effective_from"], metadata["effective_from"]),
			RequiresReview:     boolFromAny(chunkMetadata["requires_human_review"]) || stringFromAny(chunkMetadata["review_status"]) == "needs_review",
			PublishBlocked:     boolFromAny(chunkMetadata["publish_blocked"]),
			SourceEvidenceOnly: boolFromAny(chunkMetadata["source_evidence_only"]),
			UpdatedAt:          time.Now().UTC(),
		})
	}
	if len(docs) == 0 {
		s.logger.WarnContext(ctx, "AI chunks fetch returned no chunks", "document_id", documentID, "version_id", versionID)
		return nil
	}
	if err := s.ensureMeiliIndex(ctx, "ai_chunks", aiChunkFilterableAttributes()); err != nil {
		return err
	}
	if err := s.ensureMeiliIndex(ctx, "sop_chunks", sopChunkFilterableAttributes()); err != nil {
		return err
	}
	if err := s.meiliRequest(ctx, http.MethodPost, "/indexes/ai_chunks/documents?primaryKey=chunk_id", docs, nil); err != nil {
		return err
	}
	if err := s.meiliRequest(ctx, http.MethodPost, "/indexes/sop_chunks/documents?primaryKey=chunk_id", docs, nil); err != nil {
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

func (s *Store) ClearSearchIndexes(ctx context.Context) map[string]string {
	indexes := []string{"sops", "ai_documents", "ai_chunks", "sop_documents", "sop_chunks"}
	results := make(map[string]string, len(indexes))
	for _, index := range indexes {
		if err := s.meiliRequest(ctx, http.MethodDelete, "/indexes/"+index+"/documents", nil, nil); err != nil {
			results[index] = err.Error()
			s.logger.WarnContext(ctx, "clear meilisearch index failed", "index", index, "error", err)
			continue
		}
		results[index] = "cleared"
	}
	return results
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
	chunkResults, chunkErr := s.searchMeiliChunks(ctx, req)
	sopResults, sopErr := s.searchMeiliSOPs(ctx, req)
	if chunkErr != nil && sopErr != nil {
		return nil, chunkErr
	}
	results := make([]model.SearchResult, 0, len(chunkResults)+len(sopResults))
	seen := map[string]bool{}
	for _, result := range chunkResults {
		key := "chunk:" + result.ChunkID
		if result.ChunkID == "" {
			key = "doc:" + result.DocumentID + ":" + result.Title
		}
		if seen[key] {
			continue
		}
		seen[key] = true
		results = append(results, result)
	}
	for _, result := range sopResults {
		key := "sop:" + result.SOPID
		if seen[key] {
			continue
		}
		seen[key] = true
		results = append(results, result)
	}
	return results, nil
}

func (s *Store) searchMeiliChunks(ctx context.Context, req model.SearchRequest) ([]model.SearchResult, error) {
	payload := map[string]any{
		"q":                req.Query,
		"limit":            30,
		"showRankingScore": true,
	}
	if req.Debug {
		payload["showRankingScoreDetails"] = true
	}
	filter := combineMeiliFilters("status = \"published\"", "is_current_version = true", meiliFilter(req.Filters))
	if filter != "" {
		payload["filter"] = filter
	}
	var decoded meiliChunkSearchResponse
	if err := s.meiliRequest(ctx, http.MethodPost, "/indexes/sop_chunks/search", payload, &decoded); err != nil {
		return nil, err
	}
	results := make([]model.SearchResult, 0, len(decoded.Hits))
	for index, hit := range decoded.Hits {
		confidence := hit.RankingScore
		if confidence <= 0 {
			confidence = 1 - float64(index)*0.06
		}
		if confidence < 0.18 {
			confidence = 0.18
		}
		debug := map[string]any(nil)
		if req.Debug {
			debug = map[string]any{
				"score_debug": map[string]any{
					"meili_score":           hit.RankingScore,
					"ranking_score_details": hit.RankingScoreDetails,
					"rank":                  index + 1,
					"mode":                  "portal_search",
					"index":                 "sop_chunks",
				},
			}
		}
		results = append(results, aiChunkToSearchResult(hit, confidence, debug))
	}
	return results, nil
}

func (s *Store) searchMeiliSOPs(ctx context.Context, req model.SearchRequest) ([]model.SearchResult, error) {
	payload := map[string]any{
		"q":                req.Query,
		"limit":            20,
		"showRankingScore": true,
	}
	if req.Debug {
		payload["showRankingScoreDetails"] = true
	}
	if filter := meiliFilter(req.Filters); filter != "" {
		payload["filter"] = filter
	}
	var decoded meiliSOPSearchResponse
	if err := s.meiliRequest(ctx, http.MethodPost, "/indexes/sops/search", payload, &decoded); err != nil {
		return nil, err
	}
	results := make([]model.SearchResult, 0, len(decoded.Hits))
	for index, hit := range decoded.Hits {
		confidence := hit.RankingScore
		if confidence <= 0 {
			confidence = 1 - float64(index)*0.06
		}
		if confidence < 0.18 {
			confidence = 0.18
		}
		debug := map[string]any(nil)
		if req.Debug {
			debug = map[string]any{
				"score_debug": map[string]any{
					"meili_score":           hit.RankingScore,
					"ranking_score_details": hit.RankingScoreDetails,
					"rank":                  index + 1,
					"mode":                  "portal_search",
					"index":                 "sops",
				},
			}
		}
		results = append(results, model.SearchResult{
			SOPID: hit.SOPID, ResultType: "sop_catalog", Title: hit.Title, Snippet: hit.Snippet, Category: hit.Category,
			Audience: hit.Audience, Vertical: hit.Vertical, Tags: hit.Tags, UpdatedAt: hit.UpdatedAt,
			Version: hit.Version, Confidence: confidence, Score: confidence, Debug: debug,
		})
	}
	return results, nil
}

func (s *Store) ensureMeiliIndex(ctx context.Context, index string, filterable []string) error {
	_ = s.meiliRequest(ctx, http.MethodPost, "/indexes", map[string]string{"uid": index}, nil)
	settings := map[string]any{
		"filterableAttributes": filterable,
		"sortableAttributes":   sortableAttributesForIndex(index),
	}
	if searchable := searchableAttributesForIndex(index); len(searchable) > 0 {
		settings["searchableAttributes"] = searchable
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
		SOPID: sop.ID, ResultType: "sop_catalog", Title: sop.Title, Snippet: sop.Summary, Category: sop.Category,
		Audience: sop.Audience, Vertical: sop.Vertical, Tags: sop.Tags, UpdatedAt: sop.UpdatedAt,
		Version: sop.CurrentVersion.VersionNumber, Confidence: confidence,
	}
}

func aiChunkToSearchResult(chunk aiChunkDocument, confidence float64, debug map[string]any) model.SearchResult {
	snippet := stringFromAny(firstAny(chunk.DisplayText, chunk.Content, chunk.RetrievalText))
	if strings.TrimSpace(snippet) == "" {
		snippet = chunk.Heading
	}
	title := strings.TrimSpace(chunk.Title)
	if title == "" {
		title = strings.TrimSpace(chunk.Heading)
	}
	return model.SearchResult{
		SOPID:             chunk.DocumentID,
		ResultType:        "sop_chunk",
		DocumentID:        chunk.DocumentID,
		DocumentVersionID: chunk.DocumentVersionID,
		VersionID:         chunk.VersionID,
		ChunkID:           chunk.ChunkID,
		Title:             title,
		Snippet:           truncateString(snippet, 700),
		Category:          stringFromAny(chunk.Category),
		Audience:          stringSliceFromAny(chunk.Audience),
		Vertical:          firstStringFromAny(chunk.Vertical),
		Tags:              stringSliceFromAny(chunk.Tags),
		Collections:       stringSliceFromAny(chunk.Collections),
		SectionPath:       stringSliceFromAny(chunk.SectionPath),
		ChunkType:         chunk.ChunkType,
		RiskLevel:         chunk.RiskLevel,
		SourceRefs:        chunk.SourceRefs,
		UpdatedAt:         timeFromAny(chunk.UpdatedAt),
		Version:           chunk.VersionNumber,
		Confidence:        confidence,
		Score:             confidence,
		Debug:             debug,
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
	add("collections", filters.Collections)
	add("visibility", filters.Visibility)
	add("scope", filters.Scope)
	add("policy_type", filters.PolicyType)
	add("authority_level", filters.AuthorityLevel)
	return strings.Join(parts, " AND ")
}

func combineMeiliFilters(filters ...string) string {
	parts := make([]string, 0, len(filters))
	for _, filter := range filters {
		filter = strings.TrimSpace(filter)
		if filter == "" {
			continue
		}
		parts = append(parts, "("+filter+")")
	}
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

func stringFromAny(value any) string {
	switch typed := value.(type) {
	case string:
		return typed
	case []string:
		return strings.Join(typed, ", ")
	case []any:
		values := make([]string, 0, len(typed))
		for _, item := range typed {
			text := strings.TrimSpace(stringFromAny(item))
			if text != "" {
				values = append(values, text)
			}
		}
		return strings.Join(values, ", ")
	case fmt.Stringer:
		return typed.String()
	case nil:
		return ""
	default:
		return fmt.Sprint(typed)
	}
}

func stringSliceFromAny(value any) []string {
	switch typed := value.(type) {
	case []string:
		return typed
	case []any:
		output := make([]string, 0, len(typed))
		for _, item := range typed {
			text := strings.TrimSpace(stringFromAny(item))
			if text != "" {
				output = append(output, text)
			}
		}
		return output
	case string:
		text := strings.TrimSpace(typed)
		if text == "" {
			return nil
		}
		return []string{text}
	default:
		text := strings.TrimSpace(stringFromAny(value))
		if text == "" {
			return nil
		}
		return []string{text}
	}
}

func firstStringFromAny(value any) string {
	values := stringSliceFromAny(value)
	if len(values) == 0 {
		return ""
	}
	return values[0]
}

func timeFromAny(value any) time.Time {
	switch typed := value.(type) {
	case time.Time:
		return typed
	case string:
		for _, layout := range []string{time.RFC3339Nano, time.RFC3339, "2006-01-02"} {
			parsed, err := time.Parse(layout, typed)
			if err == nil {
				return parsed
			}
		}
	default:
		text := strings.TrimSpace(stringFromAny(value))
		if text != "" && text != "<nil>" {
			return timeFromAny(text)
		}
	}
	return time.Time{}
}

func truncateString(value string, maxLength int) string {
	value = strings.TrimSpace(value)
	if maxLength <= 0 || len([]rune(value)) <= maxLength {
		return value
	}
	runes := []rune(value)
	return strings.TrimSpace(string(runes[:maxLength])) + "..."
}

func firstAny(values ...any) any {
	for _, value := range values {
		if strings.TrimSpace(stringFromAny(value)) != "" {
			return value
		}
	}
	return ""
}

func indexableAIChunk(metadata map[string]any) bool {
	unitType := strings.TrimSpace(stringFromAny(metadata["unit_type"]))
	if unitType == "" {
		return false
	}
	if unitType == "source_evidence_section" || unitType == "visual_source_block" || strings.HasPrefix(unitType, "candidate_") {
		return false
	}
	if boolFromAny(metadata["publish_blocked"]) || boolFromAny(metadata["source_evidence_only"]) {
		return false
	}
	if strings.TrimSpace(stringFromAny(metadata["review_status"])) != "approved" {
		return false
	}
	extractionStatus := strings.TrimSpace(stringFromAny(metadata["extraction_status"]))
	if extractionStatus != "structured" && extractionStatus != "manually_curated" {
		return false
	}
	if workflowVisualChunkNeedsBBox(unitType) && !hasWorkflowPageBBoxSourceRef(metadata["source_refs"]) {
		return false
	}
	return true
}

func workflowVisualChunkNeedsBBox(unitType string) bool {
	switch unitType {
	case "workflow_step", "decision_node", "decision_branch", "workflow_path", "script_block", "annotation", "relation_to_sop":
		return true
	default:
		return false
	}
}

func boolFromAny(value any) bool {
	switch typed := value.(type) {
	case bool:
		return typed
	case string:
		switch strings.ToLower(strings.TrimSpace(typed)) {
		case "1", "true", "yes", "on":
			return true
		default:
			return false
		}
	default:
		return false
	}
}

func hasWorkflowPageBBoxSourceRef(value any) bool {
	switch refs := value.(type) {
	case []any:
		for _, ref := range refs {
			if workflowRefHasPageBBox(ref) {
				return true
			}
		}
	case []map[string]any:
		for _, ref := range refs {
			if workflowRefHasPageBBox(ref) {
				return true
			}
		}
	}
	return false
}

func workflowRefHasPageBBox(value any) bool {
	ref, ok := value.(map[string]any)
	if !ok {
		return false
	}
	if intFromAny(firstAny(ref["page"], ref["page_number"])) <= 0 {
		return false
	}
	bbox, ok := ref["bbox"].([]any)
	if !ok || len(bbox) < 4 {
		return false
	}
	x1, y1, x2, y2 := floatFromAny(bbox[0]), floatFromAny(bbox[1]), floatFromAny(bbox[2]), floatFromAny(bbox[3])
	return x2 > x1 && y2 > y1
}

func floatFromAny(value any) float64 {
	switch typed := value.(type) {
	case float64:
		return typed
	case float32:
		return float64(typed)
	case int:
		return float64(typed)
	case int64:
		return float64(typed)
	case json.Number:
		output, _ := typed.Float64()
		return output
	default:
		return 0
	}
}

func aiChunkFilterableAttributes() []string {
	return []string{
		"document_id",
		"version_id",
		"document_version_id",
		"document_type",
		"status",
		"publish_state",
		"is_current_version",
		"review_status",
		"requires_review",
		"publish_blocked",
		"source_evidence_only",
		"vertical",
		"category",
		"collections",
		"audience",
		"visibility",
		"scope",
		"policy_type",
		"authority_level",
		"tags",
		"case_reasons",
		"phase",
		"lane",
		"unit_type",
		"chunk_type",
		"risk_level",
		"source_ref_quality",
		"parent_section_id",
		"parent_chunk_id",
	}
}

func sopChunkFilterableAttributes() []string {
	return aiChunkFilterableAttributes()
}

func aiDocumentFilterableAttributes() []string {
	return []string{"status", "publish_state", "is_current_version", "vertical", "category", "collections", "audience", "visibility", "scope", "policy_type", "authority_level", "risk_level", "tags", "case_reasons"}
}

func sopDocumentFilterableAttributes() []string {
	return aiDocumentFilterableAttributes()
}

func searchableAttributesForIndex(index string) []string {
	switch index {
	case "ai_chunks", "sop_chunks":
		return []string{"title", "normalized_title", "macro_text", "forbidden_phrases", "section_path", "heading", "step_code", "source_text", "display_text", "content", "retrieval_text", "phase", "lane", "path_title", "path_steps", "keywords"}
	case "ai_documents", "sop_documents":
		return []string{"title", "summary", "section_titles", "category", "collections", "tags", "case_reasons"}
	case "sops":
		return []string{"title", "snippet", "category", "tags", "case_reasons"}
	default:
		return nil
	}
}

func sortableAttributesForIndex(index string) []string {
	switch index {
	case "ai_chunks", "sop_chunks":
		return []string{"updated_at", "risk_priority", "authority_priority"}
	case "ai_documents", "sop_documents":
		return []string{"updated_at", "risk_priority", "authority_priority", "effective_from"}
	default:
		return []string{"updated_at"}
	}
}

func riskPriority(value string) int {
	switch normalize(value) {
	case "critical":
		return 4
	case "high":
		return 3
	case "medium":
		return 2
	case "low":
		return 1
	default:
		return 0
	}
}

func authorityPriority(value string) int {
	switch normalize(value) {
	case "source of truth", "source_of_truth":
		return 5
	case "policy":
		return 4
	case "procedure":
		return 3
	case "reference":
		return 2
	case "example":
		return 1
	case "deprecated":
		return -2
	default:
		return 0
	}
}

func conditionalText(chunkType string, content string, expected string) string {
	if strings.Contains(normalize(chunkType), normalize(expected)) {
		return content
	}
	return ""
}
