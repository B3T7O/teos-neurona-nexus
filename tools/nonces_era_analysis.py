#!/usr/bin/env python3
import json
import statistics
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
NONCES_FILE = ROOT / "data" / "processed" / "nonces_10k.json"

def analyze_era(nonces, name):
    if not nonces:
        return None
    values = [n["nonce"] for n in nonces]
    print(f"\n📊 ERA: {name} ({len(values):,} nonces)")
    print(f"  Media:       {statistics.mean(values):,.0f}")
    print(f"  Mediana:     {statistics.median(values):,.0f}")
    print(f"  Desv. Est.:  {statistics.stdev(values):,.0f}")
    print(f"  Mín / Máx:   {min(values):,} / {max(values):,}")

def main():
    print("🔬 ANÁLISIS ESTADÍSTICO DE NONCES POR ERA\n")
    with NONCES_FILE.open("r", encoding="utf-8") as f:
        all_nonces = json.load(f)

    era1 = [n for n in all_nonces if 0 < n.get("height", 0) <= 500_000]
    era2 = [n for n in all_nonces if 500_000 < n.get("height", 0) <= 800_000]
    era3 = [n for n in all_nonces if n.get("height", 0) > 800_000]

    analyze_era(era1, "Era 1: P2PKH (Bloques 1 - 500k)")
    analyze_era(era2, "Era 2: SegWit (Bloques 500k - 800k)")
    analyze_era(era3, "Era 3: Taproot (Bloques 800k+)")

if __name__ == "__main__":
    main()
