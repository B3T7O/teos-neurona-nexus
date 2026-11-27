#!/usr/bin/env python3
"""Genera el TEOS HUB con Neurona Map y Diagnóstico en vivo."""
import json
import os
import time
import urllib.request
from pathlib import Path
from datetime import datetime

ROOT = Path(__file__).resolve().parent.parent
OUTPUT = ROOT / "web" / "teos_hub.html"
ASIC_IP = os.getenv("ASIC_IP", "192.168.18.45")

def fetch(url):
    try:
        with urllib.request.urlopen(url, timeout=5) as r:
            return {"_ok": True, **json.loads(r.read())}
    except Exception as e:
        return {"_ok": False, "_err": str(e)}

def read_jsonl_last(path, n=5):
    p = ROOT / path
    if not p.exists(): return []
    lines = p.read_text(encoding="utf-8").strip().split("\n")[-n:]
    out = []
    for l in lines:
        try: out.append(json.loads(l))
        except: pass
    return out

def read_json(path):
    p = ROOT / path
    if not p.exists(): return {}
    try: return json.loads(p.read_text(encoding="utf-8"))
    except: return {}

def count_lines(path):
    p = ROOT / path
    if not p.exists(): return 0
    try: return len(p.read_text(encoding="utf-8").strip().split("\n"))
    except: return 0

def num(v, default=0.0):
    try: return float(v)
    except: return default

def show(v, suffix=""):
    return "—" if v is None else f"{v}{suffix}"

def check_stale(path, max_minutes):
    """Revisa si un archivo se ha actualizado en los últimos X minutos."""
    p = ROOT / path
    if not p.exists(): return False
    mtime = os.path.getmtime(p)
    return (time.time() - mtime) / 60 < max_minutes

# === RECOLECCIÓN ===
hw = fetch(f"http://{ASIC_IP}/api/system/info")
perfect_count = count_lines("data/processed/perfect_shares.jsonl")
champion = read_json("data/processed/evolve_champion.json")
meta = read_jsonl_last("data/processed/meta_learner_recommendations.jsonl", 1)
evolve_pred = read_json("data/processed/evolve_live_prediction.json")
wallet = read_json("data/processed/wallet_state.json")
last_latency = read_jsonl_last("data/processed/latency_sniper_rt.jsonl", 5)
last_ai = read_jsonl_last("data/processed/ai_bridge_log.jsonl", 5)
segwit = read_json("data/audit/segwit_verify_full.json")
taproot = read_json("data/audit/taproot_verify_full.json")

# === EVALUACIÓN DE SALUD (DIAGNÓSTICO) ===
# Diccionario para guardar el estado: "ok", "warn", "error"
health = {
    "asic": {"status": "error", "msg": "Desconectado"},
    "temp": {"status": "ok", "msg": "Normal"},
    "latency": {"status": "ok", "msg": "Rápida"},
    "ai": {"status": "warn", "msg": "Sin datos recientes"},
    "audit": {"status": "ok", "msg": "Verificado"}
}

if hw.get("_ok"):
    health["asic"] = {"status": "ok", "msg": f"Conectado a {ASIC_IP}"}
    t = num(hw.get("temp"))
    if t > 70: health["temp"] = {"status": "error", "msg": f"¡Peligro! {t}°C"}
    elif t > 60: health["temp"] = {"status": "warn", "msg": f"Caliente {t}°C"}
    else: health["temp"] = {"status": "ok", "msg": f"Seguro {t}°C"}

if last_latency:
    lat = num(last_latency[-1].get("latency_ms"))
    if lat > 15000: health["latency"] = {"status": "error", "msg": f"Muy lenta ({lat} ms)"}
    elif lat > 8000: health["latency"] = {"status": "warn", "msg": f"Lenta ({lat} ms)"}
    else: health["latency"] = {"status": "ok", "msg": f"Óptima ({lat} ms)"}

if check_stale("data/processed/ai_bridge_log.jsonl", 30):
    health["ai"] = {"status": "ok", "msg": "Activo"}
else:
    health["ai"] = {"status": "error", "msg": "Logs inactivos (>30m)"}

# Colores para el mapa
def get_color(status):
    return {"ok": "#3fb950", "warn": "#d29922", "error": "#f85149"}[status]

