# Copyright (c) 2026 Luis Alberto Siguencia Andrade (B3T7O)
# SPDX-License-Identifier: Apache-2.0
#
# TEOS Neurona Nexus - Reference Implementation
# https://github.com/[TU_USUARIO]/teos-neurona-nexus

import json
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import urlopen

from core.validation import validate_bitaxe_record
from core.sample_quality import classify

import os
BITAXE_IP = os.environ.get("BITAXE_IP", "192.168.1.100")
URL = f"http://{BITAXE_IP}/api/system/info"
OUTPUT = Path(__file__).resolve().parent.parent / "data/raw/bitaxe_samples.marked.jsonl"
INTERVAL = 60

FIELDS = (
    "hashRate", "hashRate_1m", "hashRate_10m", "hashRate_1h",
    "expectedHashrate", "temp", "temp2", "vrTemp", "frequency",
    "power", "voltage", "current", "errorPercentage",
    "sharesAccepted", "sharesRejected", "poolDifficulty",
    "bestDiff", "bestSessionDiff", "uptimeSeconds", "wifiRSSI",
    "fanrpm", "fan2rpm", "networkDifficulty", "blockHeight",
)

def capture():
    with urlopen(URL, timeout=5) as response:
        device = json.load(response)

    sample = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "source": "bitaxe_api_system_info",
    }

    for field in FIELDS:
        if field in device:
            sample[field] = device[field]

    sample["quality"] = classify(sample)

    valid, message = validate_bitaxe_record(sample)
    if not valid:
        raise ValueError(message)

    if sample["quality"] != "ok":
        print(f"  ADVERTENCIA: sample marcado como {sample['quality']}")

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT.open("a", encoding="utf-8") as file:
        file.write(json.dumps(sample) + "\n")

    print(
        f"{sample['timestamp']} | "
        f"Hashrate: {sample.get('hashRate')} GH/s | "
        f"Temperatura: {sample.get('temp')} °C"
    )

def main():
    print("TEOS NEURONA NEXUS: captura Bitaxe")
    print("Una muestra cada 60 segundos. Detener con Ctrl+C.")

    try:
        while True:
            start = time.monotonic()
            try:
                capture()
            except Exception as error:
                print(f"Error de captura: {error}")

            time.sleep(max(0, INTERVAL - (time.monotonic() - start)))
    except KeyboardInterrupt:
        print("\nCaptura detenida. Las muestras guardadas se conservan.")

if __name__ == "__main__":
    main()
