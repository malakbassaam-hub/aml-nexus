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


class GeminiPath(unittest.TestCase):
    cfg = AIConfig("g-key", "gemini-2.5-flash-lite", "gemini")

    def test_request_shape_and_grounded_answer(self):
        calls = []
        def http(url, headers, body):
            calls.append((url, headers, body))
            return 200, {"candidates": [{"content": {"parts": [{"text": GOOD}]}}]}
        r = summarize(FACTS, self.cfg, http)
        self.assertEqual(r["source"], "gemini")
        url, headers, body = calls[0]
        self.assertTrue(url.startswith("https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash-lite:generateContent"))
        self.assertEqual(headers["x-goog-api-key"], "g-key"); self.assertNotIn("g-key", url)
        self.assertEqual(body["systemInstruction"]["parts"][0]["text"], SYSTEM)
        self.assertEqual(json.loads(body["contents"][0]["parts"][0]["text"]), FACTS)

    def test_bad_answers_fall_back_to_the_template(self):
        for resp in ((200, {}), (200, {"candidates": []}), (429, {"error": {"message": "quota"}}),
                     (200, {"candidates": [{"content": {"parts": [{"text": GOOD.replace("26", "99")}]}}]})):
            self.assertEqual(summarize(FACTS, self.cfg, lambda *a, r=resp: r)["source"], "template")


class GeminiModelDiscovery(unittest.TestCase):
    cfg = AIConfig("g-key", "retired-model", "gemini")
    LIST = {"models": [
        {"name": "models/gemini-2.0-flash", "supportedGenerationMethods": ["generateContent"]},
        {"name": "models/gemini-3.1-flash-lite-preview", "supportedGenerationMethods": ["generateContent"]},
        {"name": "models/gemini-3-flash", "supportedGenerationMethods": ["generateContent"]},
        {"name": "models/gemini-3-flash-image", "supportedGenerationMethods": ["generateContent"]},
        {"name": "models/gemini-embedding-001", "supportedGenerationMethods": ["embedContent"]},
        {"name": "models/gemma-3-27b", "supportedGenerationMethods": ["generateContent"]}]}

    def test_picker_prefers_stable_flash_and_skips_non_text_models(self):
        from src.explain import pick_gemini_model
        self.assertEqual(pick_gemini_model(self.LIST["models"]), "gemini-3-flash")
        self.assertIsNone(pick_gemini_model([{"name": "models/gemini-embedding-001", "supportedGenerationMethods": ["embedContent"]}]))

    def test_404_triggers_discovery_then_a_single_retry(self):
        from src import explain
        explain._MODEL_CACHE.clear()
        urls = []
        def http(url, headers, body):
            urls.append(url)
            return (404, {"error": {"message": "no longer available"}}) if "retired-model" in url else (200, {"candidates": [{"content": {"parts": [{"text": GOOD}]}}]})
        r = summarize(FACTS, self.cfg, http, lister=lambda url, headers: (200, self.LIST))
        self.assertEqual(r["source"], "gemini"); self.assertEqual(len(urls), 2); self.assertIn("gemini-3-flash", urls[1])
        urls.clear(); summarize(FACTS, self.cfg, http, lister=lambda *a: (200, self.LIST))
        self.assertEqual(len(urls), 1)  # the discovered name is remembered

    def test_discovery_is_not_used_for_other_errors_and_failures_fall_back(self):
        from src import explain
        explain._MODEL_CACHE.clear()
        def lister(*a): raise AssertionError("should not be called")
        self.assertEqual(summarize(FACTS, self.cfg, lambda *a: (429, {}), lister=lister)["source"], "template")
        self.assertEqual(summarize(FACTS, self.cfg, lambda *a: (404, {}), lister=lambda *a: (403, {}))["source"], "template")
