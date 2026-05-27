from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from app import repository
from app.schemas import DocumentMetadata, ExtractionUnitUpdateRequest, RetrievalFilters, SourceRef


class RepositoryGateTest(unittest.TestCase):
    def test_degraded_unit_requires_manual_curation(self) -> None:
        self.assertTrue(
            repository.is_degraded_unconverted(
                {
                    "extraction_status": "degraded",
                    "review_status": "approved",
                    "manual_curation_status": "",
                }
            )
        )
        self.assertFalse(
            repository.is_degraded_unconverted(
                {
                    "extraction_status": "manually_curated",
                    "review_status": "approved",
                    "manual_curation_status": "converted",
                }
            )
        )

    def test_rejected_extraction_unit_status_is_valid_but_not_publish_ready(self) -> None:
        request = ExtractionUnitUpdateRequest(
            title="Noise unit",
            content="Duplicate or incorrect extracted content.",
            unit_type="policy_rule",
            confidence=0.2,
            review_status="rejected",
            metadata={},
            actor="cs-ops-ui",
        )

        self.assertEqual(request.review_status, "rejected")
        self.assertFalse(repository.is_reviewed_status("rejected"))

    def test_production_retrieval_requires_published_approved_structured_chunks(self) -> None:
        where_sql, params = repository.filter_sql(RetrievalFilters(status=["published"]))
        self.assertIn("d.current_version_id = v.id", where_sql)
        self.assertIn("v.publish_state = 'published_ready'", where_sql)
        self.assertIn("COALESCE(c.metadata->>'review_status', '') = 'approved'", where_sql)
        self.assertIn("COALESCE(c.metadata->>'extraction_status', '') = ANY", where_sql)
        self.assertIn(["structured", "manually_curated"], params)
        self.assertIn("COALESCE(c.metadata->>'publish_blocked', 'false') <> 'true'", where_sql)

    def test_policy_table_requires_structured_table_or_sheet_refs(self) -> None:
        self.assertFalse(
            repository.has_required_source_ref(
                "policy_table",
                {"source_refs": [{"source_type": "text", "line_start": 1, "line_end": 2}]},
            )
        )
        self.assertTrue(
            repository.has_required_source_ref(
                "policy_table",
                {"source_refs": [{"source_type": "docx_table", "table_index": 0, "row_index": 1, "column_names": ["Case", "Action"]}]},
            )
        )
        self.assertTrue(
            repository.has_required_source_ref(
                "policy_table",
                {"source_refs": [{"source_type": "excel", "sheet": "Rules", "row_start": 2, "row_end": 2}]},
            )
        )

    def test_enterprise_metadata_and_source_ref_anchor_fields_are_first_class(self) -> None:
        metadata = DocumentMetadata(
            owner_team="CS Ops",
            visibility="customer_facing",
            scope="cs_response",
            policy_type="communication_rule",
            authority_level="source_of_truth",
            related_sop_ids=["sop-refund"],
            conflict_group="refund-customer-wording",
            effective_to="2026-12-31",
        )
        source_ref = SourceRef(
            source_type="pdf",
            source_file="policy.pdf",
            block_id="block-7",
            page_number=3,
            sheet_name="Rules",
            row=12,
            column="Action",
        )

        self.assertEqual(metadata.visibility, "customer_facing")
        self.assertEqual(metadata.scope, "cs_response")
        self.assertEqual(metadata.policy_type, "communication_rule")
        self.assertEqual(metadata.authority_level, "source_of_truth")
        self.assertEqual(metadata.related_sop_ids, ["sop-refund"])
        self.assertEqual(metadata.conflict_group, "refund-customer-wording")
        self.assertEqual(metadata.effective_to, "2026-12-31")
        self.assertEqual(source_ref.block_id, "block-7")
        self.assertEqual(source_ref.page_number, 3)
        self.assertEqual(source_ref.sheet_name, "Rules")
        self.assertEqual(source_ref.row, 12)
        self.assertEqual(source_ref.column, "Action")

    def test_effective_heading_sql_escapes_literal_percent_for_psycopg3(self) -> None:
        self.assertIn("|| '%%'", repository.EFFECTIVE_HEADING_SQL)
        self.assertNotIn("|| '%'", repository.EFFECTIVE_HEADING_SQL)

    def test_feedback_triage_helpers_prioritize_operational_risk(self) -> None:
        self.assertTrue(repository.is_uuid_text("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"))
        self.assertFalse(repository.is_uuid_text("legacy-sop-code"))
        self.assertEqual(repository.feedback_severity("wrong"), "high")
        self.assertEqual(repository.feedback_severity("outdated"), "high")
        self.assertEqual(repository.feedback_severity("missing_step"), "high")
        self.assertEqual(repository.feedback_severity("need_macro"), "medium")
        self.assertIn("draft version", repository.suggested_feedback_action("outdated"))
        self.assertIn("retrieval", repository.suggested_feedback_action("search_result_wrong"))
        self.assertEqual(repository.median_from_sorted([1000, 3000, 9000]), 3000)
        self.assertEqual(repository.median_from_sorted([1000, 5000]), 3000)

    def test_chat_logging_persists_retrieval_trace_for_debugging(self) -> None:
        class FakeConnection:
            def __init__(self) -> None:
                self.sql = ""
                self.params: tuple[object, ...] = ()

            def __enter__(self) -> "FakeConnection":
                return self

            def __exit__(self, *args: object) -> None:
                return None

            def execute(self, sql: str, params: tuple[object, ...]) -> None:
                self.sql = sql
                self.params = params

        fake_connection = FakeConnection()
        response = SimpleNamespace(
            question="Can CS say this?",
            answer="Use source only.",
            citations=[SimpleNamespace(chunk_id="chunk-1")],
            confidence=0.7,
            warnings=["grounded"],
            retrieval_trace={"authority_analysis": {"answer_allowed": True}},
            model_route="policy",
            model_used="moonshotai/kimi-k2.5",
            model_reason="manual_route",
            latency_ms=25,
        )

        with patch("app.repository.connection", return_value=fake_connection):
            repository.log_chat(response)

        self.assertIn("retrieval_trace", fake_connection.sql)
        self.assertIn("model_route", fake_connection.sql)
        self.assertIn('"answer_allowed": true', str(fake_connection.params))
        self.assertIn("policy", fake_connection.params)

    def test_admin_reset_preserves_curated_search_taxonomy(self) -> None:
        self.assertIn("ai_chunks", repository.ADMIN_RESET_TABLES)
        self.assertIn("ai_compiled_pages", repository.ADMIN_RESET_TABLES)
        self.assertIn("ai_chat_sessions", repository.ADMIN_RESET_TABLES)
        self.assertIn("extraction_compilation_plans", repository.ADMIN_RESET_TABLES)
        self.assertIn("extraction_map_unit_outputs", repository.ADMIN_RESET_TABLES)
        self.assertIn("extraction_reduce_items", repository.ADMIN_RESET_TABLES)
        self.assertIn("search_synonym_suggestions", repository.ADMIN_RESET_TABLES)
        self.assertNotIn("search_synonym_groups", repository.ADMIN_RESET_TABLES)
        self.assertIn("search_synonym_groups", repository.ADMIN_RESET_PRESERVED_TABLES)
        counts = {table: 1 for table in repository.ADMIN_RESET_TABLES}
        grouped = repository.group_counts(counts)
        self.assertGreater(grouped["knowledge_base"], 0)
        self.assertGreater(grouped["chat"], 0)

    def test_reset_vector_embedding_schema_tx_rebuilds_chunks_and_compiled_pages(self) -> None:
        class FakeResult:
            def __init__(self, rows: list[tuple[str]]) -> None:
                self.rows = rows

            def fetchall(self) -> list[tuple[str]]:
                return self.rows

        class FakeConnection:
            def __init__(self) -> None:
                self.sql: list[str] = []

            def execute(self, sql: str, params: tuple[object, ...] = ()) -> FakeResult:
                self.sql.append(sql)
                if "FROM pg_tables" in sql:
                    return FakeResult([("ai_chunks",), ("ai_compiled_pages",)])
                return FakeResult([])

        conn = FakeConnection()

        repository.reset_vector_embedding_schema_tx(conn)

        sql_text = "\n".join(conn.sql)
        self.assertIn("ALTER TABLE ai_chunks DROP COLUMN IF EXISTS embedding", sql_text)
        self.assertIn("ALTER TABLE ai_chunks ADD COLUMN embedding vector", sql_text)
        self.assertIn("ALTER TABLE ai_compiled_pages DROP COLUMN IF EXISTS embedding", sql_text)
        self.assertIn("ALTER TABLE ai_compiled_pages ADD COLUMN embedding vector", sql_text)
        self.assertIn("idx_ai_compiled_pages_embedding_hnsw", sql_text)

    def test_map_unit_outputs_from_artifacts_normalizes_durable_rows(self) -> None:
        rows = repository.map_unit_outputs_from_artifacts(
            [
                {
                    "stage": "map",
                    "artifact_type": "map_unit_extracts",
                    "payload": {
                        "units": [
                            {
                                "unit_id": "unit_element_1",
                                "index": 0,
                                "unit_type": "generic_fact",
                                "title": "Greeting SOP",
                                "status": "completed",
                                "confidence": 0.93,
                                "evidence_hash": "abc123",
                                "source_element_ids": ["element_1"],
                                "missing_source_element_ids": [],
                                "source_refs": [{"source_type": "text", "line_start": 1}],
                                "source_ref_quality": "line",
                                "warnings": ["review"],
                            }
                        ]
                    },
                }
            ]
        )

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["unit_id"], "unit_element_1")
        self.assertEqual(rows[0]["unit_index"], 0)
        self.assertEqual(rows[0]["unit_type"], "generic_fact")
        self.assertEqual(rows[0]["status"], "completed")
        self.assertEqual(rows[0]["attempt_count"], 1)
        self.assertEqual(rows[0]["last_error"], "")
        self.assertEqual(rows[0]["evidence_hash"], "abc123")
        self.assertEqual(rows[0]["source_element_ids"], ["element_1"])
        self.assertEqual(rows[0]["source_refs"][0]["line_start"], 1)

    def test_reduce_items_from_artifacts_dedupes_map_claims(self) -> None:
        rows = repository.reduce_items_from_artifacts(
            [
                {
                    "stage": "map",
                    "artifact_type": "map_unit_extracts",
                    "payload": {
                        "units": [
                            {
                                "unit_id": "unit_1",
                                "unit_type": "policy_rule",
                                "title": "Refund threshold",
                                "status": "completed",
                                "confidence": 0.9,
                                "evidence_hash": "hash-1",
                                "source_element_ids": ["element_1"],
                            },
                            {
                                "unit_id": "unit_2",
                                "unit_type": "policy_rule",
                                "title": "Refund threshold",
                                "status": "completed",
                                "confidence": 0.8,
                                "evidence_hash": "hash-2",
                                "source_element_ids": ["element_2"],
                            },
                        ]
                    },
                }
            ]
        )

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["item_kind"], "claim")
        self.assertEqual(rows[0]["title"], "Refund threshold")
        self.assertEqual(rows[0]["duplicate_count"], 2)
        self.assertEqual(rows[0]["source_unit_ids"], ["unit_1", "unit_2"])
        self.assertEqual(rows[0]["evidence_hashes"], ["hash-1", "hash-2"])

    def test_update_extraction_map_unit_status_tx_records_retry_metadata(self) -> None:
        class FakeResult:
            def fetchone(self) -> dict[str, object]:
                return {
                    "job_id": "job-1",
                    "unit_id": "unit_element_1",
                    "status": "in_progress",
                    "attempt_count": 2,
                    "last_error": "",
                    "warnings": ["retry"],
                }

        class FakeConnection:
            def __init__(self) -> None:
                self.sql = ""
                self.params: tuple[object, ...] = ()

            def execute(self, sql: str, params: tuple[object, ...]) -> FakeResult:
                self.sql = sql
                self.params = params
                return FakeResult()

        fake_connection = FakeConnection()

        row = repository.update_extraction_map_unit_status_tx(
            fake_connection,
            job_id="job-1",
            unit_id="unit_element_1",
            status="in_progress",
            warnings=["retry"],
        )

        self.assertEqual(row["status"], "in_progress")
        self.assertEqual(row["attempt_count"], 2)
        self.assertIn("attempt_count", fake_connection.sql)
        self.assertIn("started_at", fake_connection.sql)
        self.assertIn("updated_at", fake_connection.sql)
        self.assertEqual(fake_connection.params[0], "in_progress")
        self.assertIn('"retry"', str(fake_connection.params))

    def test_compiled_pages_from_chunks_uses_full_sop_document_layer(self) -> None:
        pages = repository.compiled_pages_from_chunks(
            "Refund SOP",
            [
                {
                    "chunk_index": 0,
                    "section": "full_sop",
                    "heading": "Refund SOP",
                    "content": "Full refund handling instructions.",
                    "metadata": {"unit_type": "full_sop", "retrieval_scope": "document"},
                    "embedding": [0.1, 0.2, 0.3],
                },
                {
                    "chunk_index": 1,
                    "section": "policy_rule",
                    "heading": "Check payment",
                    "content": "CS checks payment before refund.",
                    "metadata": {"unit_type": "policy_rule"},
                },
            ],
        )

        self.assertEqual(len(pages), 1)
        self.assertEqual(pages[0]["page_type"], "document_overview")
        self.assertEqual(pages[0]["title"], "Refund SOP")
        self.assertEqual(pages[0]["source_chunk_indexes"], [0, 1])
        self.assertEqual(pages[0]["source_unit_types"], ["full_sop", "policy_rule"])
        self.assertIn("Full refund handling instructions", pages[0]["content_md"])
        self.assertEqual(pages[0]["embedding"], [0.1, 0.2, 0.3])
        self.assertEqual(pages[0]["metadata"]["embedding_source"], "full_sop")

    def test_compiled_pages_from_approved_plan_adds_wiki_style_unit_pages(self) -> None:
        pages = repository.compiled_pages_from_chunks(
            "Refund SOP",
            [
                {
                    "chunk_index": 0,
                    "section": "full_sop",
                    "heading": "Refund SOP",
                    "content": "Full refund handling instructions.",
                    "metadata": {"unit_type": "full_sop"},
                    "embedding": [0.1, 0.2, 0.3],
                },
                {
                    "chunk_index": 1,
                    "section": "policy_rule",
                    "heading": "Check payment",
                    "content": "CS checks payment before refund.",
                    "metadata": {"unit_type": "policy_rule"},
                    "embedding": [0.4, 0.5, 0.6],
                },
                {
                    "chunk_index": 2,
                    "section": "policy_rule",
                    "heading": "Refund threshold",
                    "content": "Refunds over threshold need lead approval.",
                    "metadata": {"unit_type": "policy_rule"},
                },
            ],
            approved_compilation_plans=[
                {
                    "id": "plan-1",
                    "status": "approved",
                    "plan_version": "document_compilation_plan_v1",
                    "payload": {
                        "operations": [
                            {"index": 1, "operation": "create_or_update_unit", "publish_eligible": True, "unit_type": "policy_rule"},
                            {"index": 2, "operation": "create_or_update_unit", "publish_eligible": True, "unit_type": "policy_rule"},
                        ]
                    },
                }
            ],
        )

        wiki_page = next(page for page in pages if page["page_type"] == "wiki_policy_rule")

        self.assertEqual(wiki_page["title"], "Refund SOP - Policy Rule")
        self.assertIn("## Check payment", wiki_page["content_md"])
        self.assertIn("Refunds over threshold need lead approval.", wiki_page["content_md"])
        self.assertEqual(wiki_page["source_chunk_indexes"], [1, 2])
        self.assertEqual(wiki_page["source_unit_types"], ["policy_rule"])
        self.assertEqual(wiki_page["embedding"], [0.4, 0.5, 0.6])
        self.assertEqual(wiki_page["metadata"]["compiled_from"], "approved_compilation_plan")
        self.assertEqual(wiki_page["metadata"]["unit_type"], "compiled_wiki_page")
        self.assertEqual(wiki_page["metadata"]["wiki_page_unit_type"], "policy_rule")
        self.assertEqual(wiki_page["metadata"]["compilation_plan_id"], "plan-1")

    def test_materialize_compiled_pages_for_compilation_plan_tx_upserts_wiki_pages(self) -> None:
        class FakeResult:
            def __init__(self, one: dict[str, object] | None = None, many: list[dict[str, object]] | None = None) -> None:
                self.one = one
                self.many = many or []

            def fetchone(self) -> dict[str, object] | None:
                return self.one

            def fetchall(self) -> list[dict[str, object]]:
                return self.many

        class FakeCursor:
            def __init__(self, connection: "FakeConnection") -> None:
                self.connection = connection

            def __enter__(self) -> "FakeCursor":
                return self

            def __exit__(self, *args: object) -> None:
                return None

            def executemany(self, sql: str, rows: list[tuple[object, ...]]) -> None:
                self.connection.executemany_sql = sql
                self.connection.upsert_rows = rows

        class FakeConnection:
            def __init__(self) -> None:
                self.executemany_sql = ""
                self.upsert_rows: list[tuple[object, ...]] = []

            def execute(self, sql: str, params: tuple[object, ...]) -> FakeResult:
                if "FROM extraction_jobs" in sql:
                    return FakeResult({"document_id": "doc-1", "version_id": "ver-1", "title": "Refund SOP"})
                if "FROM ai_chunks" in sql:
                    return FakeResult(
                        many=[
                            {
                                "chunk_index": 0,
                                "section": "full_sop",
                                "heading": "Refund SOP",
                                "content": "Full refund handling instructions.",
                                "metadata": {"unit_type": "full_sop"},
                                "embedding": "[0.1,0.2]",
                            },
                            {
                                "chunk_index": 1,
                                "section": "policy_rule",
                                "heading": "Check payment",
                                "content": "CS checks payment before refund.",
                                "metadata": {"unit_type": "policy_rule"},
                                "embedding": "[0.3,0.4]",
                            },
                        ]
                    )
                return FakeResult()

            def cursor(self) -> FakeCursor:
                return FakeCursor(self)

        conn = FakeConnection()

        result = repository.materialize_compiled_pages_for_compilation_plan_tx(
            conn,
            {
                "id": "plan-1",
                "job_id": "job-1",
                "status": "approved",
                "plan_version": "document_compilation_plan_v1",
                "payload": {
                    "operations": [
                        {"index": 1, "operation": "create_or_update_unit", "publish_eligible": True, "unit_type": "policy_rule"}
                    ]
                },
            },
        )

        page_types = [row[3] for row in conn.upsert_rows]
        self.assertEqual(result["wiki_page_count"], 1)
        self.assertIn("wiki_policy_rule", page_types)
        self.assertIn("ON CONFLICT", conn.executemany_sql)

    def test_embedding_model_spec_from_metadata_normalizes_active_spec(self) -> None:
        spec = repository.embedding_model_spec_from_metadata(
            {
                "embedding_provider": "openrouter",
                "embedding_model": "openai/text-embedding-3-small",
                "embedding_dimensions": 1536,
                "embedding_spec_id": "openrouter:openai/text-embedding-3-small:1536",
            }
        )

        self.assertEqual(spec["spec_id"], "openrouter:openai/text-embedding-3-small:1536")
        self.assertEqual(spec["provider"], "openrouter")
        self.assertEqual(spec["model"], "openai/text-embedding-3-small")
        self.assertEqual(spec["dimensions"], 1536)
        self.assertEqual(spec["status"], "active")

    def test_embedding_migration_item_counts_include_chunks_and_compiled_pages(self) -> None:
        class FakeResult:
            def fetchone(self) -> dict[str, object]:
                return {
                    "chunk_count": 7,
                    "compiled_page_count": 2,
                }

        class FakeConnection:
            def __init__(self) -> None:
                self.sql = ""
                self.params: tuple[object, ...] = ()

            def execute(self, sql: str, params: tuple[object, ...]) -> FakeResult:
                self.sql = sql
                self.params = params
                return FakeResult()

        fake_connection = FakeConnection()

        counts = repository.embedding_migration_item_counts_tx(fake_connection, "local_hash:local_hash:1536")

        self.assertEqual(counts["chunk_count"], 7)
        self.assertEqual(counts["compiled_page_count"], 2)
        self.assertEqual(counts["total_items"], 9)
        self.assertIn("FROM ai_chunks", fake_connection.sql)
        self.assertIn("FROM ai_compiled_pages", fake_connection.sql)
        self.assertEqual(fake_connection.params, ("local_hash:local_hash:1536", "local_hash:local_hash:1536"))

    def test_compilation_plans_from_artifacts_normalizes_reviewable_rows(self) -> None:
        rows = repository.compilation_plans_from_artifacts(
            [
                {
                    "stage": "plan",
                    "artifact_type": "document_compilation_plan",
                    "payload": {
                        "plan_version": "document_compilation_plan_v1",
                        "human_approval_required": True,
                        "operation_count": 3,
                        "source_coverage": {"source_element_count": 5},
                        "review_gates": {"approval_required_before_publish": True},
                    },
                }
            ]
        )

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["plan_version"], "document_compilation_plan_v1")
        self.assertEqual(rows[0]["status"], "pending_review")
        self.assertEqual(rows[0]["operation_count"], 3)
        self.assertTrue(rows[0]["human_approval_required"])
        self.assertEqual(rows[0]["source_coverage"]["source_element_count"], 5)

    def test_update_extraction_compilation_plan_status_tx_records_approval(self) -> None:
        class FakeResult:
            def fetchone(self) -> dict[str, object]:
                return {
                    "id": "plan-1",
                    "job_id": "job-1",
                    "plan_version": "document_compilation_plan_v1",
                    "status": "approved",
                    "approved_by": "cs-lead",
                    "rejection_reason": "",
                }

        class FakeConnection:
            def __init__(self) -> None:
                self.sql = ""
                self.params: tuple[object, ...] = ()

            def execute(self, sql: str, params: tuple[object, ...]) -> FakeResult:
                self.sql = sql
                self.params = params
                return FakeResult()

        fake_connection = FakeConnection()

        row = repository.update_extraction_compilation_plan_status_tx(
            fake_connection,
            plan_id="plan-1",
            status="approved",
            actor="cs-lead",
        )

        self.assertEqual(row["status"], "approved")
        self.assertEqual(row["approved_by"], "cs-lead")
        self.assertIn("approved_at", fake_connection.sql)
        self.assertIn("rejected_at", fake_connection.sql)
        self.assertEqual(fake_connection.params[0], "approved")
        self.assertEqual(fake_connection.params[3], "cs-lead")

    def test_force_approve_promotes_candidate_unit_types(self) -> None:
        self.assertEqual(repository.promoted_unit_type("candidate_rule", "policy_rule"), "policy_rule")
        self.assertEqual(repository.promoted_unit_type("candidate_table_row", "policy_table"), "policy_rule")
        self.assertEqual(repository.promoted_unit_type("candidate_step", "workflow_diagram"), "workflow_step")
        self.assertEqual(repository.promoted_unit_type("candidate_action", "workflow_diagram"), "workflow_step")
        self.assertEqual(repository.promoted_unit_type("candidate_decision", "workflow_diagram"), "decision_point")
        self.assertEqual(repository.promoted_unit_type("candidate_sla", "workflow_diagram"), "sla_rule")
        self.assertEqual(repository.promoted_unit_type("candidate_audit_rule", "workflow_diagram"), "warning")
        self.assertEqual(repository.promoted_unit_type("candidate_queue_rule", "workflow_diagram"), "routing_rule")
        self.assertEqual(repository.promoted_unit_type("candidate_workflow_text", "workflow_diagram"), "workflow_overview")
        self.assertEqual(repository.promoted_unit_type("candidate_section", "policy_rule"), "text_section")
        self.assertEqual(repository.promoted_unit_type("full_sop", "policy_rule"), "full_sop")

    def test_related_document_chunk_creates_unresolved_relation_candidate(self) -> None:
        candidates = repository.relation_candidates_from_chunk(
            {
                "chunk_id": "chunk-1",
                "section": "related_document",
                "heading": "Quy định sử dụng tasklist",
                "content": "bat buoc xem truoc khi xu ly task.",
                "metadata": {"unit_type": "related_document"},
            },
            repository.normalize_phrase("Quy định chuyển Tech"),
        )

        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0]["target_title"], "Quy định sử dụng tasklist")
        self.assertEqual(candidates[0]["relation_type"], "requires")

    def test_explicit_text_reference_creates_single_requires_candidate(self) -> None:
        candidates = repository.relation_candidates_from_chunk(
            {
                "chunk_id": "chunk-2",
                "section": "policy_rule",
                "heading": "Tasklist",
                "content": "CS thực hiện theo Quy định sử dụng tasklist trước khi xử lý.",
                "metadata": {"unit_type": "policy_rule"},
            },
            repository.normalize_phrase("Quy định chuyển Tech"),
        )

        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0]["target_title"], "Quy định sử dụng tasklist")
        self.assertEqual(candidates[0]["relation_type"], "requires")
        self.assertEqual(candidates[0]["metadata"]["relation_source"], "explicit_text_reference")
        self.assertFalse(candidates[0]["metadata"]["needs_clarification"])

    def test_ambiguous_corresponding_process_creates_clarification_candidate(self) -> None:
        candidates = repository.relation_candidates_from_chunk(
            {
                "chunk_id": "chunk-3",
                "section": "handling_rule",
                "heading": "Hỗ trợ khách hàng",
                "content": "CS hỗ trợ theo quy trình tương ứng.",
                "metadata": {"unit_type": "handling_rule"},
            },
            repository.normalize_phrase("Quy định xác minh tài khoản"),
        )

        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0]["target_title"], "quy trình tương ứng")
        self.assertEqual(candidates[0]["relation_type"], "requires")
        self.assertTrue(candidates[0]["metadata"]["needs_clarification"])

    def test_operational_handoff_creates_routes_to_candidate(self) -> None:
        candidates = repository.relation_candidates_from_chunk(
            {
                "chunk_id": "chunk-4",
                "section": "workflow_step",
                "heading": "Chuyển case",
                "content": "CS cần chuyển cho MSC trong vòng 30 phút.",
                "metadata": {"unit_type": "workflow_step"},
            },
            repository.normalize_phrase("Quy định theo dõi hình ảnh"),
        )

        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0]["target_title"], "MSC")
        self.assertEqual(candidates[0]["relation_type"], "routes_to")
        self.assertEqual(candidates[0]["metadata"]["relation_source"], "operational_handoff")

    def test_manual_relation_types_are_preserved(self) -> None:
        self.assertEqual(repository.normalize_relation_type("must_follow"), "must_follow")
        self.assertEqual(repository.normalize_relation_type("uses_macro"), "uses_macro")
        self.assertEqual(repository.normalize_relation_type("related_to"), "related_to")
        self.assertEqual(repository.normalize_relation_type("possible_conflict"), "possible_conflict")

    def test_high_risk_governance_requires_owner_review_sla_and_future_due_date(self) -> None:
        tomorrow = (datetime.now(timezone.utc).date() + timedelta(days=1)).isoformat()
        failures = repository.high_risk_governance_failures(
            {"risk_level": "high"},
            {},
            "payment compliance rule",
            "policy_rule",
        )

        self.assertIn("missing_owner_team", failures)
        self.assertIn("missing_review_frequency", failures)
        self.assertIn("missing_last_reviewed_at", failures)
        self.assertIn("missing_next_review_due", failures)

        ready_failures = repository.high_risk_governance_failures(
            {
                "risk_level": "high",
                "owner_team": "CS Ops",
                "review_frequency": "quarterly",
                "last_reviewed_at": datetime.now(timezone.utc).date().isoformat(),
                "next_review_due": tomorrow,
            },
            {},
            "payment compliance rule",
            "policy_rule",
        )
        self.assertEqual(ready_failures, [])

    def test_high_risk_governance_blocks_overdue_review(self) -> None:
        yesterday = (datetime.now(timezone.utc).date() - timedelta(days=1)).isoformat()
        failures = repository.high_risk_governance_failures(
            {
                "risk_level": "critical",
                "owner_team": "CS Ops",
                "review_frequency": "annual",
                "last_reviewed_at": "2026-01-01",
                "next_review_due": yesterday,
            },
            {},
            "security rule",
            "policy_rule",
        )

        self.assertEqual(failures, ["high_risk_review_due_in_past"])


if __name__ == "__main__":
    unittest.main()
