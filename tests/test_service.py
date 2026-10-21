import unittest
from src.service import SCENARIOS, Workbench


class ServiceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.base = Workbench(7)

    def fresh(self):
        wb = Workbench.__new__(Workbench)
        wb.__dict__.update(self.base.__dict__)
        wb.audit, wb.watches, wb.closed, wb.reviews, wb.decisions = type(self.base.audit)(), {}, {}, [], {}
        return wb

    def test_every_scenario_loads_a_visible_case(self):
        for name in SCENARIOS:
            wb = self.fresh()
            a = wb.load_scenario(name)
            self.assertIsNotNone(wb.case(a), f"{name}: {a} has no case at day {wb.now}")
            self.assertNotEqual(wb.case(a).tier, "Clear", name)

    def test_queue_excludes_clear_and_is_sorted(self):
        wb = self.fresh(); wb.now = 60
        q = wb.queue()
        self.assertTrue((q.tier != "Clear").all())
        order = {"Escalate": 0, "Monitor": 1, "Verify": 2}
        self.assertEqual(list(q.tier.map(order)), sorted(q.tier.map(order)))
        self.assertIn("synthetic_truth", wb.queue(reveal=True).columns)

    def test_watch_lifecycle(self):
        wb = self.fresh(); a = wb.load_scenario("1 - Ring forming")
        wb.start_watch(a, "internal_policy", "gather evidence", "rev1", 30, seconds=30, opened_counter_evidence=True)
        with self.assertRaises(ValueError): wb.start_watch(a, "internal_policy", "again", "rev1", 30)
        wb.advance(7)
        traj = wb.trajectory(a)
        self.assertEqual(list(traj.columns), ["day", "suspicion", "counter", "tier"])
        self.assertTrue(traj.day.is_monotonic_increasing)
        p = wb.packet(a)
        self.assertIn("now", p); self.assertFalse(p["expired"])
        wb.decide_watch(a, "rev1", "Escalate", "evidence confirmed")
        self.assertIn("closed", wb.watch_status(a))
        self.assertTrue(wb.audit.verify())

    def test_expired_watch_stops_collecting_but_packet_still_works(self):
        wb = self.fresh(); a = wb.load_scenario("1 - Ring forming")
        wb.start_watch(a, "internal_policy", "gather evidence", "rev1", 5)
        wb.advance(14)
        self.assertEqual(wb.watch_status(a), "expired")
        self.assertTrue(wb.packet(a)["expired"])

    def test_escalation_blocked_until_counter_evidence_read_and_reason_given(self):
        wb = self.fresh(); a = wb.load_scenario("1 - Ring forming")
        self.assertEqual(wb.case(a).tier, "Monitor")
        wb.now += 4
        a2 = wb.queue().query("tier == 'Escalate'").account.iloc[0]
        self.assertFalse(wb.decide_case("rev1", a2, "Escalate", "looks bad", 5, False)[0])
        self.assertFalse(wb.decide_case("rev1", a2, "Escalate", " ", 5, True)[0])
        self.assertTrue(wb.decide_case("rev1", a2, "Escalate", "evidence reviewed", 60, True)[0])

    def test_simulated_reviewers_trigger_and_clear_the_guard(self):
        wb = self.fresh()
        wb.simulate_reviewers("fast"); wb.simulate_reviewers("careful")
        q = wb.quality()
        self.assertTrue(q["reviewer_B (simulated)"]["possible_rubber_stamping"])
        self.assertFalse(q["reviewer_A (simulated)"]["possible_rubber_stamping"])


if __name__ == "__main__":
    unittest.main()
