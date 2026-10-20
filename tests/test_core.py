import unittest
from src.data_gen import generate
from src.detectors import find_cycles
from src.risk import build_cases, recommend


class Core(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.acc, cls.tx = generate(7)
        cls.cases = build_cases(cls.tx, cls.acc)
        cls.tier = cls.cases.set_index("account")["tier"].to_dict()
        cls.role = cls.acc.set_index("account")["role"].to_dict()

    def test_deterministic(self):
        a2, t2 = generate(7)
        self.assertTrue(self.tx.equals(t2) and self.acc.equals(a2))

    def test_has_all_categories(self):
        self.assertTrue({"normal", "legit_hub", "laundering", "external"} <= set(self.acc.label))
        self.assertTrue({"collector", "stealth_collector", "cycle_member", "shop", "charity", "friend_cycle"} <= set(self.acc.role))

    def test_finds_every_planted_cycle_and_no_friend_loop(self):
        found = [set(c["nodes"]) for c in find_cycles(self.tx, self.acc)]
        for c in range(4):
            planted = {a for a in self.acc.account if a.startswith(f"LC{c}_")}
            self.assertIn(planted, found)
        self.assertFalse(any(n.startswith("FR") for s in found for n in s))

    def test_typical_collectors_are_flagged(self):
        for a, r in self.role.items():
            if r == "collector":
                self.assertIn(self.tier.get(a), ("Monitor", "Escalate"), a)

    def test_legit_hubs_never_reach_freeze_level(self):
        for a, r in self.role.items():
            if r in ("shop", "charity", "payroll"):
                self.assertNotEqual(self.tier.get(a, "Clear"), "Escalate", a)

    def test_shops_show_counter_evidence(self):
        shops = self.cases[self.cases.account.str.startswith("SHOP")]
        self.assertTrue(len(shops) == 0 or all(len(x) > 0 for x in shops.counter_evidence))

    def test_tier_boundaries(self):
        self.assertEqual(recommend(0.9, 0.1), "Escalate")
        self.assertEqual(recommend(0.9, 0.5), "Monitor")
        self.assertEqual(recommend(0.55, 0.7), "Verify")
        self.assertEqual(recommend(0.4, 0.7), "Clear")
        self.assertEqual(recommend(0.4, 0.2), "Verify")
        self.assertEqual(recommend(0.1, 0.0), "Clear")


if __name__ == "__main__":
    unittest.main()
