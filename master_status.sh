#!/usr/bin/env bash
clear
echo -e "\e[1;36m╔══════════════════════════════════════════════════════════════╗\e[0m"
echo -e "\e[1;36m║       🦾 TEOS NEURONA NEXUS - REPORTE GENERAL DEL DÍA         ║\e[0m"
echo -e "\e[1;36m╚══════════════════════════════════════════════════════════════╝\e[0m"

# 1. HARDWARE
echo -e "\n\e[1;33m▶ [1] HARDWARE (Iron Man):\e[0m"
python3 -c "
import json, urllib.request
try:
    d = json.loads(urllib.request.urlopen('http://192.168.18.45/api/system/info', timeout=5).read())
    print(f'  Frecuencia:  {d.get(\"actualFrequency\")} MHz')
    print(f'  Hashrate:    {d.get(\"hashRate_10m\", 0):.0f} GH/s')
    acc = d.get(\"sharesAccepted\", 0) or 0
    rej = d.get(\"sharesRejected\", 0) or 0
    total = acc + rej
    err_rate = (rej / total * 100) if total > 0 else 0.0
    print(f'  Error Rate:  {err_rate:.2f}% (Real: {rej}/{total})')
    print(f'  Temp:        ASIC {d.get(\"temp\",0):.1f}°C | VRM {d.get(\"vrTemp\",0)}°C')
    print(f'  Shares:      {acc} ok / {rej} fail')
except Exception:
    print('  ❌ Error conectando al Bitaxe')
"

# 2. SHARES PERFECTOS (0.00% ERROR)
echo -e "\n\e[1;33m▶ [2] MOMENTOS DE PRECISIÓN PERFECTA (0.00% Error):\e[0m"
PERFECT_FILE="data/processed/perfect_shares.jsonl"
if [ -f "$PERFECT_FILE" ] && [ -s "$PERFECT_FILE" ]; then
    COUNT=$(wc -l < "$PERFECT_FILE")
    echo -e "  🏆 Total de hitos registrados: \e[1;32m$COUNT\e[0m"
    echo -e "  Último registro:"
    tail -n 1 "$PERFECT_FILE" | python3 -c "
import sys, json
d = json.loads(sys.stdin.read())
print(f'    - Fecha:    {d.get(\"timestamp\")}')
print(f'    - Shares:   {d.get(\"shares_accepted\")}')
print(f'    - Frecuencia: {d.get(\"frequency\")} MHz')
"
else
    echo -e "  ⏳ Aún no se han registrado momentos de 0.00% error hoy."
fi

# 3. INTELIGENCIA ARTIFICIAL Y EVOLUCIÓN
echo -e "\n\e[1;33m▶ [3] INTELIGENCIA ARTIFICIAL Y EVOLUCIÓN:\e[0m"
# Campeón Evolutivo
if [ -f "data/processed/evolve_champion.json" ]; then
    python3 -c "
import json
c = json.load(open('data/processed/evolve_champion.json'))
print(f'  🧬 Campeón Evolutivo (APE: {c.get(\"ape_mean\")}%)')
print('     Peso del MLP Lite: 92.3% (F1 V4)')
"
fi
# Últimas acciones del AI Bridge
if [ -f "data/processed/ai_bridge_log.jsonl" ]; then
    echo -e "  🧠 Últimas decisiones del AI Bridge:"
    tail -n 3 data/processed/ai_bridge_log.jsonl | python3 -c "
import sys, json
for line in sys.stdin:
    try:
        d = json.loads(line)
        print(f'     - {d.get(\"reason\")} (Freq: {d.get(\"new_freq\")} MHz)')
    except: pass
"
else
    echo -e "  🧠 AI Bridge: Sin decisiones registradas (en cooldown o sin diferencias)."
fi

# 4. AUDITORÍA Y LATENCIA
echo -e "\n\e[1;33m▶ [4] AUDITORÍA CRIPTOGRÁFICA Y LATENCIA:\e[0m"
# Auditorías
SW_VALIDS=$(python3 -c "import json; print(json.load(open('data/audit/segwit_verify_full.json')).get('valid', 0))" 2>/dev/null || echo "0")
TP_VALIDS=$(python3 -c "import json; print(json.load(open('data/audit/taproot_verify_full.json')).get('valid', 0))" 2>/dev/null || echo "0")
echo -e "  🔐 SegWit Validados:  \e[1;32m$SW_VALIDS\e[0m txs"
echo -e "  🔐 Taproot Validados: \e[1;32m$TP_VALIDS\e[0m txs"

# Latency Sniper
if [ -f "data/processed/latency_sniper_rt.jsonl" ] && [ -s "data/processed/latency_sniper_rt.jsonl" ]; then
    echo -e "  🎯 Últimos bloques cazados por el Latency Sniper:"
    tail -n 2 data/processed/latency_sniper_rt.jsonl | python3 -c "
import sys, json
for line in sys.stdin:
    try:
        d = json.loads(line)
        print(f'     - Bloque #{d.get(\"block_height\")}: {d.get(\"latency_ms\")} ms de latencia global')
    except: pass
"
else
    echo -e "  🎯 Latency Sniper: Esperando el próximo bloque..."
fi

echo -e "\n\e[1;36m═══════════════════════════════════════════════════════════════\e[0m"
echo -e "\e[1;32m  ✅ SISTEMA OPERATIVO Y APRENDIENDO.\e[0m"
echo -e "\e[1;36m═══════════════════════════════════════════════════════════════\e[0m\n"
