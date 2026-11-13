#!/usr/bin/env python3
"""
Captura los logs de AxeOS en vivo desde WebSocket y los guarda en JSON.
Reconecta automaticamente si el WebSocket se cae.
"""
import asyncio
import json
import re
from collections import deque
from datetime import datetime, timezone
from pathlib import Path

try:
    import websockets
except ImportError:
    print("ERROR: falta websockets. pip install websockets")
    raise SystemExit(1)

ROOT = Path(__file__).resolve().parent.parent
OUTPUT = ROOT / "data" / "processed" / "axeos_logs.json"
BITAXE_IP = "192.168.18.45"
WS_URL = f"ws://{BITAXE_IP}/api/ws"
MAX_LINES = 200

buffer = deque(maxlen=MAX_LINES)
# Formato real: 'I (5536640) stratum_api: message...'
LINE_RE = re.compile(r"^([IWED])\s+\((\d+)\)\s+([\w_]+):\s*(.*)$")
# Limpieza de codigos ANSI
ANSI_RE = re.compile(r"[\[][0-9;]*[mHJK]")


def clean_ansi(s):
    return ANSI_RE.sub("", s).replace("[0m", "").replace("[0;32m", "").replace("[0;31m", "").replace("[0;33m", "")


def parse_line(msg):
    msg = clean_ansi(msg)
    m = LINE_RE.match(msg)
    if m:
        return {
            "uptime_ms": int(m.group(2)),
            "category": m.group(3),
            "message": m.group(4).strip(),
            "level": m.group(1),
            "ts": datetime.now(timezone.utc).isoformat(),
        }
    return {
        "uptime_ms": 0,
        "category": "raw",
        "message": msg,
        "level": "I",
        "ts": datetime.now(timezone.utc).isoformat(),
    }


def save():
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(list(buffer), ensure_ascii=False))


async def stream_once():
    async with websockets.connect(WS_URL, ping_interval=20, ping_timeout=10) as ws:
        print(f"✅ Conectado a {WS_URL}")
        async for raw in ws:
            parsed = parse_line(raw)
            buffer.append(parsed)
            save()


async def main():
    print(f"Streamer iniciado. IP: {BITAXE_IP}")
    while True:
        try:
            await stream_once()
        except Exception as e:
            print(f"⚠️  Desconectado: {e}. Reintentando en 5s...")
            await asyncio.sleep(5)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nStreamer detenido.")
