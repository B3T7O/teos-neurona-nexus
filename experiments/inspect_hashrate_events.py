import json
from datetime import datetime
from pathlib import Path

root = Path(".")
source = root / "data/raw/bitaxe_samples.marked.jsonl"
report = root / "experiments/hashrate_audit_report.json"

audit = json.loads(report.read_text(encoding="utf-8"))
events = audit["absolute_error_outliers"]["examples"]

rows = []
with source.open(encoding="utf-8") as f:
    for line in f:
        try:
            row = json.loads(line)
            ts = datetime.fromisoformat(
                row["timestamp"].replace("Z", "+00:00")
            )
            row["_ts"] = ts
            rows.append(row)
        except (ValueError, KeyError, TypeError, json.JSONDecodeError):
            continue

rows.sort(key=lambda r: r["_ts"])

fields = [
    "hashRate", "hashRate_1m", "hashRate_10m", "hashRate_1h",
    "frequency", "temp", "temp2", "power", "voltage", "vrTemp",
    "errorPercentage", "sharesAccepted", "sharesRejected",
]

print("TEOS NEURONA — CONTEXTO DE EVENTOS")
print("Solo lectura; se muestran hasta 2 muestras antes y después.")

for n, event in enumerate(events, 1):
    target = datetime.fromisoformat(
        event["timestamp"].replace("Z", "+00:00")
    )
    idx = min(
        range(len(rows)),
        key=lambda i: abs((rows[i]["_ts"] - target).total_seconds())
    )

    print(f"\n{'=' * 18} EVENTO {n} {'=' * 18}")
    print(f"Error de referencia: {event['absolute_error_ghs']:.2f} GH/s")
    print(f"Salto previo: {event['change_from_previous_ghs']:.2f} GH/s")

    for j in range(max(0, idx - 2), min(len(rows), idx + 3)):
        row = rows[j]
        marker = ">>" if j == idx else "  "
        values = " | ".join(
            f"{key}={row[key]}"
            for key in fields if row.get(key) is not None
        )
        print(f"{marker} {row.get('timestamp', '?')} | {values}")
