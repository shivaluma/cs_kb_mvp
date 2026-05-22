from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.ranking import QueryUnderstanding, RankingOptions, SearchCandidate, business_rerank, maybe_model_rerank, normalize_text


@dataclass(frozen=True)
class EvalQuery:
    key: str
    query: str
    expected: tuple[str, ...]


def fixture_candidates() -> list[SearchCandidate]:
    rows = [
        ("email_open", "macro_script", "Email macro: Open / Mở đầu", "Đối với Email. Mail: Open / Mở đầu. Macro: Xin chào anh/chị + Tên. Lưu ý: nếu không xác định giới tính KH, sử dụng Xin chào Quý khách hàng.", 0.56, "macro_table_email", "table_row", "low"),
        ("tx_identity_check", "operational_note", "Kiểm tra họ tên và hình ảnh TX", "Đối với TX, CS phải kiểm tra họ tên và hình ảnh trên hệ thống trước khi phản hồi.", 0.42, "email_section", "block_id", "medium"),
        ("call_chat_open", "macro_script", "Call/Chat opening script", "Be xin chào, em là/em tên là xxx.", 0.46, "call_chat_section", "block_id", "low"),
        ("already_mentioned", "handling_rule", "Nếu KH/TX đã đề cập vấn đề", "Nếu KH/TX đã đề cập vấn đề, CS không hỏi lại, chỉ xác nhận hoặc hỏi thêm thông tin nếu chưa rõ.", 0.58, "handling_group", "block_id", "medium"),
        ("not_mentioned", "handling_rule", "Nếu KH/TX chưa đề cập vấn đề", "Nếu KH/TX chưa đề cập vấn đề, CS có thể hỏi hoặc khai thác vấn đề.", 0.53, "handling_group", "block_id", "medium"),
        ("handling_group", "handling_rule_group", "Call/Chat conditional handling", "Nếu KH/TX chưa đề cập vấn đề thì CS có thể hỏi; nếu đã đề cập thì không hỏi lại, chỉ xác nhận hoặc hỏi rõ phần chưa rõ.", 0.5, "", "block_id", "medium"),
        ("sorry_rule", "wording_rule", 'Khi nào dùng "xin lỗi"', 'Dùng "xin lỗi" chỉ khi vấn đề do be, TX hoặc nhà hàng gây ra.', 0.6, "wording_group", "block_id", "medium"),
        ("regret_rule", "wording_rule", 'Khi nào dùng "rất tiếc"', 'Dùng "rất tiếc về trải nghiệm không tốt của anh/chị" cho các trường hợp còn lại.', 0.55, "wording_group", "block_id", "medium"),
        ("wording_group", "wording_rule_group", 'Phân biệt "xin lỗi" và "rất tiếc"', 'Dùng "xin lỗi" khi vấn đề do be/TX/nhà hàng; dùng "rất tiếc" cho các trường hợp còn lại.', 0.52, "", "block_id", "medium"),
        ("duplicate_forbidden", "compliance_rule", 'Không nói "ĐÓNG HỖ TRỢ TẠI ĐÂY"', 'Tuyệt đối không nói "ĐÓNG HỖ TRỢ TẠI ĐÂY" cho case trùng.', 0.62, "duplicate_section", "block_id", "high"),
        ("sanction_threshold", "compliance_rule", "Không cung cấp ngưỡng và lý do chế tài", "Không chủ động cung cấp ngưỡng chế tài, số lần vi phạm, trạng thái khóa tài khoản hoặc lý do chế tài cho KH/TX.", 0.57, "sanction_group", "block_id", "high"),
        ("internal_workflow", "compliance_rule", "Không cung cấp quy trình xử lý nội bộ", "Không chủ động cung cấp quy trình xử lý nội bộ, thời gian SI call, số lần gọi hoặc nội dung cuộc gọi.", 0.58, "sanction_group", "block_id", "high"),
        ("sanction_group", "compliance_rule_group", "Sanction/internal disclosure group", "Không cung cấp ngưỡng/lý do chế tài, số lần vi phạm hoặc trạng thái khóa; không cung cấp quy trình xử lý nội bộ, thời gian SI call, số lần gọi hoặc nội dung cuộc gọi.", 0.5, "", "block_id", "high"),
        ("specialist_note", "operational_note", 'Chỉ dùng "[bộ phận chuyên môn]"', 'Chỉ dùng cụm [bộ phận chuyên môn] trong case xem xét khoá tài khoản theo macro được phép.', 0.51, "sanction_group", "block_id", "medium"),
        ("full_sop", "full_sop", "Quy định nội dung phản hồi tài xế, khách hàng", "Full SOP: email/call/chat macro, wording xin lỗi/rất tiếc, case trùng, khiếu nại đối tượng còn lại, chế tài và quy trình nội bộ.", 0.7, "", "block_id", "low"),
    ]
    return [
        SearchCandidate(
            chunk_id=chunk_id,
            document_id="fixture-doc",
            document_version_id="fixture-version",
            parent_chunk_id=parent,
            title=title,
            normalized_title=normalize_text(title),
            content=text,
            retrieval_text=text,
            section_path=("Quy định nội dung phản hồi tài xế, khách hàng",),
            chunk_type=chunk_type,
            status="published",
            review_status="approved",
            risk_level=risk,
            source_ref_quality=source_ref_quality,
            source_refs=({"block_id": f"block-{chunk_id}"},),
            meili_score=score,
            lexical_score=score,
            vector_score=score * 0.9,
            from_meilisearch=True,
            from_vector=True,
        )
        for chunk_id, chunk_type, title, text, score, parent, source_ref_quality, risk in rows
    ]


