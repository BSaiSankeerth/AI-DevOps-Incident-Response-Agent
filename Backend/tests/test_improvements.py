"""
Unit tests for the AI DevOps Agent improvements.
Tests use unittest.mock to avoid real LLM/tool/DB calls.

Run with:
    cd Backend
    .\\venv\\Scripts\\Activate.ps1
    python -m pytest tests/test_improvements.py -v
"""
import sys
import os

# Add Backend/ to path so imports work without installing the package
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import unittest
from unittest.mock import patch, MagicMock

# ------------------------------------------------------------------ helpers

def _make_state(**kwargs):
    base = {
        "messages": [{"role": "user", "content": kwargs.pop("question", "Why is the service slow?")}],
        "steps": 0,
        "user_id": "test-user",
        "conversation_id": "test-conv",
        "incident_type": "unknown",
        "evidence": {"metrics": None, "logs": None, "rag": None},
        "retrieved_sources": [],
        "calculations": [],
        "tools_called": [],
        "failed_tools": [],
        "validation_status": "pending",
    }
    base.update(kwargs)
    return base


# ==================================================================
# Tests for incident_classifier
# ==================================================================
class TestIncidentClassifier(unittest.TestCase):

    def _classify(self, text):
        from app.agent.incident_classifier import classify_question
        return classify_question(text)

    def test_incident_latency(self):
        self.assertEqual(self._classify("Why is the API latency spiking?"), "incident")

    def test_incident_error(self):
        self.assertEqual(self._classify("The service is returning 500 errors"), "incident")

    def test_incident_outage(self):
        self.assertEqual(self._classify("We have an outage — DB is down"), "incident")

    def test_simple_port(self):
        self.assertEqual(self._classify("What port does the service use?"), "simple")

    def test_simple_version(self):
        self.assertEqual(self._classify("What version is deployed?"), "simple")

    def test_incident_what_happened(self):
        self.assertEqual(self._classify("What happened to the service?"), "incident")


# ==================================================================
# Tests for validator
# ==================================================================
class TestValidator(unittest.TestCase):

    def _validate(self, answer, sources=None, calcs=None, rag_text=""):
        from app.agent.validator import validate_answer
        return validate_answer(answer, sources or [], calcs or [], rag_text)

    # Test 10: Citation validation — invented page number removed
    def test_invalid_page_removed(self):
        answer = "See runbook.pdf page 99 for steps."
        sources = [{"source": "runbook.pdf", "page": 1}, {"source": "runbook.pdf", "page": 2}]
        cleaned, violations = self._validate(answer, sources)
        self.assertNotIn("page 99", cleaned)
        self.assertTrue(any("99" in v for v in violations))

    def test_valid_citation_kept(self):
        answer = "See runbook.pdf page 1 for steps."
        sources = [{"source": "runbook.pdf", "page": 1}]
        cleaned, violations = self._validate(answer, sources)
        self.assertIn("runbook.pdf", cleaned)
        self.assertEqual([v for v in violations if "runbook.pdf" in v], [])

    # Test 9: Command validation — invented kubectl removed
    def test_kubectl_without_runbook_removed(self):
        answer = "Run kubectl rollout undo deployment/api to rollback."
        cleaned, violations = self._validate(answer, rag_text="")
        self.assertNotIn("kubectl", cleaned)
        self.assertTrue(any("kubectl" in v for v in violations))

    def test_kubectl_in_runbook_kept(self):
        answer = "Run kubectl rollout undo deployment/api as per runbook."
        rag_text = "To rollback: kubectl rollout undo deployment/api"
        cleaned, _ = self._validate(answer, rag_text=rag_text)
        self.assertIn("kubectl", cleaned)

    def test_unverified_calculation_warning(self):
        # 400% was NOT produced by calculator_tool (calculations=[])
        answer = "Latency increased by 400%.\n\nNOT VERIFIED\n- none"
        cleaned, violations = self._validate(answer, calcs=[])
        self.assertTrue(any("400" in v for v in violations))

    def test_verified_calculation_no_warning(self):
        # 400 was produced by calculator_tool
        answer = "Latency increased by 400%."
        cleaned, violations = self._validate(answer, calcs=["400"])
        calc_warnings = [v for v in violations if "400" in v]
        self.assertEqual(calc_warnings, [])


