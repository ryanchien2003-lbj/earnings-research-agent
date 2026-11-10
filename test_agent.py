import json
import unittest

from agent import investigate, run_tool


class EarningsAgentTests(unittest.TestCase):
    def test_financial_comparison_uses_reported_inputs(self):
        report = investigate("Compare Microsoft FY25 Q4 revenue and operating margin year over year.")
        by_metric = {step["arguments"]["metric"]: step["result"] for step in report["trace"]}
        self.assertIn("+18.10%", by_metric["revenue"]["text"])
        self.assertIn("+1.76 percentage points", by_metric["operating_margin"]["text"])
        self.assertEqual(["F25", "F24"], [s["id"] for s in by_metric["revenue"]["sources"]])

    def test_note_retrieval_returns_expected_evidence(self):
        report = investigate("What did Microsoft say about Azure growth and capex in FY25 Q4?")
        self.assertEqual(["N1", "N2"], [result["sources"][0]["id"] for result in report["results"]])

    def test_unsupported_requests_and_tool_arguments(self):
        self.assertTrue(investigate("What was Nvidia FY25 Q4 revenue?")["message"])
        self.assertIn("error", run_tool("lookup_metric", {"metric": "revenue", "period": "FY26 Q4"}))

    def test_model_tool_round_trip_uses_only_tool_output(self):
        def fake_complete(messages):
            if len(messages) == 2:
                return {"tool_calls": [{"id": "check1", "type": "function", "function": {
                    "name": "lookup_metric",
                    "arguments": json.dumps({"metric": "revenue", "period": "FY25 Q4"}),
                }}]}
            self.assertEqual("check1", messages[-1]["tool_call_id"])
            self.assertIn("76,441", messages[-1]["content"])
            return {"content": "Invented narrative that should never appear in the report."}

        report = investigate("Microsoft revenue?", fake_complete)
        self.assertEqual(1, len(report["results"]))
        self.assertIn("76,441", report["results"][0]["text"])
        self.assertNotIn("Invented narrative", json.dumps(report))


if __name__ == "__main__":
    unittest.main()
