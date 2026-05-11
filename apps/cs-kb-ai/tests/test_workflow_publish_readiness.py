from __future__ import annotations

import unittest

from app.repository import workflow_graph_quality_failures


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

    def test_graph_validation_errors_are_allowed_after_human_acknowledgement(self) -> None:
        failures = workflow_graph_quality_failures(
            {
                "graph_validation_acknowledged": True,
                "graph_validation_errors": ["decision_missing_two_branches:step_4"],
                "uncertain_edges": [{"from_node": "a", "to_node": "b"}],
            }
        )

        self.assertEqual(failures, [])


if __name__ == "__main__":
    unittest.main()
