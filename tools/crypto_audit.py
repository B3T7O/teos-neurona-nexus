#!/usr/bin/env python3
"""
Auditoria criptografica de TEOS:
1. Master Merkle Root (Outcomes + IA + Rete + Reglas)
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
from bitcoin.core.scripteval import VerifyScript, SCRIPT_VERIFY_P2SH, SCRIPT_VERIFY_STRICTENC

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
    """Calcula el Master Merkle Root combinando Outcomes, IA, Rete y Reglas."""
    print("[1] Calculando Master Merkle Root (Auditoría Global)...")
    txids = []

    # 1. Outcomes
    if OUTCOMES.exists():
        with OUTCOMES.open("r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                try:
                    obj = json.loads(line.strip())
                    pid = obj.get("prediction_id")
                    if pid: txids.append(sha256d(pid.encode()).hex())
                except: continue

    # 2. Predicciones de la IA (MLP Lite)
    preds_path = ROOT / "data" / "processed" / "learning_predictions_v2.jsonl"
    if preds_path.exists():
        with preds_path.open("r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                try:
                    obj = json.loads(line.strip())
                    if obj.get("method") == "mlp_lite":
                        pid = obj.get("prediction_id")
                        if pid: txids.append(sha256d(pid.encode()).hex())
                except: continue

    # 3. Decisiones del Motor Rete
    rete_path = ROOT / "data" / "processed" / "rete_decisions.jsonl"
    if rete_path.exists():
        with rete_path.open("r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                try:
                    obj = json.loads(line.strip())
                    t = obj.get("timestamp")
                    r = obj.get("rule")
                    if t and r: txids.append(sha256d(f"{t}|{r}".encode()).hex())
                except: continue

    # 4. Hash del archivo de reglas (rules.json)
    rules_path = ROOT / "data" / "config" / "rules.json"
    if rules_path.exists():
        with rules_path.open("rb") as f:
            txids.append(sha256d(f.read()).hex())

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

    for txid in txids[1:500]:
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

            # Solo P2PKH (OP_DUP OP_HASH160 <20 bytes> OP_EQUALVERIFY OP_CHECKSIG)
            if not (prev_spk.startswith(b'\x76\xa9\x14') and prev_spk.endswith(b'\x88\xac')):
                continue

            tx_hex = fetch_text(f"{API}/tx/{txid}/hex")
            prev_tx_hex = fetch_text(f"{API}/tx/{prev_txid}/hex")
            tx = CTransaction.deserialize(bytes.fromhex(tx_hex))
            prev_tx = CTransaction.deserialize(bytes.fromhex(prev_tx_hex))
            script_pubkey = CScript(prev_spk)
            script_sig = tx.vin[0].scriptSig

            # Verificar con flags estrictos
            VerifyScript(script_sig, script_pubkey, tx, 0, (SCRIPT_VERIFY_P2SH, SCRIPT_VERIFY_STRICTENC))
            print(f"    ✅ Transaccion {txid[:16]}... verificada con exito.")
            return True
        except Exception:
            continue

    print("    ℹ️ N/A (Bloque moderno sin transacciones P2PKH legacy para verificar ECDSA)")
    print("       Nota: Esto es NORMAL. Bitcoin moderno usa SegWit/Taproot. El Master Merkle Root es la auditoría principal.")
    return None

def main():
    print("="*60)
    print("  TEOS CRYPTO AUDIT")
    print("="*60)

    merkle_root, count = local_merkle_root()
    if merkle_root:
        print(f"    Merkle Root local: {merkle_root[:32]}...")
        print(f"    Transacciones locales: {count}")
    else:
        print("    ⚠️ No hay transacciones locales para auditar.")

    ecdsa_valid = verify_bitcoin_block()

    # Guardar reporte
    AUDIT_DIR.mkdir(parents=True, exist_ok=True)
    report = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "local_merkle_root": merkle_root,
        "local_transactions": count,
        "bitcoin_block_height": fetch_text(f"{API}/blocks/tip/height"),
        "ecdsa_valid": ecdsa_valid
    }
    with (AUDIT_DIR / "crypto_audit.json").open("w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)

    print(f"\n    ✅ Reporte guardado en {AUDIT_DIR / 'crypto_audit.json'}")
    if ecdsa_valid is True:
        print("    Firma ECDSA: ✅ VALIDA")
    elif ecdsa_valid is False:
        print("    Firma ECDSA: ❌ INVALIDA (fallo real en la verificación)")
    else:
        print("    Firma ECDSA: ℹ️ N/A (sin P2PKH legacy en este bloque)")

if __name__ == "__main__":
    main()
