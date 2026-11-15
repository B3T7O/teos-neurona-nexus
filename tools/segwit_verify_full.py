#!/usr/bin/env python3
"""
Verificación criptográfica completa de SegWit (P2WPKH).
Usa btclib para verificar firmas ECDSA en transacciones SegWit nativas.
"""
import json
import urllib.request
from pathlib import Path
from datetime import datetime, timezone

from btclib.tx import Tx
from btclib.script.engine import verify_transaction, ALL_FLAGS
from btclib.exceptions import BTClibValueError

API = "https://mempool.space/api"
ROOT = Path(__file__).resolve().parent.parent
AUDIT_DIR = ROOT / "data" / "audit"

def fetch_json(url):
    with urllib.request.urlopen(url, timeout=30) as r:
        return json.loads(r.read())

def fetch_text(url):
    with urllib.request.urlopen(url, timeout=30) as r:
        return r.read().decode().strip()

def is_p2wpkh(script_hex):
    """P2WPKH: OP_0 (0x00) PUSH20 (0x14) <20 bytes> = 22 bytes total"""
    if not script_hex: return False
    s = bytes.fromhex(script_hex)
    return len(s) == 22 and s[0] == 0x00 and s[1] == 0x14

def find_segwit_txids(block_hash):
    """Busca txids con outputs P2WPKH en el bloque."""
    txids = fetch_json(f"{API}/block/{block_hash}/txids")
    segwit_txids = []
    
    for txid in txids[1:100]:  # Muestreo de las primeras 100
        try:
            tx_data = fetch_json(f"{API}/tx/{txid}")
            for vout in tx_data.get("vout", []):
                if is_p2wpkh(vout.get("scriptpubkey")):
                    segwit_txids.append(txid)
                    break
            if len(segwit_txids) >= 5:
                break
        except Exception:
            continue
    
    return segwit_txids

def build_prevouts(tx_json):
    """Construye la lista de TxOut (UTXOs gastados)."""
    prevouts = []
    for vin_json in tx_json["vin"]:
        prev_txid = vin_json["txid"]
        prev_vout = vin_json["vout"]
        prev_tx_hex = fetch_text(f"{API}/tx/{prev_txid}/hex")
        prev_tx = Tx.parse(bytes.fromhex(prev_tx_hex))
        prevouts.append(prev_tx.vout[prev_vout])
    return prevouts

def verify_segwit_tx(txid):
    """Verifica una transacción SegWit (P2WPKH) y devuelve True/False/None."""
    try:
        tx_hex = fetch_text(f"{API}/tx/{txid}/hex")
        tx_json = fetch_json(f"{API}/tx/{txid}")
        tx = Tx.parse(bytes.fromhex(tx_hex))
        prevouts = build_prevouts(tx_json)
        
        # btclib verifica SegWit nativamente con los mismos flags
        verify_transaction(prevouts, tx, ALL_FLAGS)
        return True
    except BTClibValueError as e:
        print(f"        🔍 DEBUG BTClibValueError: {str(e)[:200]}")
        return False
    except Exception as e:
        print(f"        🔍 DEBUG ERROR: {type(e).__name__}: {str(e)[:200]}")
        return None

def main():
    print("="*60)
    print("  TEOS SEGWIT VERIFICATION (P2WPKH - Full Cryptographic)")
    print("="*60)
    
    height = fetch_text(f"{API}/blocks/tip/height")
    block_hash = fetch_text(f"{API}/block-height/{height}")
    
    print(f"[1] Bloque BTC #{height}")
    print(f"[2] Buscando transacciones P2WPKH (SegWit)...")
    
    txids = find_segwit_txids(block_hash)
    
    if not txids:
        print("    ⚠️ No se encontraron transacciones P2WPKH en las primeras 100 txs.")
        print("       Esto es inusual en bloques modernos. Reintentando en el próximo ciclo.")
        return
    
    print(f"    ✅ Encontradas {len(txids)} transacciones P2WPKH para verificar.")
    print()
    
    results = {"valid": 0, "invalid": 0, "errors": 0, "details": []}
    
    for i, txid in enumerate(txids, 1):
        print(f"    [{i}/{len(txids)}] {txid[:16]}...")
        status = verify_segwit_tx(txid)
        
        if status is True:
            print(f"        ✅ VALIDA (firma ECDSA SegWit verificada)")
            results["valid"] += 1
            results["details"].append({"txid": txid, "status": "valid"})
        elif status is False:
            print(f"        ❌ INVÁLIDA")
            results["invalid"] += 1
            results["details"].append({"txid": txid, "status": "invalid"})
        else:
            print(f"        ⚠️ ERROR")
            results["errors"] += 1
            results["details"].append({"txid": txid, "status": "error"})
    
    AUDIT_DIR.mkdir(parents=True, exist_ok=True)
    output = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "block_height": height,
        "total_verified": len(txids),
        "valid": results["valid"],
        "invalid": results["invalid"],
        "errors": results["errors"],
        "details": results["details"],
        "note": "Verificación criptográfica completa SegWit (P2WPKH) con btclib"
    }
    
    output_path = AUDIT_DIR / "segwit_verify_full.json"
    with output_path.open("w", encoding="utf-8") as f:
        json.dump(output, f, indent=2)
    
    print()
    print("="*60)
    print(f"  RESULTADOS FINALES")
    print("="*60)
    print(f"    Total verificadas: {len(txids)}")
    print(f"    ✅ Válidas:        {results['valid']}")
    print(f"    ❌ Inválidas:      {results['invalid']}")
    print(f"    ⚠️ Errores:        {results['errors']}")
    print(f"\n    ✅ Reporte guardado en {output_path}")

if __name__ == "__main__":
    main()
