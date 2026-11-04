import unittest
import xml.etree.ElementTree as ET
from src import evalview
from src.report import case_report_html, verify_fingerprint
from src.service import Workbench


class Report(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.wb = Workbench(7)

    def test_report_has_every_section_and_a_valid_fingerprint(self):
        a = self.wb.load_scenario("1 - Ring forming")
        self.wb.start_watch(a, "internal_policy", "gather evidence", "rev1", 30)
        self.wb.advance(7)
        self.wb.decide_watch(a, "rev1", "Escalate", "evidence confirmed")
        h = case_report_html(self.wb, a)
        for s in ("AML-Nexus case report", "Evidence", "How the score was built", "Money-flow map", "evidence ledger", "Evidence Watch",
                  "Human actions and audit trail", "Known limits", "Report fingerprint"):
            self.assertIn(s, h, s)
        self.assertTrue(verify_fingerprint(h))
        self.assertFalse(verify_fingerprint(h.replace("Escalate", "Clear", 1)))
        self.assertNotIn("collector", h.lower())  # synthetic ground truth never leaks

    def test_user_text_is_escaped(self):
        a = self.wb.load_scenario("5 - Closed loop")
        self.wb.audit.add("rev1", "case_decision", a, dict(reason="<script>alert(1)</script>"), self.wb.now)
        h = case_report_html(self.wb, a)
        self.assertNotIn("<script>alert(1)", h); self.assertIn("&lt;script&gt;", h)

    def test_no_case_no_report(self):
        with self.assertRaises(ValueError): case_report_html(self.wb, "C0001")


class EvalView(unittest.TestCase):
    def test_numbers_come_from_the_saved_files(self):
        d = evalview.load()
        res = d["results"]
        self.assertIsNotNone(res)
        t = evalview.headline(res)
        self.assertEqual(len(t), 7); self.assertIn(f"{res['heldout_chosen']['recall']:.1%}", t.iloc[0, 1])
        self.assertEqual(len(evalview.per_seed(res)), 10)
        self.assertIn("no gating", evalview.sensitivity(res).index)
        self.assertEqual(len(evalview.counter_evidence_effect(res)), 2)
        s = evalview.ledger_summary(d["ledger_results"])
        self.assertGreater(s["positives"], 0); self.assertGreater(s["negatives"], 0)


if __name__ == "__main__":
    unittest.main()
