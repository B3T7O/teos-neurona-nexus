import json
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import urlopen

from core.validation import validate_bitaxe_record

URL = "http://192.168.1.100/api/system/info"
OUTPUT = Path(__file__).resolve().parent.parent / "data/raw/bitaxe_samples.jsonl"
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

    valid, message = validate_bitaxe_record(sample)
    if not valid:
        raise ValueError(message)

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
