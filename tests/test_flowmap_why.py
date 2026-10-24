import unittest
import xml.etree.ElementTree as ET
from src.flowmap import H, W, build_geometry, to_svg
from src.service import Workbench
from src.why import breakdown, decision_path, what_would_change
from src.risk import recommend


class FlowMapWhy(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.wb = Workbench(7)

    def test_funnel_svg_is_wellformed_and_inside_the_canvas(self):
        a = self.wb.load_scenario("1 - Ring forming")
        geo = build_geometry(self.wb.tx, self.wb.acc, a, self.wb.now)
        self.assertEqual(geo["kind"], "funnel"); self.assertGreater(len(geo["senders"]), 5)
        ET.fromstring(to_svg(geo))
        for s in geo["senders"] + geo["outs"]:
            self.assertTrue(0 < s["y"] < H)

    def test_many_senders_are_capped_and_summarised(self):
        geo = build_geometry(self.wb.tx, self.wb.acc, "SHOP0", 60)
        self.assertLessEqual(len(geo["senders"]), 15)
        self.assertTrue(any(s.get("more") for s in geo["senders"]))
        ET.fromstring(to_svg(geo))

    def test_cycle_view(self):
        a = self.wb.load_scenario("5 - Closed loop")
        geo = build_geometry(self.wb.tx, self.wb.acc, a, self.wb.now, as_cycle=True)
        self.assertEqual(geo["kind"], "cycle"); self.assertTrue(3 <= len(geo["nodes"]) <= 5)
        self.assertEqual(sum(n["hub"] for n in geo["nodes"]), 1)
        ET.fromstring(to_svg(geo))

    def test_replay_shows_the_network_forming(self):
        a = self.wb.load_scenario("1 - Ring forming")
        early = build_geometry(self.wb.tx, self.wb.acc, a, self.wb.now - 8)
        late = build_geometry(self.wb.tx, self.wb.acc, a, self.wb.now)
        self.assertLess(len(early["senders"]), len(late["senders"]))

    def test_empty_period_does_not_crash(self):
        ET.fromstring(to_svg(build_geometry(self.wb.tx, self.wb.acc, "C0001", 3)))

    def test_breakdown_adds_up_exactly_for_every_case(self):
        for r in self.wb.cases_at(60).itertuples():
            b = breakdown(r)
            self.assertAlmostEqual(b["total_for"], r.suspicion, delta=0.004, msg=r.account)
            self.assertAlmostEqual(b["total_against"], r.counter, delta=0.004, msg=r.account)

    def test_decision_path_and_counterfactuals_are_consistent(self):
        for s, c in [(0.74, 0.15), (0.85, 0.0), (0.54, 0.48), (0.4, 0.7), (0.2, 0.0), (0.9, 0.5)]:
            tier, why = decision_path(s, c)
            self.assertEqual(tier, recommend(s, c)); self.assertIn(f"{s:.2f}", why)
            for line in what_would_change(s, c):
                self.assertTrue(line.startswith("If "))
        self.assertTrue(any("Verify" in l for l in what_would_change(0.74, 0.15)))


if __name__ == "__main__":
    unittest.main()
