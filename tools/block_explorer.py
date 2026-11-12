#!/usr/bin/env python3
"""
Explorador de Bloques de Bitcoin para TEOS.
Extrae Nonce, Merkle Root, num de transacciones y verifica una firma ECDSA.
Guarda el resultado en data/processed/block_explorer.json
"""
import json
import urllib.request
from pathlib import Path
from datetime import datetime, timezone
from bitcoin.core import CTransaction
from bitcoin.core.script import CScript
from bitcoin.core.scripteval import VerifyScript, SCRIPT_VERIFY_P2SH

ROOT = Path(__file__).resolve().parent.parent
OUTPUT = ROOT / "data" / "processed" / "block_explorer.json"
API = "https://mempool.space/api"

def fetch_json(url):
    with urllib.request.urlopen(url, timeout=30) as r:
        return json.loads(r.read())

def fetch_text(url):
    with urllib.request.urlopen(url, timeout=30) as r:
        return r.read().decode().strip()

def verify_one_ecdsa(txids):
    """Busca una transaccion legacy y verifica su firma ECDSA."""
    for txid in txids[1:50]:
        try:
            tx_data = fetch_json(f"{API}/tx/{txid}")
            if not tx_data.get("vin") or not tx_data.get("vout"):
                continue
            # Buscamos cualquier transaccion que gaste un P2PKH o P2WPKH
            if not tx_data["vin"][0].get("scriptsig") and not tx_data["vin"][0].get("witness"):
                continue
                
            prev_txid = tx_data["vin"][0]["txid"]
            prev_vout = tx_data["vin"][0]["vout"]
            prev_tx_data = fetch_json(f"{API}/tx/{prev_txid}")
            prev_spk = bytes.fromhex(prev_tx_data["vout"][prev_vout]["scriptpubkey"])
            
            tx_hex = fetch_text(f"{API}/tx/{txid}/hex")
            prev_tx_hex = fetch_text(f"{API}/tx/{prev_txid}/hex")
            
            tx = CTransaction.deserialize(bytes.fromhex(tx_hex))
            prev_tx = CTransaction.deserialize(bytes.fromhex(prev_tx_hex))
            
            script_pubkey = CScript(prev_spk)
            script_sig = tx.vin[0].scriptSig
            
            VerifyScript(script_sig, script_pubkey, tx, 0, (SCRIPT_VERIFY_P2SH,))
            return {"txid": txid, "valid": True}
        except Exception:
            continue
    return {"txid": None, "valid": False}

def main():
    print("=" * 60)
    print("  TEOS BLOCK EXPLORER - BITCOIN EN VIVO")
    print("=" * 60)

    print("\n[1] Descargando cabecera del ultimo bloque...")
    height = fetch_text(f"{API}/blocks/tip/height")
    block_hash = fetch_text(f"{API}/block-height/{height}")
    block = fetch_json(f"{API}/block/{block_hash}")
    
    print(f"    Altura: {height}")
    print(f"    Hash: {block_hash[:32]}...")
    
    print("\n[2] Extrayendo datos criptograficos del bloque...")
    nonce = block.get("nonce")
    merkle_root = block.get("merkle_root")
    tx_count = block.get("tx_count")
    
    print(f"    Nonce: {nonce}")
    print(f"    Merkle Root: {merkle_root}")
    print(f"    Transacciones: {tx_count}")

    print("\n[3] Buscando y verificando una firma ECDSA...")
    txids = fetch_json(f"{API}/block/{block_hash}/txids")
    ecdsa_result = verify_one_ecdsa(txids)
    
    if ecdsa_result["valid"]:
        print(f"    ✅ Firma ECDSA VALIDA en tx: {ecdsa_result['txid'][:16]}...")
    else:
        print("    ❌ No se pudo verificar una firma en este bloque")

    # Guardar resultado
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    result = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "height": int(height),
        "block_hash": block_hash,
        "nonce": nonce,
        "merkle_root": merkle_root,
        "tx_count": tx_count,
        "ecdsa_verified": ecdsa_result["valid"],
        "ecdsa_txid": ecdsa_result["txid"]
    }
    
    with OUTPUT.open("w", encoding="utf-8") as f:
        json.dump(result, f, indent=2)
        
    print(f"\n✅ Datos guardados en {OUTPUT}")

if __name__ == "__main__":
    main()
