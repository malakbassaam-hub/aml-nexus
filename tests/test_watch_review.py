import unittest
from src.audit import AuditLog
from src.data_gen import generate
from src.review import Review, bias_report, can_submit
from src.watch import KeepOpen, EvidenceWatch


class KeepOpenTests(unittest.TestCase):
    def mk(self, **k):
        d = dict(account="X", basis="internal_policy", purpose="enhanced monitoring", requested_by="rev1", start_day=10, duration_days=30)
        return KeepOpen(**{**d, **k})

    def test_requires_purpose_and_valid_duration(self):
        with self.assertRaises(ValueError): self.mk(purpose=" ")
        with self.assertRaises(ValueError): self.mk(duration_days=91)
        with self.assertRaises(ValueError): self.mk(basis="law_enforcement_request", duration_days=181)
        self.mk(basis="law_enforcement_request", duration_days=180)

    def test_expiry_review_and_extension(self):
        k = self.mk(duration_days=60)           # runs day 10..70
        self.assertEqual(k.status(15), "active")
        self.assertEqual(k.status(40), "review_due")
        k.reviews.append(40)
        self.assertEqual(k.status(45), "active")
        self.assertEqual(k.status(70), "expired")
        with self.assertRaises(ValueError): k.extend(10, "", "boss", 20)
        k.extend(10, "new written request", "boss", 20)
        self.assertEqual(k.end_day, 80)
        with self.assertRaises(ValueError): k.extend(10, "late", "boss", 90)


class WatchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.acc, cls.tx = generate(7)

    def watch(self, account, start, dur=30):
        log = AuditLog()
        ko = KeepOpen(account, "internal_policy", "gather more evidence", "rev1", start, dur)
        return EvidenceWatch(self.tx, self.acc, ko, log), log

    def test_collector_stays_flagged_and_expiry_blocks_collection(self):
        first = int(self.tx[self.tx.dst == "COL0"].day.min())
        w, log = self.watch("COL0", first + 2, dur=10)
        self.assertIn(w.snapshot(first + 9)["tier"], ("Monitor", "Escalate"))
        with self.assertRaises(PermissionError): w.snapshot(first + 2 + 10)
        self.assertTrue(log.verify())

    def test_links_need_transfers_and_in_bank_accounts(self):
        w, log = self.watch("SHOP0", 40)
        sugg = w.suggest_links(45)
        self.assertTrue(all("transfers" in s["reason"] for s in sugg))
        suggested = {s["account"] for s in sugg}
        stranger = next(a for a in self.acc.account if a not in suggested and a != "SHOP0")
        with self.assertRaises(ValueError): w.approve_link(stranger, "rev1", 45)
        out = [s["account"] for s in sugg if not s["monitorable"]]
        if out:
            with self.assertRaises(ValueError): w.approve_link(out[0], "rev1", 45)

    def test_decisions_need_written_reason_and_are_audited(self):
        w, log = self.watch("COL0", 30)
        with self.assertRaises(ValueError): w.decide("rev1", "Clear", " ", 35)
        w.decide("rev1", "Escalate", "evidence confirmed", 35)
        self.assertEqual(log.entries[-1]["action"], "decision_escalate")

    def test_audit_chain_detects_tampering(self):
        w, log = self.watch("COL0", 30)
        w.decide("rev1", "Clear", "reason", 35)
        self.assertTrue(log.verify())
        log.entries[0]["detail"]["purpose"] = "changed"
        self.assertFalse(log.verify())


class ReviewTests(unittest.TestCase):
    def test_flags_fast_agreeing_reviewer_but_not_attentive_one(self):
        fast = [Review("a", f"c{i}", "Escalate", "Escalate", 6, False) for i in range(12)]
        careful = [Review("b", f"c{i}", "Escalate", "Escalate" if i % 3 else "Verify", 90, True) for i in range(12)]
        rep = bias_report(fast + careful)
        self.assertTrue(rep["a"]["possible_rubber_stamping"])
        self.assertFalse(rep["b"]["possible_rubber_stamping"])

    def test_too_few_cases_never_flagged(self):
        self.assertFalse(bias_report([Review("a", "c", "Escalate", "Escalate", 1, False)])["a"]["possible_rubber_stamping"])

    def test_friction_blocks_unread_escalation(self):
        self.assertFalse(can_submit("Escalate", "Escalate", False)[0])
        self.assertTrue(can_submit("Escalate", "Escalate", True)[0])
        self.assertTrue(can_submit("Escalate", "Verify", False)[0])


if __name__ == "__main__":
    unittest.main()
