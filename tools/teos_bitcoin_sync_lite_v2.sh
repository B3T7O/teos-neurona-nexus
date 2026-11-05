#!/usr/bin/env bash
set -u

DATA="$HOME/.bitcoin"
UNIT="teos-bitcoin-sync-lite.service"
BIN="/usr/local/bin/bitcoind"
CLI="/usr/local/bin/bitcoin-cli"
ACTION="${1:-status}"

case "$ACTION" in
  status)
    echo "===== TEOS BITCOIN SYNC LITE 2.0 | ESTADO ====="

    if systemctl --user is-active --quiet "$UNIT"; then
      echo "Unidad TEOS: activa"
      systemctl --user --no-pager show "$UNIT" \
        -p ActiveState -p SubState -p CPUQuotaPerSecUSec \
        -p Nice -p IOSchedulingClass -p ControlGroup

      CG="$(systemctl --user show "$UNIT" -p ControlGroup --value 2>/dev/null || true)"
      if [ -n "$CG" ] && [ -r "/sys/fs/cgroup${CG}/cpu.max" ]; then
        echo "Cuota cgroup (quota period):"
        cat "/sys/fs/cgroup${CG}/cpu.max"
      fi
    elif pgrep -x bitcoind >/dev/null 2>&1; then
      echo "ATENCIÓN: bitcoind existe, pero no está activo en la unidad TEOS."
      pgrep -a bitcoind
      echo "No se intentará detenerlo automáticamente."
    else
      echo "Bitcoin Core detenido."
    fi

    echo
    echo "--- Prueba RPC con tiempo limitado ---"
    if pgrep -x bitcoind >/dev/null 2>&1; then
      timeout 6 "$CLI" -datadir="$DATA" -rpcclienttimeout=5 getblockchaininfo 2>&1 |
        python3 -c '
import json,sys
s=sys.stdin.read()
try:
 d=json.loads(s)
 for k in ("chain","blocks","headers","verificationprogress",
           "initialblockdownload","pruned","warnings"):
  print(f"{k}: {d.get(k, \"no disponible\")}")
except Exception:
 print(s.strip() or "RPC sin respuesta.")
' || true
    else
      echo "RPC omitido: Bitcoin Core está detenido."
    fi

    echo
    echo "--- Recursos y NEURONA ---"
    free -h
    uptime
    ps -p 10076,227 -o pid,stat,pcpu,pmem,comm
    ;;

  start)
    if pgrep -x bitcoind >/dev/null 2>&1; then
      echo "Cancelado: ya existe un proceso bitcoind."
      pgrep -a bitcoind
      exit 1
    fi

    if systemctl --user is-active --quiet "$UNIT"; then
      echo "Cancelado: la unidad ya está activa."
      exit 1
    fi

    if [ ! -x "$BIN" ] || [ ! -x "$CLI" ]; then
      echo "Cancelado: no se encuentran bitcoind y bitcoin-cli en /usr/local/bin."
      exit 1
    fi

    if [ ! -d "$DATA/blocks" ] || [ ! -d "$DATA/chainstate" ]; then
      echo "Cancelado: faltan directorios de datos esperados."
      exit 1
    fi

    echo "Se solicitará inicio con cuota de CPU del 75 %."
    echo "No se cambiarán la cartera ni los datos de la cadena."
    echo "Unidad: $UNIT"
    echo "dbcache=256 MiB; maxconnections=12; par=2"
    echo "Prioridad: Nice=5; I/O best-effort."
    echo "El proceso permanecerá en primer plano dentro de systemd."

    systemd-run --user --no-block \
      --unit="$UNIT" \
      --description="TEOS Bitcoin Sync Lite 2.0" \
      --property=CPUQuota=75% \
      --property=Nice=5 \
      --property=IOSchedulingClass=best-effort \
      --property=KillSignal=SIGINT \
      --property=TimeoutStopSec=300s \
      --property=Restart=no \
      "$BIN" -datadir="$DATA" -daemon=0 \
      -dbcache=256 -maxconnections=12 -par=2

    echo
    echo "Solicitud enviada. Verifica con:"
    echo "$HOME/teos-neurona-nexus/tools/teos_bitcoin_sync_lite_v2.sh status"
    echo "Registros de la unidad:"
    echo "journalctl --user -u $UNIT -n 60 --no-pager"
    ;;

  stop)
    if ! systemctl --user is-active --quiet "$UNIT"; then
      if pgrep -x bitcoind >/dev/null 2>&1; then
        echo "Bitcoin Core existe fuera de la unidad TEOS."
        echo "Por seguridad, no se enviará ninguna señal."
        pgrep -a bitcoind
        exit 1
      fi
      echo "La unidad TEOS ya está detenida."
      exit 0
    fi

    echo "Solicitando apagado ordenado de la unidad TEOS..."
    echo "Bitcoin Core puede tardar varios minutos en cerrar."
    systemctl --user stop "$UNIT"
    echo "Solicitud de apagado completada."
    ;;

  logs)
    journalctl --user -u "$UNIT" -n 80 --no-pager
    ;;

  *)
    echo "Uso: $0 {status|start|stop|logs}"
    exit 2
    ;;
esac
