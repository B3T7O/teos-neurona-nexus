#!/usr/bin/env bash
set -u

DATA="$HOME/.bitcoin"
LOGDIR="$HOME/teos-neurona-nexus/logs"
LOG="$LOGDIR/bitcoin_sync_lite_start.log"
ACTION="${1:-status}"

mkdir -p "$LOGDIR"

case "$ACTION" in
    status)
        echo "===== TEOS BITCOIN SYNC LITE: ESTADO ====="
        if pgrep -x bitcoind >/dev/null 2>&1; then
            ps -C bitcoind -o pid,stat,etime,pcpu,pmem,args
            echo
            timeout 5 bitcoin-cli -datadir="$DATA" getblockchaininfo 2>/dev/null |
                python3 -c '
import json,sys
try:
 d=json.load(sys.stdin)
 for k in ("chain","blocks","headers","verificationprogress",
           "initialblockdownload","warnings"):
  print(f"{k}: {d.get(k, \"no disponible\")}")
except Exception:
 print("RPC no disponible todavía.")
' || true
            echo
            timeout 5 bitcoin-cli -datadir="$DATA" getnetworkinfo 2>/dev/null |
                python3 -c '
import json,sys
try:
 d=json.load(sys.stdin)
 print("Conexiones:",d.get("connections","no disponible"))
 print("Red activa:",d.get("networkactive","no disponible"))
except Exception:
 print("Estado de red RPC no disponible.")
' || true
        else
            echo "Bitcoin Core está detenido."
        fi
        echo
        free -h
        uptime
        ;;

    start)
        echo "Delegando inicio al controlador único V2..."
        exec "$HOME/teos-neurona-nexus/tools/teos_bitcoin_sync_lite_v2.sh" start
    stop)
        if ! pgrep -x bitcoind >/dev/null 2>&1; then
            echo "Bitcoin Core ya está detenido."
            exit 0
        fi
        echo "Solicitando apagado normal mediante RPC..."
        timeout 20 bitcoin-cli -datadir="$DATA" stop
        echo "Comprueba después con: $0 status"
        echo "No se fuerza el cierre del proceso."
        ;;

    *)
        echo "Uso: $0 {status|start|stop}"
        exit 2
        ;;
esac
