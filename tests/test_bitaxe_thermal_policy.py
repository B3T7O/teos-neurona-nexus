import unittest


def thermal_policy(freq, asic_temp, vr_temp, allowed_freq):
    target = freq
    reason = "Sin cambios"
    if asic_temp >= 70 or vr_temp >= 80:
        lower = [f for f in allowed_freq if f < freq]
        if lower:
            target = max(lower)
            reason = "Reducir frecuencia por temperatura elevada"
        else:
            reason = "Temperatura elevada; sin frecuencia inferior disponible"
    return target, reason


class TestBitaxeThermalPolicy(unittest.TestCase):
    options = [400, 490, 525, 550, 600, 625]

    def test_normal_conditions_keep_frequency(self):
        target, _ = thermal_policy(525, 60, 73, self.options)
        self.assertEqual(target, 525)

    def test_asic_threshold_reduces_frequency(self):
        target, _ = thermal_policy(525, 70, 73, self.options)
        self.assertEqual(target, 490)

    def test_vr_threshold_reduces_frequency(self):
        target, _ = thermal_policy(525, 60, 80, self.options)
        self.assertEqual(target, 490)

    def test_no_lower_frequency_does_not_increase(self):
        target, reason = thermal_policy(400, 75, 82, self.options)
        self.assertEqual(target, 400)
        self.assertIn("sin frecuencia inferior", reason)


if __name__ == "__main__":
    unittest.main()
