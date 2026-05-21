package model

import "time"

type SOP struct {
	ID               string     `json:"id"`
	Code             string     `json:"code"`
	Title            string     `json:"title"`
	Summary          string     `json:"summary"`
	Audience         []string   `json:"audience"`
	Vertical         string     `json:"vertical"`
	Category         string     `json:"category"`
	Tags             []string   `json:"tags"`
	CaseReasons      []string   `json:"case_reasons"`
	Status           string     `json:"status"`
	CurrentVersionID string     `json:"current_version_id"`
	OwnerTeam        string     `json:"owner_team"`
	UpdatedAt        time.Time  `json:"updated_at"`
	CurrentVersion   SOPVersion `json:"current_version"`
	Analytics        SOPMetrics `json:"analytics"`
}

type SOPVersion struct {
	ID            string      `json:"id"`
	SOPID         string      `json:"sop_id"`
	VersionNumber int         `json:"version_number"`
	Status        string      `json:"status"`
	EffectiveFrom time.Time   `json:"effective_from"`
	CreatedBy     string      `json:"created_by"`
	ApprovedBy    string      `json:"approved_by"`
	ChangeSummary string      `json:"change_summary"`
	Sections      SOPSections `json:"sections"`
	PublishedAt   time.Time   `json:"published_at"`
}

type SOPSections struct {
	WhenToApply      string   `json:"when_to_apply"`
	InputRequirement string   `json:"input_requirements"`
	Checklist        []string `json:"checklist"`
	AgentScript      string   `json:"agent_script"`
	MacroResponses   []Macro  `json:"macro_response"`
	SLA              string   `json:"sla,omitempty"`
	Escalation       string   `json:"escalation,omitempty"`
	RelatedPolicies  []string `json:"related_policies,omitempty"`
}

type Macro struct {
	Title   string `json:"title"`
	Content string `json:"content"`
}

type SOPMetrics struct {
	Views      int `json:"views"`
	MacroCopy  int `json:"macro_copy"`
	Helpful    int `json:"helpful"`
	NotHelpful int `json:"not_helpful"`
}

type HealthStatus struct {
	Name      string `json:"name"`
	Status    string `json:"status"`
	LatencyMS int64  `json:"latency_ms"`
	Detail    string `json:"detail"`
}

type SearchRequest struct {
	Query           string        `json:"query"`
	Filters         SearchFilters `json:"filters"`
	IncludeSemantic bool          `json:"include_semantic"`
}

type SearchFilters struct {
	Audience    []string `json:"audience"`
	Vertical    []string `json:"vertical"`
	Category    []string `json:"category"`
	Tags        []string `json:"tags"`
	CaseReasons []string `json:"case_reasons"`
	Collections []string `json:"collections"`
	TaskTypes   []string `json:"task_types"`
	UnitTypes   []string `json:"unit_types"`
}

type SearchResponse struct {
	Query           string           `json:"query"`
	Results         []SearchResult   `json:"results"`
	SemanticResults []SemanticResult `json:"semantic_results,omitempty"`
	Total           int              `json:"total"`
	LatencyMS       int64            `json:"latency_ms"`
	UsedModes       []string         `json:"used_modes"`
	Suggestions     []string         `json:"suggestions"`
}

type SearchResult struct {
	SOPID      string    `json:"sop_id"`
	Title      string    `json:"title"`
	Snippet    string    `json:"snippet"`
	Category   string    `json:"category"`
	Audience   []string  `json:"audience"`
	Vertical   string    `json:"vertical"`
	Tags       []string  `json:"tags"`
	UpdatedAt  time.Time `json:"updated_at"`
	Version    int       `json:"version"`
	Confidence float64   `json:"confidence"`
}

