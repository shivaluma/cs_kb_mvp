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
	DocumentID    string         `json:"document_id"`
	VersionID     string         `json:"version_id"`
	ChunkID       string         `json:"chunk_id"`
	Title         string         `json:"title"`
	SourceFile    string         `json:"source_filename"`
	VersionNumber int            `json:"version_number"`
	ChunkIndex    int            `json:"chunk_index"`
	Section       string         `json:"section"`
	Heading       string         `json:"heading"`
	Content       string         `json:"content"`
	Score         float64        `json:"score"`
	RankSource    []string       `json:"rank_source"`
	Metadata      map[string]any `json:"metadata"`
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
