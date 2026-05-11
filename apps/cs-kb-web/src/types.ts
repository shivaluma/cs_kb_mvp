export type Macro = {
  title: string;
  content: string;
};

export type SOP = {
  id: string;
  code: string;
  title: string;
  summary: string;
  audience: string[];
  vertical: string;
  category: string;
  tags: string[];
  case_reasons: string[];
  status: string;
  current_version_id: string;
  owner_team: string;
  updated_at: string;
  current_version: {
    id: string;
    version_number: number;
    status: string;
    change_summary: string;
    sections: {
      when_to_apply: string;
      input_requirements: string;
      checklist: string[];
      agent_script: string;
      macro_response: Macro[];
      sla?: string;
      escalation?: string;
      related_policies?: string[];
    };
  };
  analytics: {
    views: number;
    macro_copy: number;
    helpful: number;
    not_helpful: number;
  };
};

export type SearchResult = {
  sop_id: string;
  title: string;
  snippet: string;
  category: string;
  audience: string[];
  vertical: string;
  tags: string[];
  updated_at: string;
  version: number;
  confidence: number;
};

export type Homepage = {
  recently_updated: SOP[];
  most_viewed: SOP[];
  category_shortcuts: Array<{ key: string; label: string }>;
};

export type ServiceHealthStatus = "healthy" | "degraded" | "down" | "unknown" | "skipped";

export type ServiceHealth = {
  name: string;
  status: ServiceHealthStatus;
  latency_ms: number;
  detail: string;
};

export type SystemHealth = {
  status: ServiceHealthStatus;
  checked_at: string;
  services: ServiceHealth[];
};

export type AISuggestion = {
  answer: string;
  suggested_sops: Array<{
    sop_id: string;
    title: string;
    version: number;
    confidence: number;
  }>;
  citations: Array<{ sop_id: string; version_id: string; section: string }>;
  warnings: string[];
};

export type RetrievalResponse = {
  query: string;
  normalized_query: string;
  query_expansion: {
    strategy: string;
    expansions: string[];
    matched_synonyms: Array<{
      group_id: string;
      canonical_key: string;
      synonym_type: string;
      domain: string;
      audience: string;
      matched_terms: string[];
      matched_canonical: boolean;
    }>;
    active_synonym_group_count: number;
  };
  mode: "lexical" | "vector" | "hybrid";
  results: RetrievalResult[];
  citations: Citation[];
  warnings: string[];
  latency_ms: number;
};

export type ChatMessage = {
  role: "user" | "assistant";
  content: string;
};

export type ChatModelRoute = "simple" | "policy" | "high_risk" | "complex";

export type ChatModelRouteConfig = {
  route: ChatModelRoute;
  label: string;
  model: string;
  description: string;
};

export type ChatModelRoutesResponse = {
  default_route: ChatModelRoute;
  routes: ChatModelRouteConfig[];
  fallback_model: string;
};

export type GroundedChatResponse = {
  question: string;
  answer: string;
  steps: string[];
  warnings: string[];
  citations: Citation[];
  sources: RetrievalResult[];
  confidence: number;
  retrieval: RetrievalResponse;
  latency_ms: number;
  model_route: string;
  model_used: string;
  model_reason: string;
};

export type ChatThreadMessage = {
  id: string;
  role: "user" | "assistant";
  content: string;
  createdAt: string;
  response?: GroundedChatResponse;
  pending?: boolean;
};

export type RetrievalResult = {
  document_id: string;
  version_id: string;
  chunk_id: string;
  title: string;
  source_filename: string;
  version_number: number;
  chunk_index: number;
  section: string;
  heading: string;
  content: string;
  score: number;
  lexical_score: number;
  vector_score: number;
  rank_source: string[];
  metadata: Record<string, unknown>;
  citation: Citation;
};

export type Citation = {
  document_id: string;
  version_id: string;
  chunk_id: string;
  chunk_index: number;
  section: string;
  title: string;
  version_number: number;
  source_filename: string;
};

export type DocumentSummary = {
  document_id: string;
  external_id: string;
  title: string;
  source_filename: string;
  status: "active" | "archived";
  latest_version_id?: string;
  latest_version_number?: number;
  latest_version_status?: string;
  latest_document_type?: string;
  latest_review_status?: string;
  latest_extraction_confidence?: number;
  updated_at: string;
  metadata: Record<string, unknown>;
};

