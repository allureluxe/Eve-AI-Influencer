import unittest
from gold_bot.lab import fingerprint, _aggregate

class TestStrategyLab(unittest.TestCase):
    def test_fingerprint_deterministe(self):
        a = {"name":"x","min_adx":16.0}
        self.assertEqual(fingerprint(a), fingerprint({"min_adx":16.0,"name":"x"}))

    def test_aggregate_recalcule_les_seuils(self):
        out = _aggregate([
            {"trades":60,"wins":30,"losses":30,"profit":120.0,"gross_w":180.0,"gross_l":60.0},
            {"trades":50,"wins":25,"losses":25,"profit":50.0,"gross_w":100.0,"gross_l":50.0},
        ])
        self.assertEqual(out["trades"],110)
        self.assertEqual(out["win_rate"],50.0)
        self.assertEqual(out["profit_factor"],2.545)
        self.assertGreater(out["payoff"],1.0)

if __name__ == "__main__":
    unittest.main()
