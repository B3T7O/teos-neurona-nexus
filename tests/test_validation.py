import unittest
from copy import deepcopy

from core.validation import (
    validate_bitaxe_record,
    interpret_bitaxe_sensors,
    evaluate_thermal_status,
)


class TestBitaxeValidation(unittest.TestCase):

    def valid_record(self):
        return {
            "timestamp": "2026-10-20T05:30:00+00:00",
            "hashRate": 1070.0,
            "temp": 60.0,
            "vrTemp": 74.0,
            "temp2": -1,
            "fan2rpm": 0,
        }

    def test_valid_record(self):
        ok, message = validate_bitaxe_record(self.valid_record())
        self.assertTrue(ok, message)

    def test_non_dictionary_rejected(self):
        ok, _ = validate_bitaxe_record([])
        self.assertFalse(ok)

    def test_empty_record_rejected(self):
        ok, _ = validate_bitaxe_record({})
        self.assertFalse(ok)

    def test_missing_timestamp_rejected(self):
        record = self.valid_record()
        del record["timestamp"]
        ok, _ = validate_bitaxe_record(record)
        self.assertFalse(ok)

    def test_negative_hashrate_rejected(self):
        record = self.valid_record()
        record["hashRate"] = -1
        ok, _ = validate_bitaxe_record(record)
        self.assertFalse(ok)

    def test_boolean_hashrate_rejected(self):
        record = self.valid_record()
        record["hashRate"] = True
        ok, _ = validate_bitaxe_record(record)
        self.assertFalse(ok)

    def test_missing_hashrate_allowed_by_basic_validator(self):
        record = self.valid_record()
        del record["hashRate"]
        ok, _ = validate_bitaxe_record(record)
        self.assertTrue(ok)

    def test_validation_does_not_modify_record(self):
        record = self.valid_record()
        original = deepcopy(record)
        validate_bitaxe_record(record)
        self.assertEqual(record, original)

    def test_unavailable_temp2_is_identified(self):
        result = interpret_bitaxe_sensors(self.valid_record())
        self.assertEqual(result["temp2"], "no_disponible")

    def test_zero_fan2_is_not_declared_a_failure(self):
        result = interpret_bitaxe_sensors(self.valid_record())
        self.assertEqual(result["fan2rpm"], "cero_rpm_reportadas")

    def test_normal_temperatures(self):
        result = evaluate_thermal_status({
            "temp": 60.0,
            "vrTemp": 74.0,
        })
        self.assertEqual(result["status"], "normal")

    def test_asic_warning_threshold(self):
        result = evaluate_thermal_status({
            "temp": 70.0,
            "vrTemp": 74.0,
        })
        self.assertEqual(result["status"], "warning")

    def test_asic_critical_threshold(self):
        result = evaluate_thermal_status({
            "temp": 75.0,
            "vrTemp": 74.0,
        })
        self.assertEqual(result["status"], "critical")

    def test_regulator_warning_threshold(self):
        result = evaluate_thermal_status({
            "temp": 60.0,
            "vrTemp": 85.0,
        })
        self.assertEqual(result["status"], "warning")

    def test_missing_temperature_is_unknown(self):
        result = evaluate_thermal_status({
            "temp": 60.0,
        })
        self.assertEqual(result["status"], "unknown")

    def test_thermal_evaluation_does_not_modify_record(self):
        record = self.valid_record()
        original = deepcopy(record)
        evaluate_thermal_status(record)
        self.assertEqual(record, original)


    def test_negative_regulator_temperature_is_unknown(self):
        record = {"temp": 60.0, "vrTemp": -1.0}
        result = evaluate_thermal_status(record)
        self.assertEqual(result["sensors"]["vrTemp"]["status"], "unknown")
        self.assertEqual(result["status"], "unknown")

if __name__ == "__main__":
    unittest.main(verbosity=2)
