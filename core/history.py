"""Consulta del historial de análisis de TEOS NEURONA NEXUS."""

import json
from pathlib import Path
from statistics import mean

HISTORY_FILE = (
    Path(__file__).resolve().parent.parent
    / "data/processed/analysis_history.jsonl"
)


def load_history():
    """Carga los registros válidos e informa si encuentra líneas dañadas."""
    records = []
    damaged = 0

    if not HISTORY_FILE.exists():
        return records, damaged

    with HISTORY_FILE.open(encoding="utf-8") as file:
        for line in file:
            try:
                item = json.loads(line)
                if isinstance(item, dict):
                    records.append(item)
                else:
                    damaged += 1
            except json.JSONDecodeError:
                damaged += 1

    return records, damaged


def main():
    records, damaged = load_history()

    print("=== HISTORIAL TEOS NEURONA NEXUS ===")
    print(f"Análisis guardados: {len(records)}")
    print(f"Registros dañados: {damaged}")

    if not records:
        print("Todavía no hay análisis disponibles.")
        return

    latest = records[-1]
    print(f"Última ejecución: {latest.get('analysis_time', 'desconocida')}")
    print(f"Muestras: {latest.get('sample_count', 'N/D')}")
    print(f"Hashrate medio: {latest.get('hashrate_mean', 'N/D')} GH/s")
    print(f"Temperatura ASIC media: {latest.get('asic_temp_mean', 'N/D')} °C")
    print(f"Temperatura regulador media: {latest.get('vr_temp_mean', 'N/D')} °C")
    print(f"Estado térmico: {latest.get('thermal_status', 'unknown')}")
    print("\\n--- ESTADO OPERATIVO MÁS RECIENTE ---")
    for key, label, unit in (
        ("latest_hashrate", "Hashrate actual", "GH/s"),
        ("latest_asic_temp", "Temperatura ASIC actual", "°C"),
        ("latest_vr_temp", "Temperatura regulador actual", "°C"),
    ):
        value = latest.get(key)
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            print(f"{label}: {value:.3f} {unit}")
        else:
            print(f"{label}: no registrado")

    sensor_states = latest.get("latest_sensor_states", {})
    if isinstance(sensor_states, dict):
        for name, state in sensor_states.items():
            print(f"Sensor {name}: {state}")

    if "latest_alerts" not in latest:
        print("Alertas: no disponibles (registro antiguo)")
    else:
        alerts = latest["latest_alerts"]
        if isinstance(alerts, list) and alerts:
            print("Alertas registradas:")
            for alert in alerts:
                print(f"- {alert}")
        elif isinstance(alerts, list):
            print("Alertas térmicas: ninguna según los umbrales configurados.")
        else:
            print("Alertas: campo registrado con formato no válido")


    rates = [
        item["hashrate_mean"]
        for item in records
        if isinstance(item.get("hashrate_mean"), (int, float))
        and not isinstance(item.get("hashrate_mean"), bool)
    ]

    if rates:
        print(f"Promedio entre ejecuciones: {mean(rates):.3f} GH/s")
        print(f"Primer promedio registrado: {rates[0]:.3f} GH/s")
        print(f"Último promedio registrado: {rates[-1]:.3f} GH/s")

        if len(rates) >= 2 and rates[0] != 0:
            change = (rates[-1] - rates[0]) / rates[0] * 100
            print(f"Cambio entre ejecuciones extremas: {change:+.3f}%")
        else:
            print("Se necesitan dos ejecuciones para comparar el historial.")


if __name__ == "__main__":
    main()
