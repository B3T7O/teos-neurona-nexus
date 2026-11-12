#!/usr/bin/env python3
"""
Auditoria criptografica de TEOS:
1. Merkle Root de los outcomes locales.
2. Verificacion ECDSA del ultimo bloque de Bitcoin.
Genera data/audit/crypto_audit.json
"""
import hashlib
import json
import urllib.request
from pathlib import Path
from datetime import datetime, timezone
from bitcoin.core import CTransaction
from bitcoin.core.script import CScript
from bitcoin.core.scripteval import VerifyScript, SCRIPT_VERIFY_P2SH

ROOT = Path(__file__).resolve().parent.parent
OUTCOMES = ROOT / "data" / "processed" / "learning_outcomes_v2.jsonl"
AUDIT_DIR = ROOT / "data" / "audit"
API = "https://mempool.space/api"

def sha256d(data: bytes) -> bytes:
    return hashlib.sha256(hashlib.sha256(data).digest()).digest()

def fetch_json(url):
    with urllib.request.urlopen(url, timeout=30) as r:
        return json.loads(r.read())

def fetch_text(url):
    with urllib.request.urlopen(url, timeout=30) as r:
        return r.read().decode().strip()

def local_merkle_root():
    """Calcula el Merkle Root de los prediction_id locales (integridad de datos)."""
    print("[1] Calculando Merkle Root local de outcomes...")
    txids = []
    with OUTCOMES.open("r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            try:
                obj = json.loads(line.strip())
                pid = obj.get("prediction_id")
                if pid:
                    txids.append(sha256d(pid.encode()).hex())
            except Exception:
                continue
    if not txids:
        return None, 0
    # Arbol de Merkle
    level = [bytes.fromhex(t)[::-1] for t in txids]
    while len(level) > 1:
        if len(level) % 2 == 1:
            level.append(level[-1])
        level = [sha256d(level[i] + level[i+1]) for i in range(0, len(level), 2)]
    return level[0][::-1].hex(), len(txids)

def verify_bitcoin_block():
    """Verifica la firma ECDSA del ultimo bloque de Bitcoin."""
    print("[2] Verificando el ultimo bloque de Bitcoin...")
    height = fetch_text(f"{API}/blocks/tip/height")
    block_hash = fetch_text(f"{API}/block-height/{height}")
    txids = fetch_json(f"{API}/block/{block_hash}/txids")
    # Buscar una transaccion legacy simple
    for txid in txids[1:20]:
        try:
            tx_data = fetch_json(f"{API}/tx/{txid}")
            if not tx_data.get("vin") or len(tx_data["vin"]) != 1 or len(tx_data["vout"]) != 1:
                continue
            if not tx_data["vin"][0].get("scriptsig"):
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
            return {
                "height": int(height),
                "block_hash": block_hash,
                "txid": txid,
                "signature_valid": True
            }
        except Exception as e:
            continue
    return {"height": int(height), "block_hash": block_hash, "signature_valid": False}

def main():
    print("=" * 60)
    print("  TEOS CRYPTO AUDIT")
    print("=" * 60)
    merkle, n_tx = local_merkle_root()
    print(f"    Merkle Root local: {merkle[:32]}...")
    print(f"    Transacciones locales: {n_tx}")
    btc = verify_bitcoin_block()
    print(f"    Bloque BTC #{btc['height']}: {btc['block_hash'][:16]}...")
    print(f"    Firma ECDSA: {'✅ VALIDA' if btc['signature_valid'] else '❌ INVALIDA'}")
    AUDIT_DIR.mkdir(parents=True, exist_ok=True)
    result = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "local_merkle_root": merkle,
        "local_outcomes_count": n_tx,
        "bitcoin_block_height": btc["height"],
        "bitcoin_block_hash": btc["block_hash"],
        "bitcoin_signature_valid": btc["signature_valid"]
    }
    with (AUDIT_DIR / "crypto_audit.json").open("w") as f:
        json.dump(result, f, indent=2)
    print("\n✅ Reporte guardado en data/audit/crypto_audit.json")

if __name__ == "__main__":
    main()
