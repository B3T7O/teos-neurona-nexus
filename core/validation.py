"""Validación básica de métricas de TEOS NEURONA NEXUS."""

from math import isfinite


def validate_bitaxe_record(record: dict) -> tuple[bool, str]:
    """Valida un registro de métricas sin modificarlo."""

    if not isinstance(record, dict):
        return False, "El registro debe ser un objeto"

    if not record:
        return False, "El registro está vacío"

    timestamp = record.get("timestamp")
    if not isinstance(timestamp, str) or not timestamp.strip():
        return False, "Falta un timestamp válido"

    hashrate = record.get("hashRate")
    if hashrate is not None:
        if (
            isinstance(hashrate, bool)
            or not isinstance(hashrate, (int, float))
            or not isfinite(hashrate)
            or hashrate < 0
        ):
            return False, "hashRate debe ser un número finito no negativo"

    return True, "Registro válido"

def interpret_bitaxe_sensors(record: dict) -> dict:
    """Interpreta lecturas conocidas sin modificar el registro original."""
    result = {}

    temp2 = record.get("temp2")
    if isinstance(temp2, (int, float)) and not isinstance(temp2, bool):
        if temp2 == -1:
            result["temp2"] = "no_disponible"
        elif isfinite(temp2) and -50 <= temp2 <= 200:
            result["temp2"] = "lectura_disponible"
        else:
            result["temp2"] = "valor_sospechoso"
    else:
        result["temp2"] = "ausente_o_no_numerico"

    fan2 = record.get("fan2rpm")
    if isinstance(fan2, (int, float)) and not isinstance(fan2, bool):
        if not isfinite(fan2) or fan2 < 0:
            result["fan2rpm"] = "valor_sospechoso"
        elif fan2 == 0:
            result["fan2rpm"] = "cero_rpm_reportadas"
        else:
            result["fan2rpm"] = "rpm_reportadas"
    else:
        result["fan2rpm"] = "ausente_o_no_numerico"

    return result

def evaluate_thermal_status(record: dict) -> dict:
    """Evalúa temperaturas y devuelve estados; no controla el hardware."""
    if not isinstance(record, dict):
        return {"status": "unknown", "sensors": {},
                "reason": "Registro no válido"}

    sensors = {}

    rules = {
        "temp": (70.0, 75.0),
        "vrTemp": (85.0, 100.0),
    }

    for name, (warning_at, critical_at) in rules.items():
        value = record.get(name)

        if (
            not isinstance(value, (int, float))
            or isinstance(value, bool)
            or not isfinite(value)
            or value < (0 if name == "vrTemp" else -50)
            or value > 200
        ):
            sensors[name] = {
                "status": "unknown",
                "value": value,
                "reason": "Lectura ausente o no válida",
            }
        elif value >= critical_at:
            sensors[name] = {
                "status": "critical",
                "value": value,
                "reason": f"Temperatura igual o superior a {critical_at:g} °C",
            }
        elif value >= warning_at:
            sensors[name] = {
                "status": "warning",
                "value": value,
                "reason": f"Temperatura igual o superior a {warning_at:g} °C",
            }
        else:
            sensors[name] = {
                "status": "normal",
                "value": value,
                "reason": "Por debajo del umbral de advertencia",
            }

    states = [sensor["status"] for sensor in sensors.values()]

    if "critical" in states:
        overall = "critical"
    elif "warning" in states:
        overall = "warning"
    elif all(state == "normal" for state in states):
        overall = "normal"
    else:
        overall = "unknown"

    return {
        "status": overall,
        "sensors": sensors,
        "reason": {
            "normal": "Temperaturas dentro de los umbrales definidos",
            "warning": "Se requiere atención térmica",
            "critical": "Temperatura crítica: revisar el equipo",
            "unknown": "No hay datos suficientes para confirmar el estado",
        }[overall],
    }

