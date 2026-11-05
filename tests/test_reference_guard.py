import unittest

from core.learning_loop_v2 import filter_contextual_anomalies
from core.reference_guard import (guard_references, build_safe_forecasts, select_available_method)


class ReferenceGuardTests(unittest.TestCase):
    def setUp(self):
        self.samples = [
            {
                "timestamp": f"normal-{i}",
                "actual": 1070.0,
                "rate_10m": 1070.0,
                "rate_1h": 1070.0,
            }
            for i in range(8)
        ]

        self.samples += [
            {
                "timestamp": "pico-sintetico",
                "actual": 81806.5,
                "rate_10m": 1070.0,
                "rate_1h": 1070.0,
            },
            {
                "timestamp": "posterior-sintetica",
                "actual": 1080.0,
                "rate_10m": 1075.0,
                "rate_1h": 81806.5,
            },
        ]

    def test_anomaly_filtered_and_suspicious_reference_flagged(self):
        filtered = filter_contextual_anomalies(self.samples)
        guarded = guard_references(filtered)

        self.assertEqual(len(filtered), 9)
        self.assertNotIn(
            "pico-sintetico",
            [s["timestamp"] for s in guarded],
        )

        posterior = next(
            s for s in guarded
            if s["timestamp"] == "posterior-sintetica"
        )

        self.assertFalse(posterior["rate_1h_valid"])
        self.assertEqual(
            posterior["rate_1h_guard_reason"],
            "referencia_supera_limite_contextual",
        )

        # La referencia original se conserva, no se sobrescribe.
        self.assertEqual(posterior["rate_1h"], 81806.5)

    def test_normal_references_remain_valid(self):
        guarded = guard_references(self.samples[:8])
        last = guarded[-1]

        self.assertTrue(last["rate_10m_valid"])
        self.assertTrue(last["rate_1h_valid"])
        self.assertEqual(last["rate_1h"], 1070.0)

    def test_invalid_reference_is_not_used_for_forecast(self):
        filtered = filter_contextual_anomalies(self.samples)
        guarded = guard_references(filtered)
        forecasts = build_safe_forecasts(guarded)

        self.assertNotIn("referencia_1h", forecasts)
        self.assertIn("referencia_10m", forecasts)
        self.assertIn("ultimo_hashrate", forecasts)

    def test_insufficient_history_blocks_reference(self):
        guarded = guard_references(self.samples[:4])
        forecasts = build_safe_forecasts(guarded)

        self.assertNotIn("referencia_10m", forecasts)
        self.assertNotIn("referencia_1h", forecasts)

    def test_unavailable_preferred_method_uses_available_fallback(self):
        forecasts = {
            "ultimo_hashrate": 1070.0,
            "media_ultimas_5": 1068.0,
        }
        self.assertEqual(
            select_available_method("referencia_1h", forecasts),
            "ultimo_hashrate",
        )

    def test_no_available_method_returns_none(self):
        self.assertIsNone(select_available_method("referencia_1h", {}))

    def test_input_is_not_modified(self):
        original = [dict(s) for s in self.samples]
        guard_references(original)

        self.assertEqual(original, self.samples)
        self.assertNotIn("rate_1h_valid", original[-1])


if __name__ == "__main__":
    unittest.main(verbosity=2)
