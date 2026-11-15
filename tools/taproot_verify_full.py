#!/usr/bin/env python3
"""
Verificación criptográfica completa de Taproot (BIP341).
Usa btclib para verificar firmas Schnorr en transacciones P2TR.
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

def build_prevouts(tx_json):
    """Construye la lista de TxOut (UTXOs gastados) para la verificación."""
    prevouts = []
    for vin_json in tx_json["vin"]:
        prev_txid = vin_json["txid"]
        prev_vout = vin_json["vout"]
        prev_tx_hex = fetch_text(f"{API}/tx/{prev_txid}/hex")
        prev_tx = Tx.parse(bytes.fromhex(prev_tx_hex))
        prevouts.append(prev_tx.vout[prev_vout])
    return prevouts

def verify_taproot_tx(txid):
    """Verifica una transacción Taproot y devuelve True/False/None."""
    try:
        tx_hex = fetch_text(f"{API}/tx/{txid}/hex")
        tx_json = fetch_json(f"{API}/tx/{txid}")
        tx = Tx.parse(bytes.fromhex(tx_hex))
        prevouts = build_prevouts(tx_json)
        
        # CORRECCIÓN CRÍTICA: el orden es (prevouts, tx, flags)
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
    print("  TEOS TAPROOT VERIFICATION (BIP341 - Full Cryptographic)")
    print("="*60)
    
    structural_report = AUDIT_DIR / "taproot_audit.json"
    if not structural_report.exists():
        print("❌ No existe taproot_audit.json. Ejecuta primero crypto_audit_taproot.py")
        return
    
    with structural_report.open("r", encoding="utf-8") as f:
        report = json.load(f)
    
    txids = report.get("sample_txids", [])
    if not txids:
        print("❌ No hay txids de Taproot en el reporte estructural.")
        return
    
    print(f"[1] Verificando {len(txids)} transacciones Taproot...")
    print(f"    Bloque de referencia: #{report.get('block_height')}")
    print()
    
    results = {"valid": 0, "invalid": 0, "errors": 0, "details": []}
    
    for i, txid in enumerate(txids, 1):
        print(f"    [{i}/{len(txids)}] {txid[:16]}...")
        status = verify_taproot_tx(txid)
        
        if status is True:
            print(f"        ✅ VALIDA (firma Schnorr verificada)")
            results["valid"] += 1
            results["details"].append({"txid": txid, "status": "valid"})
        elif status is False:
            print(f"        ❌ INVÁLIDA (firma no coincide o formato incorrecto)")
            results["invalid"] += 1
            results["details"].append({"txid": txid, "status": "invalid"})
        else:
            print(f"        ⚠️ ERROR (no se pudo verificar)")
            results["errors"] += 1
            results["details"].append({"txid": txid, "status": "error"})
    
    AUDIT_DIR.mkdir(parents=True, exist_ok=True)
    output = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "block_height": report.get("block_height"),
        "total_verified": len(txids),
        "valid": results["valid"],
        "invalid": results["invalid"],
        "errors": results["errors"],
        "details": results["details"],
        "note": "Verificación criptográfica completa BIP341 con btclib"
    }
    
    output_path = AUDIT_DIR / "taproot_verify_full.json"
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
