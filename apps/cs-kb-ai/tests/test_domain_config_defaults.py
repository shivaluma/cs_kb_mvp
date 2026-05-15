from __future__ import annotations

import unittest
from unittest.mock import patch

from app import repository
from app.chat import active_channel_terms, query_intent
from app.ingestion import sheet_mapping_for_name
from app.retrieval import rerank_by_query_intent


class DomainConfigDefaultsTest(unittest.TestCase):
    def tearDown(self) -> None:
        repository.clear_domain_config_cache()

    def test_empty_db_config_falls_back_to_domain_defaults(self) -> None:
        repository.clear_domain_config_cache()
        with patch("app.repository.load_active_taxonomy_terms", return_value=[]):
            terms = repository.active_taxonomy_terms()

        self.assertIn("hotline", {term["term_key"] for term in terms})

    def test_active_taxonomy_overrides_default_intent_patterns(self) -> None:
        custom_terms = [
            {
                "term_key": "zalo_support",
                "term_type": "chat_intent",
                "display_name": "Zalo support",
                "aliases": ["zalo"],
                "metadata": {},
            }
        ]

        with patch("app.chat.repository.active_taxonomy_terms", return_value=custom_terms):
            self.assertEqual(query_intent("khach nhan qua zalo"), {"zalo_support"})
            self.assertNotIn("hotline", query_intent("hotline"))

    def test_new_channel_term_can_be_added_without_code_change(self) -> None:
        custom_terms = [
            {
                "term_key": "zalo_support",
                "term_type": "chat_intent",
                "display_name": "Zalo support",
                "aliases": ["zalo"],
                "metadata": {},
            }
        ]
        custom_groups = [
            {
                "group_key": "channels",
                "group_type": "channel",
                "display_name": "Channels",
                "term_keys": ["zalo_support"],
            }
        ]

        with (
            patch("app.chat.repository.active_taxonomy_terms", return_value=custom_terms),
            patch("app.chat.repository.active_taxonomy_groups", return_value=custom_groups),
        ):
            self.assertEqual(query_intent("zalo"), {"zalo_support"})
            self.assertIn("zalo_support", active_channel_terms())

    def test_sheet_mapping_can_be_added_without_code_change(self) -> None:
        custom_rules = [
            {
                "rule_key": "zalo_queue",
                "match_type": "contains",
                "pattern": "zalo",
                "sheet_kind": "issue_router",
                "collection_slug": "social-call-email-handling",
                "collection_name": "Social / Call / Email Handling",
                "collection_type": "channel",
                "priority": 1,
                "status": "active",
            }
        ]

        with patch("app.ingestion.repository.active_sheet_mapping_rules", return_value=custom_rules):
            mapping = sheet_mapping_for_name("Zalo Queue")

        self.assertEqual(mapping["sheet_kind"], "issue_router")
        self.assertEqual(mapping["collection_slug"], "social-call-email-handling")

    def test_relation_pattern_can_be_added_without_code_change(self) -> None:
        custom_patterns = [
            {
                "pattern_key": "handoff_to_queue",
                "pattern": r"handoff sang (?P<title>[A-Za-z0-9 _-]{3,80})",
                "relation_type": "routes_to",
                "relation_source": "configured_test_pattern",
                "priority": 1,
                "status": "active",
            }
        ]

        with patch("app.repository.active_relation_patterns", return_value=custom_patterns):
            relations = repository.relation_items_from_text("Rule", "handoff sang Zalo Queue khi quá SLA")

        self.assertEqual(relations[0]["relation_type"], "routes_to")
        self.assertEqual(relations[0]["relation_source"], "configured_test_pattern")
        self.assertIn("Zalo Queue", relations[0]["target_title"])

    def test_rerank_rule_change_affects_score_trace(self) -> None:
        rows = [
            {
                "chunk_id": "exact",
                "heading": "Exact",
                "content": "zalo queue",
                "section": "policy_rule",
                "metadata": {"unit_type": "policy_rule"},
                "score": 0.01,
                "lexical_score": 0.1,
                "vector_score": 0.0,
                "rank_source": ["lexical"],
                "best_rank": 1,
            }
        ]
        rules = {
            "retrieval_exact_phrase": {"weight": 0.5, "params": {}, "rule_type": "bonus"},
            "retrieval_metadata_overlap": {"weight": 0, "params": {"cap": 0}},
            "retrieval_text_overlap": {"weight": 0, "params": {"cap": 0}},
            "retrieval_text_coverage": {"weight": 0, "params": {"cap": 0}},
            "retrieval_action_metadata_bonus": {"weight": 0, "params": {}},
        }

        with patch("app.retrieval.repository.rerank_rule_weights", return_value=rules):
            reranked = rerank_by_query_intent("zalo queue", rows)

        self.assertEqual(reranked[0]["intent_boost"], 0.5)
        self.assertEqual(reranked[0]["intent_boost_trace"][0]["rule_key"], "retrieval_exact_phrase")

    def test_draft_and_suggested_config_rows_are_not_active(self) -> None:
        rows = [
            {"rule_key": "draft", "status": "draft"},
            {"rule_key": "suggested", "status": "suggested"},
            {"rule_key": "active", "status": "active"},
        ]

        self.assertEqual(repository.active_domain_rows(rows), [{"rule_key": "active", "status": "active"}])


if __name__ == "__main__":
    unittest.main()
