from __future__ import annotations

import unittest

from app.repository import workflow_edge_key, workflow_graph_decision_edge_failures, workflow_graph_quality_failures


class WorkflowPublishReadinessTest(unittest.TestCase):
    def test_graph_validation_errors_block_without_acknowledgement(self) -> None:
        failures = workflow_graph_quality_failures(
            {
                "graph_validation_errors": ["decision_missing_two_branches:step_4"],
                "uncertain_edges": [{"from_node": "a", "to_node": "b"}],
            }
        )

        self.assertEqual(
            failures,
            [
                "workflow_graph_has_1_validation_errors",
                "workflow_graph_has_1_uncertain_edges",
            ],
        )

    def test_graph_validation_errors_require_acknowledgement_reason(self) -> None:
        failures = workflow_graph_quality_failures(
            {
                "graph_validation_acknowledged": True,
                "graph_validation_errors": ["decision_missing_two_branches:step_4"],
                "uncertain_edges": [{"from_node": "a", "to_node": "b"}],
            }
        )

        self.assertEqual(failures, ["workflow_graph_acknowledgement_reason_missing"])

    def test_graph_validation_errors_are_allowed_after_human_acknowledgement_with_reason(self) -> None:
        failures = workflow_graph_quality_failures(
            {
                "graph_validation_acknowledged": True,
                "graph_validation_acknowledged_reason": "Compared against source page and accepted known layout warning.",
                "graph_validation_errors": ["decision_missing_two_branches:step_4"],
                "uncertain_edges": [{"from_node": "a", "to_node": "b"}],
            }
        )

        self.assertEqual(failures, [])

    def test_decision_edges_require_edge_level_review(self) -> None:
        graph = {
            "workflow_graph": {
                "nodes": [
                    {"id": "decision_1", "type": "decision", "title": "Có đủ thông tin?"},
                    {"id": "yes_step", "type": "action", "title": "Xử lý"},
                    {"id": "no_step", "type": "action", "title": "Xin thêm thông tin"},
                ],
                "edges": [
                    {"from_node": "decision_1", "condition": "yes", "to_node": "yes_step"},
                    {"from_node": "decision_1", "condition": "no", "to_node": "no_step"},
                ],
            }
        }

        self.assertEqual(workflow_graph_decision_edge_failures(graph), ["workflow_graph_has_2_decision_edges_need_review"])

    def test_decision_edges_accept_confirmed_and_acknowledged_with_reason(self) -> None:
        yes_edge = {"from_node": "decision_1", "condition": "yes", "to_node": "yes_step"}
        no_edge = {"from_node": "decision_1", "condition": "no", "to_node": "no_step"}
        graph = {
            "workflow_graph": {
                "nodes": [
                    {"id": "decision_1", "type": "decision", "title": "Có đủ thông tin?"},
                    {"id": "yes_step", "type": "action", "title": "Xử lý"},
                    {"id": "no_step", "type": "action", "title": "Xin thêm thông tin"},
                ],
                "edges": [yes_edge, no_edge],
            },
            "workflow_edge_reviews": {
                workflow_edge_key(yes_edge): {"status": "confirmed"},
                workflow_edge_key(no_edge): {"status": "acknowledged", "reason": "Source arrow is visually curved but branch label is clear."},
            },
        }

        self.assertEqual(workflow_graph_decision_edge_failures(graph), [])


if __name__ == "__main__":
    unittest.main()
