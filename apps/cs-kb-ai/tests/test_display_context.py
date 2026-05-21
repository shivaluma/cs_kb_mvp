from __future__ import annotations

import inspect
import unittest
from datetime import datetime, timezone

from app import repository
from app.retrieval import build_display_context, display_highlight


class DisplayContextTest(unittest.TestCase):
    def test_exact_offset_highlight_uses_source_evidence_section(self) -> None:
        row = retrieval_row(
            "atomic-1",
            content="CS_L2 tạo tasklist + ping Tech",
            heading="Tasklist rule",
        )
        context = context_payload([
            source_evidence_row(
                "source-1",
                "Quy định chung\n\nKênh tiếp nhận: Queue Tech Support.\nCS_L2 tạo tasklist + ping Tech khi Priority P1.",
            )
        ])

        display = build_display_context(row, context)

        self.assertEqual(display.display_unit_type, "source_section")
        self.assertEqual(display.highlights[0].match_strategy, "exact")
        self.assertEqual(display.content[display.highlights[0].start_offset:display.highlights[0].end_offset], row["content"])

    def test_normalized_text_match_handles_punctuation_and_line_breaks(self) -> None:
        highlight = display_highlight(
            "atomic-2",
            "CS L2 tao tasklist ping Tech",
            "CS_L2 tạo tasklist + ping Tech khi Priority P1.",
        )

        self.assertEqual(highlight.match_strategy, "normalized")
        self.assertIsNotNone(highlight.start_offset)
        self.assertIsNotNone(highlight.end_offset)

    def test_paragraph_match_highlights_nearest_parent_paragraph(self) -> None:
        display = (
            "Cancellation before pickup is handled by CS_L1.\n\n"
            "Refund after delivery requires lead approval and proof from the customer."
        )
        highlight = display_highlight("atomic-paragraph", "Refund delivery lead proof customer", display)

        self.assertEqual(highlight.match_strategy, "paragraph")
        self.assertIn("Refund after delivery", display[highlight.start_offset:highlight.end_offset])

    def test_missing_source_section_falls_back_to_same_section_not_full_sop_summary(self) -> None:
        row = retrieval_row("atomic-3", section="handling_rule", content="Atomic handling detail")
        context = context_payload([
            {
                "chunk_id": "summary",
                "chunk_index": 0,
                "section": "full_sop",
                "heading": "Summary",
                "content": "Only a short document purpose summary.",
                "metadata": {"unit_type": "full_sop", "retrieval_scope": "document"},
            },
            {
                "chunk_id": "atomic-3",
                "chunk_index": 1,
                "section": "handling_rule",
                "heading": "Handling",
                "content": "Atomic handling detail",
                "metadata": {"unit_type": "handling_rule"},
            },
        ])

        display = build_display_context(row, context)

        self.assertEqual(display.display_unit_type, "section")
        self.assertIn("Atomic handling detail", display.content)
        self.assertNotIn("short document purpose summary", display.content)

    def test_failed_highlight_keeps_parent_source_and_relevant_excerpt(self) -> None:
        row = retrieval_row("atomic-4", content="Refund only after delivery")
        context = context_payload([source_evidence_row("source-4", "The source section discusses cancellation before pickup.")])

        display = build_display_context(row, context)

        self.assertEqual(display.display_unit_type, "source_document")
        self.assertTrue(display.highlight_failed)
        self.assertEqual(display.fallback_excerpt, "Refund only after delivery")

    def test_table_row_highlight_uses_structural_anchor(self) -> None:
        row = retrieval_row("row-2", section="policy_rule", content="Trong phần Refund table, dòng bảng này ghi Service: BF; Case: Cancel; Action: Refund.")
        row["metadata"] = {
            **row["metadata"],
            "source_ref_quality": "table_row",
            "table_id": "table_1",
            "row_index": 2,
            "section_id": "refund-table",
            "section_title": "Refund table",
            "block_id": "table_1_row_2",
        }
        context = context_payload([
            table_row("row-1", 1, "Trong phần Refund table, dòng bảng này ghi Service: BF; Case: Delay; Action: Apology."),
            table_row("row-2", 2, "Trong phần Refund table, dòng bảng này ghi Service: BF; Case: Cancel; Action: Refund."),
        ])

        display = build_display_context(row, context)

        self.assertEqual(display.display_unit_type, "table_section")
        self.assertEqual(display.highlights[0].match_strategy, "table_row_anchor")
        self.assertEqual(display.highlights[0].source_anchor.table_id, "table_1")
        self.assertEqual(display.highlights[0].source_anchor.row_index, 2)
        self.assertEqual(len(display.blocks), 2)

    def test_parent_missing_returns_safe_display_without_raw_chunk(self) -> None:
        row = retrieval_row("atomic-5", content="Sensitive raw chunk should not be primary display")

        display = build_display_context(row, None)

        self.assertEqual(display.display_unit_type, "missing_source")
        self.assertEqual(display.source_resolution_status, "parent_missing")
        self.assertNotIn("Sensitive raw chunk", display.content)

    def test_display_context_query_keeps_published_access_gate(self) -> None:
        source = inspect.getsource(repository.display_context_rows_for_results)

        self.assertIn("d.status = 'active'", source)
        self.assertIn("d.current_version_id = v.id", source)
        self.assertIn("v.status = 'published'", source)
        self.assertIn("v.publish_state = 'published_ready'", source)
        self.assertIn("COALESCE(c.metadata->>'publish_blocked', 'false') <> 'true'", source)


def retrieval_row(
    chunk_id: str,
    *,
    section: str = "policy_rule",
    content: str = "Matched policy text",
    heading: str = "Policy rule",
) -> dict[str, object]:
    return {
        "chunk_id": chunk_id,
        "document_id": "doc-1",
        "version_id": "version-1",
        "title": "Quy định chuyển thông tin cho Tech",
        "source_filename": "tech.md",
        "version_number": 1,
        "chunk_index": 1,
        "section": section,
        "heading": heading,
        "content": content,
        "metadata": {
            "unit_type": section,
            "category": "Tech",
            "collection_slug": "tech-handoff",
            "collection_name": "Tech Handoff",
        },
    }


def source_evidence_row(chunk_id: str, content: str) -> dict[str, object]:
    return {
        "chunk_id": chunk_id,
        "chunk_index": 0,
        "section": "source_evidence",
        "heading": "Source section",
        "content": content,
        "metadata": {
            "unit_type": "source_evidence_section",
            "retrieval_scope": "source_evidence",
            "source_evidence_only": True,
        },
    }


def table_row(chunk_id: str, row_index: int, content: str) -> dict[str, object]:
    return {
        "chunk_id": chunk_id,
        "chunk_index": row_index,
        "document_id": "doc-1",
        "version_id": "version-1",
        "section": "policy_rule",
        "heading": f"Refund row {row_index}",
        "content": content,
        "metadata": {
            "unit_type": "policy_rule",
            "source_ref_quality": "table_row",
            "table_id": "table_1",
            "row_index": row_index,
            "section_id": "refund-table",
            "section_title": "Refund table",
            "block_id": f"table_1_row_{row_index}",
        },
    }


def context_payload(chunks: list[dict[str, object]]) -> dict[str, object]:
    return {
        "document_id": "doc-1",
        "document_title": "Quy định chuyển thông tin cho Tech",
        "document_metadata": {"category": "Tech"},
        "updated_at": datetime(2026, 5, 22, tzinfo=timezone.utc),
        "version_id": "version-1",
        "version_number": 1,
        "chunks": chunks,
    }


if __name__ == "__main__":
    unittest.main()
