package http

import (
	"errors"
	"testing"
)

func TestIndexingVectorVerifiedRequiresAISignal(t *testing.T) {
	payload := map[string]any{"vector_index_verified": false}

	if indexingVectorVerified(payload, nil) {
		t.Fatal("expected vector verification to remain false when AI reports Qdrant sync failed")
	}
}

func TestIndexingVectorVerifiedAllowsLegacyPayload(t *testing.T) {
	payload := map[string]any{}

	if !indexingVectorVerified(payload, nil) {
		t.Fatal("expected legacy payload without vector signal to preserve previous behavior")
	}
}

func TestIndexingVectorVerifiedFailsOnLexicalError(t *testing.T) {
	payload := map[string]any{"vector_index_verified": true}

	if indexingVectorVerified(payload, errors.New("meili failed")) {
		t.Fatal("expected vector verification to fail when lexical indexing failed")
	}
}
