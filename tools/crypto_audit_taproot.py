#!/usr/bin/env python3
"""
TEOS Taproot Audit (Structural)
Busca transacciones Taproot (P2TR) en el bloque actual y verifica su estructura.
La verificación criptográfica completa (BIP341) se implementará después.
"""
import json
import urllib.request
from pathlib import Path
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parent.parent
AUDIT_DIR = ROOT / "data" / "audit"
API = "https://mempool.space/api"

def fetch_json(url):
    with urllib.request.urlopen(url, timeout=30) as r:
        return json.loads(r.read())

def fetch_text(url):
    with urllib.request.urlopen(url, timeout=30) as r:
        return r.read().decode().strip()

def is_p2tr(script_hex):
    """P2TR: OP_1 (0x51) PUSH32 (0x20) <32 bytes> = 34 bytes total"""
    if not script_hex: return False
    s = bytes.fromhex(script_hex)
    return len(s) == 34 and s[0] == 0x51 and s[1] == 0x20

def main():
    print("="*60)
    print("  TEOS TAPROOT AUDIT (Structural)")
    print("="*60)

    height = fetch_text(f"{API}/blocks/tip/height")
    block_hash = fetch_text(f"{API}/block-height/{height}")
    txids = fetch_json(f"{API}/block/{block_hash}/txids")

    print(f"[1] Bloque BTC #{height} | {len(txids)} transacciones")

    taproot_found = 0
    p2tr_txids = []

    for txid in txids[1:100]:  # Buscar en las primeras 100 (suficiente para muestreo)
        try:
            tx_data = fetch_json(f"{API}/tx/{txid}")
            for vout in tx_data.get("vout", []):
                if is_p2tr(vout.get("scriptpubkey")):
                    taproot_found += 1
                    p2tr_txids.append(txid)
                    break
        except Exception:
            continue

    print(f"[2] Transacciones Taproot (P2TR) encontradas: {taproot_found}")
    
    if taproot_found > 0:
        print(f"    ✅ Muestra de txids Taproot:")
        for txid in p2tr_txids[:5]:
            print(f"       - {txid}")
        print(f"    ℹ️ Verificación estructural: OK (todos tienen el formato OP_1 <32 bytes>)")
        print(f"    ⏳ Verificación criptográfica completa (BIP341) pendiente para la próxima sesión.")
        status = "structural_ok"
    else:
        print("    ⚠️ No se encontraron transacciones Taproot en las primeras 100 txs.")
        status = "not_found"

    # Guardar reporte
    AUDIT_DIR.mkdir(parents=True, exist_ok=True)
    report = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "block_height": height,
        "taproot_transactions_found": taproot_found,
        "sample_txids": p2tr_txids[:5],
        "status": status,
        "note": "Verificación estructural (formato P2TR). Verificación BIP341 pendiente."
    }
    with (AUDIT_DIR / "taproot_audit.json").open("w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)

    print(f"\n    ✅ Reporte guardado en {AUDIT_DIR / 'taproot_audit.json'}")

if __name__ == "__main__":
    main()
