import unittest

from core.reference_guard import (
    guard_references,
    build_safe_forecasts,
    select_available_method,
)


class ReferenceGuardIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.samples = [
            {
                "actual": 1070.0,
                "rate_10m": 1068.0,
                "rate_1h": 1072.0,
            }
            for _ in range(8)
        ]

    def test_blocked_reference_uses_safe_fallback(self):
        samples = self.samples + [{
            "actual": 1080.0,
            "rate_10m": 1075.0,
            "rate_1h": 81806.5,
        }]

        guarded = guard_references(samples)
        forecasts = build_safe_forecasts(guarded)
        selected = select_available_method("referencia_1h", forecasts)

        self.assertNotIn("referencia_1h", forecasts)
        self.assertIn(selected, forecasts)
        self.assertEqual(forecasts[selected], 1080.0)
        self.assertFalse(guarded[-1]["rate_1h_valid"])
        self.assertEqual(guarded[-1]["rate_1h"], 81806.5)

    def test_insufficient_history_still_has_safe_fallback(self):
        guarded = guard_references(self.samples[:4])
        forecasts = build_safe_forecasts(guarded)
        selected = select_available_method("referencia_1h", forecasts)

        self.assertNotIn("referencia_1h", forecasts)
        self.assertNotIn("referencia_10m", forecasts)
        self.assertEqual(selected, "ultimo_hashrate")
        self.assertEqual(forecasts[selected], 1070.0)

    def test_selected_base_is_available_for_adaptive_prediction(self):
        samples = self.samples + [{
            "actual": 1080.0,
            "rate_10m": 1075.0,
            "rate_1h": 81806.5,
        }]

        guarded = guard_references(samples)
        forecasts = build_safe_forecasts(guarded)
        selected = select_available_method("referencia_1h", forecasts)

        # Simula la entrada del predictor online; no modifica su estado real.
        base_forecast = forecasts[selected]
        simulated_online_prediction = base_forecast + 2.0

        self.assertEqual(base_forecast, 1080.0)
        self.assertEqual(simulated_online_prediction, 1082.0)
        self.assertNotEqual(base_forecast, 81806.5)


if __name__ == "__main__":
    unittest.main()