# ==================================================================
# Tests for prefetcher
# ==================================================================
class TestPrefetcher(unittest.TestCase):

    # Test 5: Missing runbook
    @patch("app.agent.prefetcher.rag_tool", return_value="No documents have been uploaded yet")
    @patch("app.agent.prefetcher._has_files", return_value=False)
    def test_no_rag_returns_none(self, mock_has, mock_rag):
        from app.agent.prefetcher import prefetch_evidence
        result = prefetch_evidence("why is it slow", "u1", "c1")
        self.assertIsNone(result["rag"])
        self.assertNotIn("rag_tool", result["tools_called"])

    # Test 6: Missing logs
    @patch("app.agent.prefetcher.rag_tool", return_value="No documents")
    @patch("app.agent.prefetcher.metrics_tool", return_value="No metrics files")
    @patch("app.agent.prefetcher._has_files", return_value=False)
    def test_no_logs_returns_none(self, mock_has, mock_metrics, mock_rag):
        from app.agent.prefetcher import prefetch_evidence
        result = prefetch_evidence("why is it slow", "u1", "c1")
        self.assertIsNone(result["logs"])
        self.assertNotIn("log_tool", result["tools_called"])

    # Test 7: Missing metrics
    @patch("app.agent.prefetcher.rag_tool", return_value="No documents")
    @patch("app.agent.prefetcher._has_files", side_effect=lambda d, e: False)
    def test_no_metrics_returns_none(self, mock_has, mock_rag):
        from app.agent.prefetcher import prefetch_evidence
        result = prefetch_evidence("why is it slow", "u1", "c1")
        self.assertIsNone(result["metrics"])
        self.assertNotIn("metrics_tool", result["tools_called"])

    # Tool failure should not crash
    @patch("app.agent.prefetcher.rag_tool", side_effect=Exception("qdrant unavailable"))
    @patch("app.agent.prefetcher._has_files", return_value=False)
    def test_tool_failure_is_recorded(self, mock_has, mock_rag):
        from app.agent.prefetcher import prefetch_evidence
        result = prefetch_evidence("why is it slow", "u1", "c1")
        self.assertTrue(any("rag_tool" in f for f in result["failed_tools"]))


# ==================================================================
# Tests for graph nodes (unit level)
# ==================================================================
class TestClassifyNode(unittest.TestCase):

    def _run(self, question):
        from app.agent.graph import classify_node
        state = _make_state(question=question)
        return classify_node(state)

    def test_incident_classified(self):
        result = self._run("Why is latency high after deployment?")
        self.assertEqual(result["incident_type"], "incident")

    def test_simple_classified(self):
        result = self._run("What port does the service use?")
        self.assertEqual(result["incident_type"], "simple")


class TestPrefetchNodeSkipsForSimple(unittest.TestCase):

    def test_simple_skips_prefetch(self):
        from app.agent.graph import prefetch_node
        state = _make_state(question="What port?")
        state["incident_type"] = "simple"
        result = prefetch_node(state)
        # Should return empty dict (nothing to update)
        self.assertEqual(result, {})


# ==================================================================
# Tests for the validate_node (integration-level with real validator)
# ==================================================================
class TestValidateNode(unittest.TestCase):

    # Test 4: Evidence-only citations
    def test_validate_node_removes_bad_citation(self):
        from app.agent.graph import validate_node
        state = _make_state()
        state["messages"] = [
            {"role": "user", "content": "why?"},
            {
                "role": "assistant",
                "content": "See inventory-api-runbook.pdf page 6 for mitigation.",
            },
        ]
        state["retrieved_sources"] = [
            {"source": "inventory-api-runbook.pdf", "page": 1},
            {"source": "inventory-api-runbook.pdf", "page": 2},
        ]
        state["calculations"] = []
        state["evidence"] = {"rag": "SOURCE: inventory-api-runbook.pdf | page 1"}

        result = validate_node(state)
        final_answer = result["messages"][-1]["content"]
        self.assertNotIn("page 6", final_answer)
        self.assertEqual(result["validation_status"], "fixed")

    # Test 1: All tools called for incident scenario
    @patch("app.agent.prefetcher.rag_tool", return_value="SOURCE: runbook.pdf | page 1 | relevance 0.9\nDB pool steps here")
    @patch("app.agent.prefetcher.log_tool", return_value="LOG FILES: app.log\nERROR: connection pool exhausted")
    @patch("app.agent.prefetcher.metrics_tool", return_value="FILE metrics.csv (time series)\n  db_connections: first=5 last=20")
    @patch("app.agent.prefetcher._has_files", return_value=True)
    def test_incident_all_tools_prefetched(self, mock_has, mock_metrics, mock_log, mock_rag):
        from app.agent.prefetcher import prefetch_evidence
        result = prefetch_evidence("Why are DB connections exhausted?", "u1", "c1")
        self.assertIn("metrics_tool", result["tools_called"])
        self.assertIn("log_tool", result["tools_called"])
        self.assertIn("rag_tool", result["tools_called"])
        self.assertIsNotNone(result["metrics"])
        self.assertIsNotNone(result["logs"])
        self.assertIsNotNone(result["rag"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
