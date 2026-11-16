#!/usr/bin/env python3
import json
import urllib.request
import random
import time
from pathlib import Path
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parent.parent
NONCES_FILE = ROOT / "data" / "processed" / "nonces_10k.json"
OUTPUT_FILE = ROOT / "data" / "audit" / "genome_analysis.json"
API = "https://mempool.space/api"

def fetch_json(url):
    try:
        with urllib.request.urlopen(url, timeout=15) as r:
            return json.loads(r.read())
    except Exception as e:
        print(f"    ⚠️ Error API: {e}")
        return None


def fetch_text(url):
    try:
        with urllib.request.urlopen(url, timeout=15) as r:
            return r.read().decode().strip()
    except Exception as e:
        print(f"    ⚠️ Error API: {e}")
        return None

def classify_tx(script_pubkey_hex):
    if not script_pubkey_hex: return "Unknown"
    spk = bytes.fromhex(script_pubkey_hex)
    
    # P2PKH: OP_DUP OP_HASH160 <20 bytes> OP_EQUALVERIFY OP_CHECKSIG
    if spk.startswith(b'\x76\xa9\x14') and spk.endswith(b'\x88\xac'):
        return "P2PKH"
    # P2WPKH: OP_0 <20 bytes>
    if len(spk) == 22 and spk[0] == 0x00 and spk[1] == 0x14:
        return "P2WPKH (SegWit)"
    # P2TR: OP_1 <32 bytes>
    if len(spk) == 34 and spk[0] == 0x51 and spk[1] == 0x20:
        return "P2TR (Taproot)"
    
    return "Other"

def analyze_block(height):
    print(f"    Consultando bloque #{height}...")
    block_hash = fetch_text(f"{API}/block-height/{height}")
    if not block_hash: return None
    
    # ¡ESTA ES LA MAGIA! Pedimos las transacciones en una sola petición.
    txs = fetch_json(f"{API}/block/{block_hash}/txs")
    if not txs: return None
    
    counts = {"P2PKH": 0, "P2WPKH (SegWit)": 0, "P2TR (Taproot)": 0, "Other": 0, "Unknown": 0}
    
    # Analizamos las primeras 20 transacciones del bloque
    for tx_data in txs[1:21]:
        for vout in tx_data.get("vout", []):
            tx_type = classify_tx(vout.get("scriptpubkey"))
            counts[tx_type] += 1
            
    return {"height": height, "counts": counts}

def main():
    print("🧬 ANÁLISIS DEL GENOMA DE BITCOIN\n")
    
    with NONCES_FILE.open("r", encoding="utf-8") as f:
        all_nonces = json.load(f)
    
    valid_nonces = [n for n in all_nonces if n.get("height", 0) > 0]
    sample = random.sample(valid_nonces, min(5, len(valid_nonces))) # 5 bloques
    
    print(f"🎲 Muestra: {len(sample)} bloques aleatorios\n")
    
    results = []
    for i, nonce in enumerate(sample, 1):
        h = nonce["height"]
        print(f"  [{i}/{len(sample)}] Analizando bloque #{h}...")
        res = analyze_block(h)
        if res:
            results.append(res)
        time.sleep(2) # Pausa entre bloques para no saturar la API
    
    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_FILE.write_text(json.dumps(results, indent=2), encoding="utf-8")
    
    # Resumen global
    total = {"P2PKH": 0, "P2WPKH (SegWit)": 0, "P2TR (Taproot)": 0, "Other": 0, "Unknown": 0}
    for r in results:
        for k, v in r["counts"].items():
            total[k] += v
    
    print(f"\n{'='*50}")
    print("  📊 DISTRIBUCIÓN DE TIPOS DE TRANSACCIÓN")
    print(f"{'='*50}")
    for k, v in total.items():
        if v > 0:
            print(f"  {k:20s}: {v:5d} transacciones")
    print(f"\n  Reporte guardado en: {OUTPUT_FILE}")

if __name__ == "__main__":
    main()
