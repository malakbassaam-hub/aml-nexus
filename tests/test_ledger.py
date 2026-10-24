import json
import unittest
import xml.etree.ElementTree as ET
import numpy as np
from src import ledger
from src.benford import MIN_N, digit_profile, to_svg
from src.service import LEDGER_PATH, Workbench

F = dict(n_senders=26, new_share=1.0, struct=1.0, pas=0.9, repeat=0.0, big=1.0, unobs=False)
G = dict(n_senders=20, new_share=0.05, struct=0.0, pas=0.3, repeat=0.7, big=0.0, unobs=False)


class Ledger(unittest.TestCase):
    def test_training_learns_signs_and_smoothing_keeps_values_finite(self):
        samples = [(ledger.bin_features(F, "fan_in", 0.99), True)] * 6 + [(ledger.bin_features(G, "fan_in", 0.3), False)] * 6
        m = ledger.train(samples)
        self.assertGreater(m["structuring"]["80%+"], 0); self.assertLess(m["structuring"]["none"], 0)
        self.assertTrue(all(abs(d) < 60 for f in m.values() for d in f.values()))
        net_bad, _ = ledger.score(m, ledger.bin_features(F, "fan_in", 0.99)); net_ok, _ = ledger.score(m, ledger.bin_features(G, "fan_in", 0.3))
        self.assertGreater(net_bad, net_ok)
        t = ledger.pick_threshold(m, samples)
        self.assertTrue(net_bad >= t > net_ok)

    def test_entries_add_up_to_the_net_score(self):
        with open(LEDGER_PATH) as f:
            m = json.load(f)["model"]
        net, entries = ledger.score(m, ledger.bin_features(F, "slow_accumulation", None))
        self.assertAlmostEqual(net, sum(d for *_, d in entries), places=1)

    def test_unobservable_pass_through_gets_its_own_bin(self):
        self.assertEqual(ledger.bin_features({**F, "unobs": True}, "fan_in")["pass_through"], "not yet observable")

    def test_benford(self):
        self.assertIsNone(digit_profile(np.full(MIN_N - 1, 123.0)))
        rng = np.random.default_rng(0)
        conforming = 10 ** rng.uniform(1, 5, 4000)
        self.assertLess(digit_profile(conforming)["mad"], 0.01)
        structured = rng.uniform(8500, 9900, 200)
        p = digit_profile(structured)
        self.assertGreater(p["mad"], 0.1); ET.fromstring(to_svg(p))


class ServiceLedger(unittest.TestCase):
    def test_view_for_a_ring_and_not_applicable_for_a_loop(self):
        wb = Workbench(7); a = wb.load_scenario("1 - Ring forming")
        lv = wb.ledger_view(a, wb.case(a))
        self.assertIsNotNone(lv); self.assertEqual(len(lv["entries"]), 8); self.assertIn("flag", lv["verdict"].lower())
        a = wb.load_scenario("5 - Closed loop")
        self.assertIsNone(wb.ledger_view(a, wb.case(a)))

    def test_missing_model_file_hides_the_panel(self):
        wb = Workbench(7); wb.ledger = None; a = wb.load_scenario("1 - Ring forming")
        self.assertIsNone(wb.ledger_view(a, wb.case(a)))


if __name__ == "__main__":
    unittest.main()
