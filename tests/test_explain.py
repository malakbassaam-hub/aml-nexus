import json
import unittest
from src.explain import AIConfig, SYSTEM, check_grounding, facts_from_case, facts_from_packet, summarize, template_summary
from src.service import Workbench

FACTS = dict(pattern="many senders paying one account", system_recommendation="Monitor", suspicion=0.74, counter_evidence_score=0.15,
             evidence_for=["26 distinct senders within 7 days", "100% of deposits sit just under the 10,000 threshold"],
             evidence_against=[])
GOOD = ("The screening system recommends Monitor. The pattern resembles many senders paying one account: 26 distinct senders "
        "within 7 days, and 100% of deposits sit just under the 10,000 threshold. No evidence against suspicion was found. "
        "A human reviewer makes the decision.")


def fake(status, text="", body=None):
    calls = []
    def http(url, headers, b):
        calls.append((url, headers, b))
        return status, body if body is not None else {"content": [{"type": "text", "text": text}]}
    http.calls = calls
    return http


class Explain(unittest.TestCase):
    cfg = AIConfig("sk-test")

    def test_grounded_summary_is_accepted_and_request_is_well_formed(self):
        h = fake(200, GOOD)
        r = summarize(FACTS, self.cfg, h)
        self.assertEqual(r["source"], "claude")
        url, headers, body = h.calls[0]
        self.assertTrue(url.startswith("https://api.anthropic.com"))
        self.assertEqual(body["system"], SYSTEM)
        self.assertEqual(json.loads(body["messages"][0]["content"]), FACTS)

    def test_invented_numbers_accusations_and_missing_human_are_rejected(self):
        self.assertFalse(check_grounding(GOOD.replace("26", "31"), FACTS)[0])
        self.assertFalse(check_grounding(GOOD + " The owner is a criminal.", FACTS)[0])
        self.assertFalse(check_grounding("The screening system recommends Monitor for these 26 distinct senders within 7 days.", FACTS)[0])
        r = summarize(FACTS, self.cfg, fake(200, GOOD.replace("26", "31")))
        self.assertEqual(r["source"], "template"); self.assertIn("grounding", r["note"])

    def test_fallbacks_never_raise(self):
        self.assertEqual(summarize(FACTS, None)["source"], "template")
        self.assertEqual(summarize(FACTS, self.cfg, fake(429, body={"error": {"message": "rate limited"}}))["source"], "template")
        def boom(*a): raise ConnectionError("down")
        self.assertIn("unreachable", summarize(FACTS, self.cfg, boom)["note"])

    def test_template_shows_both_sides_and_defers_to_a_human(self):
        t = template_summary(FACTS)
        self.assertIn("26 distinct senders", t); self.assertIn("none was found", t); self.assertIn("human reviewer", t)
        self.assertTrue(check_grounding(t, FACTS)[0])

    def test_facts_never_leak_identifiers_or_ground_truth(self):
        wb = Workbench(7); a = wb.load_scenario("1 - Ring forming")
        f = facts_from_case(wb.case(a))
        blob = json.dumps(f)
        self.assertNotIn(a, blob); self.assertNotIn("collector", blob.lower())
        wb.start_watch(a, "internal_policy", "gather evidence", "rev1", 30); wb.advance(7)
        pf = facts_from_packet(wb.packet(a), 7)
        self.assertNotIn(a, json.dumps(pf))
        self.assertTrue(check_grounding(template_summary(pf), pf)[0])


if __name__ == "__main__":
    unittest.main()
