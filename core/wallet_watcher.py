#!/usr/bin/env python3
import json
import urllib.request
from pathlib import Path
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parent.parent
WALLET = "bc1q20m7sy4ks42yt67m44t3dc6tun387v5z6lykxt"
API = "https://mempool.space/api"
STATE_FILE = ROOT / "data" / "processed" / "wallet_state.json"
ALERT_FILE = ROOT / "data" / "processed" / "wallet_alerts.jsonl"

def fetch_json(url):
    with urllib.request.urlopen(url, timeout=15) as r:
        return json.loads(r.read())

def get_wallet_balance():
    """Consulta el saldo y transacciones recientes de la dirección."""
    try:
        stats = fetch_json(f"{API}/address/{WALLET}")
        txs = fetch_json(f"{API}/address/{WALLET}/txs")
        
        confirmed = stats.get("chain_stats", {}).get("funded_txo_sum", 0) - stats.get("chain_stats", {}).get("spent_txo_sum", 0)
        pending = stats.get("mempool_stats", {}).get("funded_txo_sum", 0) - stats.get("mempool_stats", {}).get("spent_txo_sum", 0)
        
        return {
            "confirmed_sats": confirmed,
            "pending_sats": pending,
            "tx_count": len(txs),
            "latest_txid": txs[0].get("txid") if txs else None
        }
    except Exception as e:
        return {"error": str(e)}

def main():
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Monitoreando wallet...")
    
    current = get_wallet_balance()
    if "error" in current:
        print(f"❌ Error: {current['error']}")
        return
    
    # Cargar estado anterior
    previous = {}
    if STATE_FILE.exists():
        try:
            previous = json.loads(STATE_FILE.read_text())
        except: pass
    
    # Detectar cambios
    alert = None
    if previous:
        if current.get("confirmed_sats", 0) > previous.get("confirmed_sats", 0):
            diff = current["confirmed_sats"] - previous["confirmed_sats"]
            alert = f"🚨 ¡BTC RECIBIDO! +{diff:,} sats ({(diff/100_000_000):.8f} BTC)"
        elif current.get("tx_count", 0) > previous.get("tx_count", 0):
            alert = f"📨 Nueva transacción detectada. Total txs: {current['tx_count']}"
    
    # Guardar estado actual
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(current, indent=2))
    
    # Mostrar estado
    balance_btc = current["confirmed_sats"] / 100_000_000
    print(f"  💰 Saldo confirmado: {balance_btc:.8f} BTC ({current['confirmed_sats']:,} sats)")
    print(f"  ⏳ Saldo pendiente: {current['pending_sats']:,} sats")
    print(f"  📊 Total transacciones: {current['tx_count']}")
    
    # Registrar alerta si hubo cambio
    if alert:
        print(f"\n{alert}")
        ALERT_FILE.parent.mkdir(parents=True, exist_ok=True)
        with ALERT_FILE.open("a", encoding="utf-8") as f:
            f.write(json.dumps({
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "alert": alert,
                "state": current
            }) + "\n")

if __name__ == "__main__":
    main()