type SemanticResult struct {
	DocumentID           string          `json:"document_id"`
	VersionID            string          `json:"version_id"`
	ChunkID              string          `json:"chunk_id"`
	Title                string          `json:"title"`
	SourceFile           string          `json:"source_filename"`
	VersionNumber        int             `json:"version_number"`
	ChunkIndex           int             `json:"chunk_index"`
	Section              string          `json:"section"`
	Heading              string          `json:"heading"`
	Content              string          `json:"content"`
	Score                float64         `json:"score"`
	RankSource           []string        `json:"rank_source"`
	Metadata             map[string]any  `json:"metadata"`
	SOPID                string          `json:"sop_id,omitempty"`
	DocumentTitle        string          `json:"document_title,omitempty"`
	SectionID            string          `json:"section_id,omitempty"`
	SectionTitle         string          `json:"section_title,omitempty"`
	Category             string          `json:"category,omitempty"`
	Collections          []CollectionRef `json:"collections,omitempty"`
	ChunkText            string          `json:"chunk_text,omitempty"`
	HighlightStartOffset *int            `json:"highlight_start_offset,omitempty"`
	HighlightEndOffset   *int            `json:"highlight_end_offset,omitempty"`
	DisplayContext       *DisplayContext `json:"display_context,omitempty"`
	SourceAnchor         SourceAnchor    `json:"source_anchor,omitempty"`
}

type CollectionRef struct {
	ID   string `json:"id"`
	Name string `json:"name"`
}

type DisplayHighlight struct {
	ChunkID       string       `json:"chunk_id"`
	Text          string       `json:"text"`
	StartOffset   *int         `json:"start_offset"`
	EndOffset     *int         `json:"end_offset"`
	MatchStrategy string       `json:"match_strategy"`
	SourceAnchor  SourceAnchor `json:"source_anchor"`
}

type DisplayBlock struct {
	ID           string       `json:"id"`
	Title        string       `json:"title"`
	Content      string       `json:"content"`
	UnitType     string       `json:"unit_type"`
	ChunkID      string       `json:"chunk_id"`
	BlockType    string       `json:"block_type"`
	SourceAnchor SourceAnchor `json:"source_anchor"`
}

type DisplayContext struct {
	DisplayUnitType        string             `json:"display_unit_type"`
	DocumentID             string             `json:"document_id"`
	DocumentTitle          string             `json:"document_title"`
	SectionID              string             `json:"section_id"`
	SectionTitle           string             `json:"section_title"`
	Category               string             `json:"category"`
	Collections            []CollectionRef    `json:"collections"`
	VersionNumber          *int               `json:"version_number"`
	LastUpdated            *time.Time         `json:"last_updated"`
	PublishedAt            *time.Time         `json:"published_at"`
	EffectiveDate          string             `json:"effective_date"`
	Content                string             `json:"content"`
	Blocks                 []DisplayBlock     `json:"blocks"`
	Highlights             []DisplayHighlight `json:"highlights"`
	FallbackExcerpt        string             `json:"fallback_excerpt"`
	HighlightFailed        bool               `json:"highlight_failed"`
	SourceAnchor           SourceAnchor       `json:"source_anchor"`
	SourceResolutionStatus string             `json:"source_resolution_status"`
	SourceResolutionReason string             `json:"source_resolution_reason"`
}

type SourceAnchor struct {
	SOPID        string `json:"sop_id"`
	SOPVersionID string `json:"sop_version_id"`
	SectionID    string `json:"section_id"`
	BlockID      string `json:"block_id"`
	TableID      string `json:"table_id"`
	RowIndex     *int   `json:"row_index"`
	ColumnKey    string `json:"column_key"`
}

type AISuggestRequest struct {
	Query string `json:"query"`
	SOPID string `json:"sop_id,omitempty"`
}

type AISuggestResponse struct {
	Answer        string           `json:"answer"`
	SuggestedSOPs []AISuggestedSOP `json:"suggested_sops"`
	Citations     []Citation       `json:"citations"`
	Warnings      []string         `json:"warnings"`
}

type AISuggestedSOP struct {
	SOPID      string  `json:"sop_id"`
	Title      string  `json:"title"`
	Version    int     `json:"version"`
	Confidence float64 `json:"confidence"`
}

type Citation struct {
	SOPID     string `json:"sop_id"`
	VersionID string `json:"version_id"`
	Section   string `json:"section"`
}
