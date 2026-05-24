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

func TestPortalChunkSearchQueriesRewritePhoneLookupToAbbreviationAndEntity(t *testing.T) {
	got := portalChunkSearchQueries("số điện thoại taxi thành lợi")
	want := []string{
		"số điện thoại taxi thành lợi",
		"sdt taxi thành lợi",
		"sđt taxi thành lợi",
		"taxi thành lợi",
	}
	if len(got) != len(want) {
		t.Fatalf("expected %v, got %v", want, got)
	}
	for index := range want {
		if got[index] != want[index] {
			t.Fatalf("expected %v, got %v", want, got)
		}
	}
}

func TestRerankPortalChunkHitsPromotesExactPhoneRowOverBroadPhonePolicy(t *testing.T) {
	hits := []aiChunkDocument{
		{
			ChunkID:      "broad-policy",
			Title:        "Quy định xác minh tài khoản TX, KH",
			Heading:      "Liên hệ qua số điện thoại khác",
			Content:      "CS xử lý yêu cầu liên hệ qua số điện thoại khác của tài xế.",
			RankingScore: 0.61,
		},
		{
			ChunkID:         "taxi-row",
			Title:           "Quy định xác minh tài khoản TX, KH",
			NormalizedTitle: "sdt hang taxi thanh loi",
			Heading:         "SĐT hãng Taxi Thành Lợi",
			DisplayText:     "Tên Hãng: Thành Lợi; SĐT: 0243551551",
			Content:         "Tên Hãng: Thành Lợi; SĐT: 0243551551",
			RankingScore:    0.49,
		},
	}

	ranked := rerankPortalChunkHits("số điện thoại taxi thành lợi", hits)

	if ranked[0].ChunkID != "taxi-row" {
		t.Fatalf("expected taxi row first, got %#v", ranked)
	}
}