# === GENERACIÓN HTML MAPA Y DIAGNÓSTICO ===
map_html = f"""
<div style="background:#161b22; padding:20px; border-radius:8px; border:1px solid #30363d; margin-bottom:20px; text-align:center;">
    <h2 style="color:#58a6ff; margin-bottom:20px; font-size:20px;">🧠 NEURONA MAP - ARQUITECTURA EN VIVO</h2>
    
    <!-- El Mapa -->
    <div style="display:flex; flex-direction:column; align-items:center; gap:15px;">
        <div style="background:#0d1117; border:2px solid {get_color(health['asic']['status'])}; padding:10px 20px; border-radius:8px; color:{get_color(health['asic']['status'])}; font-weight:bold; box-shadow: 0 0 10px {get_color(health['asic']['status'])}55;">
            ⚡ Bitaxe Gamma 602
        </div>
        <div style="color:#8b949e; font-size:12px;">↓ Genera Shares</div>
        
        <div style="display:flex; gap:20px;">
            <div style="background:#0d1117; border:2px solid #58a6ff; padding:10px 20px; border-radius:8px; color:#58a6ff;">📜 Logs y Telemetría</div>
            <div style="background:#0d1117; border:2px solid #58a6ff; padding:10px 20px; border-radius:8px; color:#58a6ff;">🎯 Latency Sniper</div>
        </div>
        <div style="color:#8b949e; font-size:12px;">↓ Regex & Features</div>

        <div style="display:flex; gap:20px;">
            <div style="background:#0d1117; border:2px solid #bc8cff; padding:10px 20px; border-radius:8px; color:#bc8cff;">🧠 MLP Lite (IA)</div>
            <div style="background:#0d1117; border:2px solid #bc8cff; padding:10px 20px; border-radius:8px; color:#bc8cff;">🏆 Meta Learner</div>
        </div>
        <div style="color:#8b949e; font-size:12px;">↓ Predicciones y Pesos</div>

        <div style="background:#0d1117; border:2px solid {get_color(health['ai']['status'])}; padding:10px 20px; border-radius:8px; color:{get_color(health['ai']['status'])}; font-weight:bold; box-shadow: 0 0 10px {get_color(health['ai']['status'])}55;">
            ⚙️ Scheduler Principal (Learning Loop V2)
        </div>
        <div style="color:#8b949e; font-size:12px;">↓ Decisiones</div>

        <div style="display:flex; gap:20px;">
            <div style="background:#0d1117; border:2px solid #f0883e; padding:10px 15px; border-radius:8px; color:#f0883e;">🚗 AI Bridge</div>
            <div style="background:#0d1117; border:2px solid #f0883e; padding:10px 15px; border-radius:8px; color:#f0883e;">🛡️ Rete Engine</div>
            <div style="background:#0d1117; border:2px solid {get_color(health['audit']['status'])}; padding:10px 15px; border-radius:8px; color:{get_color(health['audit']['status'])};">🔐 Auditoría</div>
        </div>
    </div>

    <!-- Panel de Diagnóstico Abajo -->
    <div style="margin-top:30px; border-top:1px solid #30363d; padding-top:20px; text-align:left;">
        <h3 style="color:#8b949e; font-size:12px; margin-bottom:15px; text-transform:uppercase;">🩺 Diagnóstico del Sistema</h3>
        <div style="display:grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap:12px;">
            
            <div style="background:#0d1117; padding:12px; border-radius:6px; border-left:3px solid {get_color(health['asic']['status'])};">
                <div style="font-size:11px; color:#8b949e;">Conexión ASIC</div>
                <div style="font-size:14px; color:{get_color(health['asic']['status'])}; font-weight:bold;">{health['asic']['msg']}</div>
            </div>

            <div style="background:#0d1117; padding:12px; border-radius:6px; border-left:3px solid {get_color(health['temp']['status'])};">
                <div style="font-size:11px; color:#8b949e;">Temperatura</div>
                <div style="font-size:14px; color:{get_color(health['temp']['status'])}; font-weight:bold;">{health['temp']['msg']}</div>
            </div>

            <div style="background:#0d1117; padding:12px; border-radius:6px; border-left:3px solid {get_color(health['latency']['status'])};">
                <div style="font-size:11px; color:#8b949e;">Latencia de Red</div>
                <div style="font-size:14px; color:{get_color(health['latency']['status'])}; font-weight:bold;">{health['latency']['msg']}</div>
            </div>

            <div style="background:#0d1117; padding:12px; border-radius:6px; border-left:3px solid {get_color(health['ai']['status'])};">
                <div style="font-size:11px; color:#8b949e;">Actividad de IA</div>
                <div style="font-size:14px; color:{get_color(health['ai']['status'])}; font-weight:bold;">{health['ai']['msg']}</div>
            </div>

        </div>
    </div>
</div>
"""

# ... (El resto de las variables HTML de tu código anterior se mantienen igual)
# Para no hacer esto tan largo, aquí continúa el ranking, shares, etc.
# Omitiré la repetición del HTML de abajo para no confundirte, 
# pero en el script final va todo junto.