export type DocumentMetadataPreview = {
  title: string;
  suggested_metadata: {
    audience: string[];
    vertical: string;
    category: string;
    tags: string[];
    case_reasons: string[];
    owner_team: string;
    document_type: string;
    source_type: string;
    review_status: string;
    extraction_confidence: number;
  };
  document_type: string;
  source_type: string;
  extraction_confidence: number;
  chunk_count: number;
  warnings: string[];
  signals: Record<string, unknown>;
};

export type VersionSummary = {
  version_id: string;
  document_id: string;
  version_number: number;
  status: string;
  checksum: string;
  chunk_count: number;
  document_type?: string;
  review_status?: string;
  extraction_confidence?: number;
  change_summary: string;
  published_at?: string;
  archived_at?: string;
  created_at: string;
};

export type ExtractionUnit = {
  unit_id: string;
  document_id: string;
  version_id: string;
  unit_index: number;
  unit_type: string;
  title: string;
  content: string;
  source_sheet?: string;
  source_row?: number | null;
  source_page?: number | null;
  source_bbox?: number[];
  confidence: number;
  review_status: "needs_review" | "reviewed" | "approved";
  metadata: Record<string, unknown>;
};

export type ExtractionUnitUpdate = {
  title: string;
  content: string;
  unit_type: string;
  confidence: number;
  review_status: "needs_review" | "reviewed" | "approved";
  metadata: Record<string, unknown>;
  actor: string;
};

export type ExtractionUnitCreate = ExtractionUnitUpdate;

export type DocumentChunk = {
  chunk_id: string;
  document_id: string;
  version_id: string;
  chunk_index: number;
  section: string;
  heading: string;
  content: string;
  token_count: number;
  metadata: Record<string, unknown>;
  created_at: string;
};

export type ExtractionStageOutput = {
  id: string;
  job_id: string;
  stage: string;
  artifact_type: string;
  payload: Record<string, unknown>;
  status: string;
  error: string;
  created_at: string;
};

export type ExtractionJobSummary = {
  id: string;
  document_id: string;
  version_id: string;
  status: string;
  current_stage: string;
  source_type: string;
  document_type: string;
  risk_level: string;
  created_at: string;
  updated_at: string;
  outputs: ExtractionStageOutput[];
};

export type ExtractionStageInspection = {
  stage: string;
  output_count: number;
  statuses: string[];
  artifact_types: string[];
  errors: string[];
  warnings: string[];
  summary: string;
};

export type ExtractionPipelineInspection = {
  version_id: string;
  document_id: string;
  job_id: string;
  status: string;
  current_stage: string;
  source_type: string;
  document_type: string;
  risk_level: string;
  created_at?: string | null;
  updated_at?: string | null;
  stage_order: string[];
  stage_summary: ExtractionStageInspection[];
  issue_summary: {
    failed_output_count: number;
    degraded_output_count: number;
    warning_count: number;
    hard_blockers: string[];
    coverage_score?: number | null;
  };
  artifacts: ExtractionStageOutput[];
  summary_markdown: string;
};

export type VersionRawText = {
  version_id: string;
  document_id: string;
  title: string;
  version_number: number;
  status: string;
  raw_text: string;
  chunk_count: number;
  created_at: string;
};

export type SynonymTerm = {
  id?: string;
  term: string;
  normalized_term: string;
  language: string;
};

export type SynonymGroup = {
  id: string;
  canonical_key: string;
  synonym_type: "regular" | "one_way" | "typo_correction" | "placeholder";
  domain: string;
  audience: string;
  status: "draft" | "in_review" | "active" | "archived" | "rejected";
  created_by: string;
  approved_by?: string | null;
  terms: SynonymTerm[];
  created_at?: string;
  updated_at?: string;
};

export type SynonymSuggestion = {
  id: string;
  canonical_key: string;
  suggested_terms: string[];
  source: string;
  confidence: number;
  status: "pending" | "accepted" | "rejected" | "archived";
  evidence: Record<string, unknown>;
  created_at: string;
  updated_at: string;
};

export type FilterState = {
  audience: string;
  vertical: string;
  category: string;
};

export type UploadState = {
  file: File | null;
  title: string;
  externalId: string;
  status: "published" | "draft";
  vertical: string;
  category: string;
  audience: string;
  tags: string;
  caseReasons: string;
  ownerTeam: string;
  asyncExtraction: boolean;
};

export type SynonymDraft = {
  canonicalKey: string;
  synonymType: SynonymGroup["synonym_type"];
  status: SynonymGroup["status"];
  domain: string;
  audience: string;
  terms: string;
};
