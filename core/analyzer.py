"""Análisis y control de calidad de muestras Bitaxe."""

import json
import math
from datetime import datetime
from pathlib import Path
from statistics import mean
from core.validation import interpret_bitaxe_sensors
from core.validation import evaluate_thermal_status

DATA_FILE = (
    Path(__file__).resolve().parent.parent
    / "data/raw/bitaxe_samples.jsonl"
)


def is_number(value):
    """Acepta números finitos, pero no valores booleanos."""
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(value)
    )


def analyze():
    if not DATA_FILE.exists():
        print("No existe todavía el historial de muestras.")
        return

    samples = []
    damaged = 0

    with DATA_FILE.open("r", encoding="utf-8") as file:
        for line in file:
            try:
                item = json.loads(line)

                if not isinstance(item, dict):
                    damaged += 1
                    continue

                timestamp = item.get("timestamp")
                if not isinstance(timestamp, str):
                    damaged += 1
                    continue

                parsed_time = datetime.fromisoformat(
                    timestamp.replace("Z", "+00:00")
                )

                if parsed_time.tzinfo is None:
                    damaged += 1
                    continue

                item["_parsed_time"] = parsed_time
                samples.append(item)

            except (json.JSONDecodeError, ValueError, TypeError):
                damaged += 1

    samples.sort(key=lambda item: item["_parsed_time"])

    timestamps = [item["timestamp"] for item in samples]
    duplicates = len(timestamps) - len(set(timestamps))

    intervals = [
        (b["_parsed_time"] - a["_parsed_time"]).total_seconds()
        for a, b in zip(samples, samples[1:])
    ]

    abnormal_gaps = sum(seconds > 90 for seconds in intervals)

    hashrates = []
    hashrate_points = []
    invalid_hashrates = 0

    temperatures = []
    invalid_temperatures = 0

    vr_temperatures = []
    vr_temperature_points = []
    invalid_vr_temperatures = 0

    unavailable_temp2 = 0
    zero_fan2 = 0

    for item in samples:
        rate = item.get("hashRate")

        if is_number(rate) and rate >= 0:
            hashrates.append(rate)
            hashrate_points.append((item["_parsed_time"], rate))
        else:
            invalid_hashrates += 1

        temp = item.get("temp")

        if is_number(temp) and -50 <= temp <= 200:
            temperatures.append(temp)
        else:
            invalid_temperatures += 1

        vr_temp = item.get("vrTemp")
        if is_number(vr_temp) and 0 <= vr_temp <= 200:
            vr_temperatures.append(vr_temp)
            vr_temperature_points.append((item["_parsed_time"], vr_temp))
        else:
            invalid_vr_temperatures += 1

        temp2 = item.get("temp2")
        if temp2 == -1:
            unavailable_temp2 += 1

        fan2 = item.get("fan2rpm")
        if is_number(fan2) and fan2 == 0:
            zero_fan2 += 1

    print("=== TEOS NEURONA NEXUS ===")
    print(f"Muestras legibles: {len(samples)}")
    print(f"Líneas dañadas: {damaged}")
    print(f"Marcas de tiempo duplicadas: {duplicates}")
    print(f"Intervalos mayores de 90 s: {abnormal_gaps}")

    if intervals:
        print(f"Intervalo medio: {mean(intervals):.1f} segundos")

    print(f"Hashrates no válidos: {invalid_hashrates}")
    print(f"Temperaturas principales no válidas: {invalid_temperatures}")
    print(f"Lecturas temp2 no disponibles (-1): {unavailable_temp2}")
    print(f"Lecturas fan2 en cero: {zero_fan2}")

    sensor_states = {}
    for item in samples:
        for sensor, state in interpret_bitaxe_sensors(item).items():
            key = f"{sensor}: {state}"
            sensor_states[key] = sensor_states.get(key, 0) + 1

    print("\nInterpretación de sensores:")
    for state, count in sorted(sensor_states.items()):
        print(f"{state}: {count}")


    if hashrates:
        print(f"Hashrate medio: {mean(hashrates):.2f} GH/s")
        print(f"Hashrate mínimo: {min(hashrates):.2f} GH/s")
        print(f"Hashrate máximo: {max(hashrates):.2f} GH/s")

    print("\\n=== COMPARACIÓN DE VENTANAS DE HASHRATE ===")
    window_fields = (
        ("hashRate", "Instantáneo"),
        ("hashRate_1m", "1 minuto"),
        ("hashRate_10m", "10 minutos"),
        ("hashRate_1h", "1 hora"),
    )
    latest_windows = {}
    latest_window_sample = samples[-1] if samples else {}

    for field, label in window_fields:
        value = latest_window_sample.get(field)
        if is_number(value) and value >= 0:
            latest_windows[field] = value
            print(f"{label}: {value:.2f} GH/s")
        else:
            print(f"{label}: dato no disponible o no válido")

    instant = latest_windows.get("hashRate")
    for field, label in window_fields[1:]:
        reference = latest_windows.get(field)
        if instant is not None and reference is not None and reference > 0:
            delta = (instant / reference - 1) * 100
            print(f"Instantáneo frente a {label.lower()}: {delta:+.2f}%")

    window_history = {}
    for field, label in window_fields:
        valid_values = [
            item[field] for item in samples
            if is_number(item.get(field)) and item[field] >= 0
        ]
        if valid_values:
            window_history[field] = {
                "count": len(valid_values),
                "mean": round(mean(valid_values), 3),
                "latest": round(valid_values[-1], 3),
            }

    print("\n=== EVOLUCIÓN DEL HASHRATE ===")
    if len(hashrate_points) >= 2:
        first_time, first_rate = hashrate_points[0]
        last_time, last_rate = hashrate_points[-1]
        print(f"Primera muestra: {first_rate:.2f} GH/s ({first_time.isoformat()})")
        print(f"Última muestra: {last_rate:.2f} GH/s ({last_time.isoformat()})")
        if first_rate > 0:
            change = (last_rate - first_rate) / first_rate * 100
            print(f"Cambio entre ambas: {change:+.2f}%")
        else:
            print("Cambio porcentual: no calculable porque el valor inicial es cero.")
    else:
        print("Se necesitan al menos dos muestras válidas.")

    if temperatures:
        print(f"Temperatura media: {mean(temperatures):.2f} °C")
        print(f"Temperatura mínima: {min(temperatures):.2f} °C")
        print(f"Temperatura máxima: {max(temperatures):.2f} °C")

    print("\n=== TEMPERATURA DEL REGULADOR ===")
    print(f"Lecturas válidas: {len(vr_temperatures)}")
    print(f"Lecturas no válidas: {invalid_vr_temperatures}")
    if vr_temperatures:
        print(f"Promedio: {mean(vr_temperatures):.2f} °C")
        print(f"Máxima: {max(vr_temperatures):.2f} °C")
        print(f"Mínima: {min(vr_temperatures):.2f} °C")
    else:
        print("No hay lecturas válidas del regulador.")

    print("\n=== TENDENCIAS RECIENTES ===")
    if len(hashrate_points) >= 10:
        previous_rates = [v for _, v in hashrate_points[-10:-5]]
        recent_rates = [v for _, v in hashrate_points[-5:]]
        previous_avg = mean(previous_rates)
        recent_avg = mean(recent_rates)

        print("Hashrate:")
        print(f"  Bloque anterior: {previous_avg:.2f} GH/s")
        print(f"  Bloque reciente: {recent_avg:.2f} GH/s")
        if previous_avg > 0:
            change = (recent_avg - previous_avg) / previous_avg * 100
            direction = (
                "subiendo" if change > 0.5
                else "bajando" if change < -0.5
                else "estable"
            )
            print(f"  Cambio: {change:+.2f}% — {direction}")
        else:
            print("  Cambio porcentual no calculable: promedio inicial cero.")
    else:
        print("Hashrate: datos insuficientes (se requieren 10 muestras válidas).")

    if len(vr_temperature_points) >= 10:
        previous_temps = [v for _, v in vr_temperature_points[-10:-5]]
        recent_temps = [v for _, v in vr_temperature_points[-5:]]
        previous_avg = mean(previous_temps)
        recent_avg = mean(recent_temps)
        delta = recent_avg - previous_avg
        direction = (
            "subiendo" if delta > 0.5
            else "bajando" if delta < -0.5
            else "estable"
        )
        print("Temperatura del regulador:")
        print(f"  Bloque anterior: {previous_avg:.2f} °C")
        print(f"  Bloque reciente: {recent_avg:.2f} °C")
        print(f"  Diferencia: {delta:+.2f} °C — {direction}")
    else:
        print("Temperatura del regulador: datos insuficientes (se requieren 10 muestras válidas).")

    thermal_counts = {
        "normal": 0,
        "warning": 0,
        "critical": 0,
        "unknown": 0,
    }

    for item in samples:
        thermal = evaluate_thermal_status(item)
        thermal_counts[thermal["status"]] += 1

    print("\n=== EVALUACIÓN TÉRMICA ===")
    for status, count in thermal_counts.items():
        print(f"{status}: {count} muestras")

    if samples:
        latest = evaluate_thermal_status(samples[-1])
        print(f"Estado térmico más reciente: {latest['status']}")
        print(f"Motivo: {latest['reason']}")

    # Informe operativo de la última muestra.
    latest_sample = samples[-1] if samples else {}
    sensor_states = interpret_bitaxe_sensors(latest_sample) if samples else {}
    thermal = evaluate_thermal_status(latest_sample) if samples else {
        "status": "unknown",
        "reason": "No hay muestras disponibles",
        "sensors": {},
    }

    print("\n=== ESTADO OPERATIVO ACTUAL ===")
    alerts = []
    if samples:
        for field, label, unit in (
            ("hashRate", "Hashrate", "GH/s"),
            ("temp", "Temperatura ASIC", "°C"),
            ("vrTemp", "Temperatura regulador", "°C"),
        ):
            value = latest_sample.get(field)
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                print(f"{label}: {value:.3f} {unit}")
            else:
                print(f"{label}: lectura no disponible o no válida")

        print(f"Estado térmico: {thermal['status']}")
        print(f"Evaluación: {thermal['reason']}")

        for name, sensor in thermal["sensors"].items():
            if sensor["status"] in ("warning", "critical", "unknown"):
                alerts.append(f"{name}: {sensor['reason']}")

        if sensor_states.get("temp2") == "no_disponible":
            print("Sensor temp2: no disponible (reporta -1).")
        if sensor_states.get("fan2rpm") == "cero_rpm_reportadas":
            print("Aviso: fan2rpm reporta 0 RPM; esto no confirma una avería.")

        if alerts:
            print("Alertas:")
            for alert in alerts:
                print(f"- {alert}")
        else:
            print("Alertas térmicas: ninguna según los umbrales configurados.")
    else:
        print("Sin muestras para evaluar el estado operativo.")

    # Guardar un resumen de esta ejecución sin modificar las muestras originales.
    history_file = (
        Path(__file__).resolve().parent.parent
        / "data/processed/analysis_history.jsonl"
    )
    history_file.parent.mkdir(parents=True, exist_ok=True)

    record = {
        "analysis_time": datetime.now().astimezone().isoformat(),
        "sample_count": len(samples),
        "valid_hashrate_count": len(hashrates),
        "hashrate_mean": round(mean(hashrates), 3) if hashrates else None,
        "hashrate_min": round(min(hashrates), 3) if hashrates else None,
        "hashrate_max": round(max(hashrates), 3) if hashrates else None,
        "asic_temp_mean": round(mean(temperatures), 3) if temperatures else None,
        "vr_temp_count": len(vr_temperatures),
        "vr_temp_mean": round(mean(vr_temperatures), 3) if vr_temperatures else None,
        "vr_temp_max": round(max(vr_temperatures), 3) if vr_temperatures else None,
        "hashrate_windows": window_history,
        "latest_hashrate": latest_sample.get("hashRate"),
        "latest_asic_temp": latest_sample.get("temp"),
        "latest_vr_temp": latest_sample.get("vrTemp"),
        "latest_sensor_states": sensor_states,
        "latest_thermal_sensors": thermal["sensors"],
        "latest_alerts": alerts,
        "thermal_status": latest["status"] if samples else "unknown",
        "recent_hashrate_change_pct": None,
        "recent_vr_temp_change_c": None,
    }

    if len(hashrate_points) >= 10:
        previous = mean(v for _, v in hashrate_points[-10:-5])
        recent = mean(v for _, v in hashrate_points[-5:])
        if previous > 0:
            record["recent_hashrate_change_pct"] = round(
                (recent - previous) / previous * 100, 3
            )

    if len(vr_temperature_points) >= 10:
        previous = mean(v for _, v in vr_temperature_points[-10:-5])
        recent = mean(v for _, v in vr_temperature_points[-5:])
        record["recent_vr_temp_change_c"] = round(recent - previous, 3)

    with history_file.open("a", encoding="utf-8") as file:
        file.write(json.dumps(record, ensure_ascii=False) + "\n")

    print(f"Resumen guardado en: {history_file}")



if __name__ == "__main__":
    analyze()
