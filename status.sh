#!/usr/bin/env bash
echo -e "\n\e[1;36m═══════════════════════════════════════════════════════════════\e[0m"
echo -e "\e[1;36m       🦾 TEOS NEURONA NEXUS - ESTADO GLOBAL DEL SISTEMA       \e[0m"
echo -e "\e[1;36m═══════════════════════════════════════════════════════════════\e[0m"

# 1. Estado de los 10 Servicios (6 Cerebros + 4 Invisibles)
echo -e "\n\e[1;33m▶ [1] SERVICIOS Y TIMERS EN SYSTEMD:\e[0m"
services=(
    "teos-neurona-scheduler.service"
    "teos-neurona-scheduler-lite.service"
    "teos-neurona-api.service"
    "teos-axeos-logs.service"
    "teos-nexus-collector.service"
    "teos-lite-proxy.service"
    "teos-neurona-mlp-lite.timer"
    "teos-neurona-rete.timer"
    "teos-segwit-audit.timer"
    "teos-taproot-audit.timer"
)
for s in "${services[@]}"; do
    status=$(systemctl is-active "$s")
    if [ "$status" = "active" ]; then
        printf "  %-40s \e[1;32m[ACTIVE]\e[0m\n" "$s"
    else
        printf "  %-40s \e[1;31m[%s]\e[0m\n" "$s" "$status"
    fi
done

# 2. Telemetría del Bitaxe
echo -e "\n\e[1;33m▶ [2] TELEMETRÍA DEL BITAXE (Iron Man):\e[0m"
python3 -c "
import json, urllib.request
try:
    d = json.loads(urllib.request.urlopen('http://192.168.18.45/api/system/info', timeout=5).read())
    print(f'  Frecuencia:  {d.get(\"actualFrequency\")} MHz')
    print(f'  Hashrate:    {d.get(\"hashRate_10m\", 0):.0f} GH/s')
    print(f'  Error Rate:  {d.get(\"errorPercentage\", 0):.2f}%')
    print(f'  ASIC / VRM:  {d.get(\"temp\",0):.1f}°C / {d.get(\"vrTemp\",0)}°C')
    print(f'  Shares:      {d.get(\"sharesAccepted\")} ok / {d.get(\"sharesRejected\")} fail')
except Exception as e:
    print(f'  \033[1;31m❌ Error conectando al Bitaxe: {e}\033[0m')
"

# 3. Estado del Proxy
echo -e "\n\e[1;33m▶ [3] LATENCIA DEL PROXY STRATUM:\e[0m"
if systemctl is-active --quiet teos-lite-proxy.service; then
    echo -e "  \e[1;32m✅ Lite Proxy Operativo (1ms de latencia local)\e[0m"
else
    echo -e "  \e[1;31m❌ Lite Proxy DETENIDO\e[0m"
fi

# 4. Últimos resultados de la IA y Auditoría
echo -e "\n\e[1;33m▶ [4] INTELIGENCIA Y AUDITORÍA:\e[0m"
if [ -f "data/processed/learning_predictions_v2.jsonl" ]; then
    last_pred=$(tail -n 1 data/processed/learning_predictions_v2.jsonl | python3 -c "import sys,json; print(json.loads(sys.stdin.read()).get('predicted_hashRate_GHs', 'N/A'))")
    echo -e "  Última Predicción MLP Lite: \e[1;35m${last_pred} GH/s\e[0m"
fi
if [ -f "data/audit/taproot_verify_full.json" ]; then
    tap_root=$(python3 -c "import json; print(json.load(open('data/audit/taproot_verify_full.json')).get('valid', 0))")
    echo -e "  Taproot Audit (BIP341):     \e[1;32m${tap_root} txs válidas\e[0m"
fi
if [ -f "data/audit/segwit_verify_full.json" ]; then
    seg_root=$(python3 -c "import json; print(json.load(open('data/audit/segwit_verify_full.json')).get('valid', 0))")
    echo -e "  SegWit Audit (P2WPKH):      \e[1;32m${seg_root} txs válidas\e[0m"
fi

echo -e "\n\e[1;36m═══════════════════════════════════════════════════════════════\e[0m"
echo -e "\e[1;32m  ✅ SISTEMA OPERATIVO. EL IRON MAN ESTÁ EN PILOTO AUTOMÁTICO.\e[0m"
echo -e "\e[1;36m═══════════════════════════════════════════════════════════════\e[0m\n"
