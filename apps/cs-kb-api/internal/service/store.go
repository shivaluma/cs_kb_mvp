package service

import (
	"sort"
	"strings"
	"time"
	"unicode"

	"cs-kb-api/internal/model"
)

type MemoryStore struct {
	sops []model.SOP
}

func NewMemoryStore() *MemoryStore {
	return &MemoryStore{sops: seedSOPs()}
}

func (s *MemoryStore) ListSOPs() []model.SOP {
	result := make([]model.SOP, 0, len(s.sops))
	for _, sop := range s.sops {
		if sop.Status == "active" && sop.CurrentVersion.Status == "published" {
			result = append(result, sop)
		}
	}
	sort.Slice(result, func(i, j int) bool {
		return result[i].UpdatedAt.After(result[j].UpdatedAt)
	})
	return result
}

func (s *MemoryStore) GetSOP(id string) (model.SOP, bool) {
	for _, sop := range s.sops {
		if sop.ID == id && sop.Status == "active" && sop.CurrentVersion.Status == "published" {
			return sop, true
		}
	}
	return model.SOP{}, false
}

func (s *MemoryStore) Search(req model.SearchRequest) []model.SearchResult {
	query := normalize(req.Query)
	results := make([]model.SearchResult, 0)

	for _, sop := range s.ListSOPs() {
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

		results = append(results, model.SearchResult{
			SOPID:      sop.ID,
			Title:      sop.Title,
			Snippet:    sop.Summary,
			Category:   sop.Category,
			Audience:   sop.Audience,
			Vertical:   sop.Vertical,
			Tags:       sop.Tags,
			UpdatedAt:  sop.UpdatedAt,
			Version:    sop.CurrentVersion.VersionNumber,
			Confidence: clamp(score / 12),
		})
	}

	sort.Slice(results, func(i, j int) bool {
		return results[i].Confidence > results[j].Confidence
	})
	return results
}

func (s *MemoryStore) Popular(limit int) []model.SOP {
	sops := s.ListSOPs()
	sort.Slice(sops, func(i, j int) bool {
		return sops[i].Analytics.Views > sops[j].Analytics.Views
	})
	if len(sops) > limit {
		return sops[:limit]
	}
	return sops
}

func (s *MemoryStore) RecentlyUpdated(limit int) []model.SOP {
	sops := s.ListSOPs()
	if len(sops) > limit {
		return sops[:limit]
	}
	return sops
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
		sop.Code,
		sop.Title,
		sop.Summary,
		sop.Vertical,
		sop.Category,
		strings.Join(sop.Tags, " "),
		strings.Join(sop.CaseReasons, " "),
		sop.CurrentVersion.Sections.WhenToApply,
		sop.CurrentVersion.Sections.InputRequirement,
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
	if time.Since(sop.UpdatedAt) < 45*24*time.Hour {
		score += 0.5
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