def eval_queries() -> list[EvalQuery]:
    return [
        EvalQuery("A", "đóng hỗ trợ tại đây", ("duplicate_forbidden",)),
        EvalQuery("B", "khi nào dùng xin lỗi thay vì rất tiếc", ("wording_group", "sorry_rule", "regret_rule")),
        EvalQuery("C", "CS có được hỏi lại vấn đề khi khách đã nói trước đó không", ("handling_group", "already_mentioned")),
        EvalQuery("D", "có được nói tài xế bị khóa vì vi phạm 3 lần không", ("sanction_group", "sanction_threshold")),
        EvalQuery("E", "SI đã gọi tài xế mấy lần có nói cho khách không", ("internal_workflow", "sanction_group")),
        EvalQuery("F", "mẫu câu email mở đầu cho khách không rõ giới tính", ("email_open",)),
        EvalQuery("G", "bộ phận chuyên môn dùng khi nào", ("specialist_note",)),
        EvalQuery("H", "quy định nội dung phản hồi tài xế khách hàng", ("full_sop",)),
    ]


def score_run(mode: str, use_model_rerank: bool) -> list[dict[str, object]]:
    output = []
    for item in eval_queries():
        baseline = sorted(fixture_candidates(), key=lambda candidate: candidate.meili_score, reverse=True)
        options = RankingOptions(
            mode=mode,
            debug=True,
            force_model_rerank=use_model_rerank,
        )
        ranked = business_rerank(item.query, fixture_candidates(), options)
        if use_model_rerank:
            ranked, _decision = maybe_model_rerank(item.query, ranked, options)
        expected = set(item.expected)
        output.append(
            {
                "key": item.key,
                "query": item.query,
                "before_top1": baseline[0].chunk_id,
                "after_top1": ranked[0].chunk_id if ranked else "",
                "top1_correct": bool(ranked and ranked[0].chunk_id in expected),
                "top3_contains_expected": bool(expected & {candidate.chunk_id for candidate in ranked[:3]}),
                "top5_contains_expected": bool(expected & {candidate.chunk_id for candidate in ranked[:5]}),
                "precision_at_3": round(sum(1 for candidate in ranked[:3] if candidate.chunk_id in expected) / 3, 2),
                "recall_at_5": round(sum(1 for expected_id in expected if expected_id in {candidate.chunk_id for candidate in ranked[:5]}) / len(expected), 2),
            }
        )
    return output


def print_table(rows: list[dict[str, object]]) -> None:
    headers = ["key", "before_top1", "after_top1", "top1", "top3", "top5", "p@3", "r@5"]
    print(" | ".join(headers))
    print(" | ".join(["---"] * len(headers)))
    for row in rows:
        print(
            " | ".join(
                [
                    str(row["key"]),
                    str(row["before_top1"]),
                    str(row["after_top1"]),
                    "yes" if row["top1_correct"] else "no",
                    "yes" if row["top3_contains_expected"] else "no",
                    "yes" if row["top5_contains_expected"] else "no",
                    str(row["precision_at_3"]),
                    str(row["recall_at_5"]),
                ]
            )
        )
    print()
    print(
        "summary:",
        {
            "top1_correct": sum(1 for row in rows if row["top1_correct"]),
            "top3_contains_expected": sum(1 for row in rows if row["top3_contains_expected"]),
            "top5_contains_expected": sum(1 for row in rows if row["top5_contains_expected"]),
        },
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Run SOP ranking fixture evaluation.")
    parser.add_argument("--mode", choices=["portal_search", "ai_chat"], default="portal_search")
    parser.add_argument("--model-rerank", action="store_true")
    args = parser.parse_args()
    print_table(score_run(args.mode, args.model_rerank))


if __name__ == "__main__":
    main()