html = f"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<meta http-equiv="refresh" content="60">
<title>TEOS HUB - Control Total</title>
<style>
* {{ margin:0; padding:0; box-sizing:border-box; }}
body {{ background:#0d1117; color:#c9d1d9; font-family: -apple-system, 'Segoe UI', sans-serif; padding:20px; }}
.hub-header {{ text-align:center; padding:20px 0; border-bottom:2px solid #30363d; margin-bottom:24px; }}
.hub-title {{ font-size:32px; color:#58a6ff; letter-spacing:2px; }}
.hub-subtitle {{ font-size:12px; color:#8b949e; letter-spacing:3px; margin-top:4px; }}
.grid {{ display:grid; grid-template-columns: repeat(3, 1fr); gap:16px; margin-bottom:16px; }}
.card {{ background:#161b22; padding:18px; border-radius:8px; border-left:4px solid #58a6ff; }}
.card h3 {{ color:#8b949e; font-size:11px; letter-spacing:1.5px; margin-bottom:14px; text-transform:uppercase; }}
.metric {{ font-size:28px; font-weight:bold; color:#c9d1d9; }}
.metric-label {{ font-size:10px; color:#8b949e; margin-bottom:4px; }}
.metric-row {{ display:grid; grid-template-columns: 1fr 1fr; gap:12px; }}
.metric-block {{ margin-bottom:12px; }}
.badge {{ padding:2px 10px; border-radius:12px; font-size:10px; font-weight:bold; }}
.badge-green {{ background:#3fb950; color:#0a0e14; }}
.badge-red {{ background:#f85149; color:#fff; }}
.badge-blue {{ background:#58a6ff; color:#0a0e14; }}
.badge-purple {{ background:#bc8cff; color:#0a0e14; }}
.badge-orange {{ background:#f0883e; color:#0a0e14; }}
.card-green {{ border-left-color:#3fb950; }}
.card-purple {{ border-left-color:#bc8cff; }}
.card-orange {{ border-left-color:#f0883e; }}
.card-red {{ border-left-color:#f85149; }}
.card-yellow {{ border-left-color:#d29922; }}
.full-row {{ grid-column: 1 / -1; }}
.footer {{ text-align:center; padding:16px; color:#8b949e; font-size:11px; border-top:1px solid #30363d; margin-top:16px; }}
.small {{ font-size:11px; color:#8b949e; }}
</style>
</head>
<body>

<div class="hub-header">
    <div class="hub-title">🦾 TEOS NEURONA NEXUS — HUB DE CONTROL</div>
    <div class="hub-subtitle">OPTIMIZAR · DISTRIBUIR · EVOLUCIONAR</div>
</div>

<!-- AQUÍ VA EL NUEVO MAPA Y DIAGNÓSTICO -->
{map_html}

<!-- TUS TARJETAS ORIGINALES (Se mantienen igual) -->
<div class="grid">
    <div class="card">
        <h3>⚡ Hardware — Iron Man</h3>
        <div class="metric-row">
            <div class="metric-block"><div class="metric-label">Frecuencia</div><div class="metric">{show(hw.get("actualFrequency"))} <span style="font-size:14px; color:#8b949e;">MHz</span></div></div>
            <div class="metric-block"><div class="metric-label">Hashrate</div><div class="metric">{num(hw.get("hashRate_10m")):.0f} <span style="font-size:14px; color:#8b949e;">GH/s</span></div></div>
        </div>
        <div class="metric-row">
            <div class="metric-block"><div class="metric-label">ASIC Temp</div><div class="metric" style="color:#3fb950;">{num(hw.get("temp")):.1f}°C</div></div>
            <div class="metric-block"><div class="metric-label">VRM Temp</div><div class="metric" style="color:#d29922;">{num(hw.get("vrTemp")):.0f}°C</div></div>
        </div>
    </div>

    <div class="card card-green">
        <h3>✅ Shares & Precisión</h3>
        <div class="metric-row">
            <div class="metric-block"><div class="metric-label">Aceptados</div><div class="metric" style="color:#3fb950;">{int(num(hw.get("sharesAccepted"))):,}</div></div>
            <div class="metric-block"><div class="metric-label">Rechazados</div><div class="metric" style="color:#f85149;">{int(num(hw.get("sharesRejected")))}</div></div>
        </div>
        <div class="metric-block"><div class="metric-label">Error Global (10 min)</div><div class="metric">{num(hw.get("errorPercentage")):.2f}%</div></div>
        <div class="metric-block"><div class="metric-label">🏆 Momentos 0.00% Error</div><div class="metric" style="color:#bc8cff;">{perfect_count}</div></div>
    </div>

    <div class="card card-yellow">
        <h3>🔍 Anomalías del Ciclo</h3>
        {''.join([f'<div style="display:flex; justify-content:space-between; padding:4px 0;"><span style="color:#8b949e;">{r.get("message", "?")}</span><span style="color:#f85149; font-weight:bold;">{r.get("count", 0)}</span></div>' for r in hw.get("sharesRejectedReasons", [])]) or '<div style="color:#8b949e;">Sin rechazos ✨</div>'}
    </div>
</div>

<div class="grid">
    <div class="card card-purple">
        <h3>🧬 Campeón Evolutivo</h3>
        <div class="metric-block"><div class="metric-label">APE del Campeón</div><div class="metric" style="color:#bc8cff;">{show(champion.get("ape_mean"), "%")}</div></div>
        <div class="metric-block"><div class="metric-label">Predicción Combinada</div><div class="metric">{show(evolve_pred.get("combined_prediction_GHs"))} <span style="font-size:14px; color:#8b949e;">GH/s</span></div></div>
        <div class="small" style="margin-top:8px; margin-bottom:4px;">Pesos:</div>
        {''.join([f'<div style="display:flex; justify-content:space-between; padding:4px 0;"><span style="color:#c9d1d9;">{k}</span><span style="color:#58a6ff; font-weight:bold;">{num(v) * 100:.1f}%</span></div>' for k, v in champion.get("weights", {}).items()]) or '<div class="small">—</div>'}
    </div>

    <div class="card" style="border-left-color:#58a6ff;">
        <h3>🧠 Ranking Meta Learner</h3>
        {''.join([f'<div style="display:flex; justify-content:space-between; padding:6px 0; border-bottom:1px solid #30363d;"><span>{r.get("method", "?")}</span><span style="color:{get_color("ok" if num(r.get("combined_median_ape")) < 3.5 else "warn" if num(r.get("combined_median_ape")) < 4.5 else "error")}; font-weight:bold;">{num(r.get("combined_median_ape")):.4f}%</span></div>' for r in (meta[0].get("ranking", []) if meta else [])]) or '<div class="small">Sin datos</div>'}
    </div>

    <div class="card card-orange">
        <h3>🚗 AI Bridge</h3>
        {''.join([f'<div style="padding:4px 0; border-bottom:1px solid #21262d; font-size:11px;"><span style="color:#8b949e;">→ {a.get("new_freq")} MHz</span> · <span>{(a.get("reason") or "")[:60]}</span></div>' for a in reversed(last_ai)]) or '<div class="small">Sin decisiones</div>'}
    </div>
</div>

<div class="grid">
    <div class="card" style="border-left-color:#58a6ff;">
        <h3>🎯 Latency Sniper</h3>
        {''.join([f'<div style="display:flex; justify-content:space-between; padding:4px 0; border-bottom:1px solid #21262d;"><span>Bloque #{l.get("block_height")}</span><span style="color:{get_color("ok" if num(l.get("latency_ms")) < 5000 else "warn" if num(l.get("latency_ms")) < 10000 else "error")}; font-weight:bold;">{num(l.get("latency_ms")):.0f} ms</span></div>' for l in reversed(last_latency)]) or '<div class="small">Sin datos</div>'}
    </div>

    <div class="card card-green">
        <h3>💰 Wallet Bitcoin</h3>
        <div class="metric-block"><div class="metric-label">Saldo Confirmado</div><div class="metric" style="color:#3fb950;">{num(wallet.get("confirmed_sats")) / 100_000_000:.8f} BTC</div></div>
        <div class="metric-block"><div class="metric-label">Pendiente</div><div class="metric">{int(num(wallet.get("pending_sats"))):,} sats</div></div>
    </div>

    <div class="card card-green">
        <h3>🔐 Auditoría</h3>
        <div class="metric-block"><div class="metric-label">SegWit</div><div class="metric" style="color:#3fb950;">{int(num(segwit.get("valid")))} txs</div></div>
        <div class="metric-block"><div class="metric-label">Taproot</div><div class="metric" style="color:#3fb950;">{int(num(taproot.get("valid")))} txs</div></div>
    </div>
</div>

<div class="footer">
    <div>🦾 TEOS NEURONA NEXUS · Generado por <span style="color:#58a6ff;">generate_hub.py</span></div>
</div>

</body>
</html>
"""

OUTPUT.parent.mkdir(parents=True, exist_ok=True)
OUTPUT.write_text(html, encoding="utf-8")
print(f"✅ TEOS HUB ACTUALIZADO: {OUTPUT}")
