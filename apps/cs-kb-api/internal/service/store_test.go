package service

import "testing"

func TestIndexableAIChunkRejectsNonProductionChunks(t *testing.T) {
	cases := []struct {
		name     string
		metadata map[string]any
	}{
		{
			name: "publish blocked",
			metadata: map[string]any{
				"unit_type":         "workflow_step",
				"review_status":     "approved",
				"extraction_status": "structured",
				"publish_blocked":   true,
				"source_refs":       []any{map[string]any{"page": 1, "bbox": []any{1, 2, 3, 4}}},
			},
		},
		{
			name: "source evidence only",
			metadata: map[string]any{
				"unit_type":            "source_evidence_section",
				"review_status":        "approved",
				"extraction_status":    "structured",
				"source_evidence_only": true,
			},
		},
		{
			name: "needs review",
			metadata: map[string]any{
				"unit_type":         "workflow_step",
				"review_status":     "needs_review",
				"extraction_status": "structured",
				"source_refs":       []any{map[string]any{"page": 1, "bbox": []any{1, 2, 3, 4}}},
			},
		},
		{
			name: "degraded fallback",
			metadata: map[string]any{
				"unit_type":         "workflow_step",
				"review_status":     "approved",
				"extraction_status": "degraded",
				"source_refs":       []any{map[string]any{"page": 1, "bbox": []any{1, 2, 3, 4}}},
			},
		},
		{
			name: "visual source block",
			metadata: map[string]any{
				"unit_type":         "visual_source_block",
				"review_status":     "approved",
				"extraction_status": "structured",
				"source_refs":       []any{map[string]any{"page": 1, "bbox": []any{1, 2, 3, 4}}},
			},
		},
		{
			name: "workflow visual chunk without bbox",
			metadata: map[string]any{
				"unit_type":         "decision_branch",
				"review_status":     "approved",
				"extraction_status": "structured",
				"source_refs":       []any{map[string]any{"page": 1}},
			},
		},
	}

	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			if indexableAIChunk(tc.metadata) {
				t.Fatalf("expected %s to be excluded from Meilisearch", tc.name)
			}
		})
	}
}

func TestIndexableAIChunkAllowsApprovedStructuredWorkflowChunkWithBBox(t *testing.T) {
	metadata := map[string]any{
		"unit_type":         "decision_branch",
		"review_status":     "approved",
		"extraction_status": "structured",
		"source_refs":       []any{map[string]any{"page": 1, "bbox": []any{1, 2, 3, 4}}},
	}

	if !indexableAIChunk(metadata) {
		t.Fatal("expected approved structured workflow chunk with bbox to be indexable")
	}
}
