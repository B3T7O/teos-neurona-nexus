"""
TEOS Guardian v1.0
==================
Autonomous watchdog. Observes RAM, CPU, Bitaxe, and services.
- Writes state to data/guardian/state.json (read by the dashboard)
- Logs to logs/guardian.log
- On critical RAM, pauses learning_loop via data/guardian/PAUSE_LEARNING
- Optional email notifications (configure config/guardian.ini)
"""
import json
import logging
import os
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GUARDIAN_DIR = ROOT / "data" / "guardian"
STATE_FILE = GUARDIAN_DIR / "state.json"
EVENTS_FILE = GUARDIAN_DIR / "guardian_events.jsonl"
PAUSE_FLAG = GUARDIAN_DIR / "PAUSE_LEARNING"
CONFIG_FILE = ROOT / "config" / "guardian.ini"

GUARDIAN_DIR.mkdir(parents=True, exist_ok=True)
(ROOT / "logs").mkdir(exist_ok=True)

# Logging a archivo
logging.basicConfig(
    filename=str(ROOT / "logs" / "guardian.log"),
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)

# Umbrales (en MB)
RAM_CRITICAL_MB = 150
RAM_WARNING_MB = 300
CPU_CRITICAL_PCT = 95
CPU_WARNING_PCT = 80
CONSECUTIVE_CRITICAL = 3  # necesita 3 checks seguidos para actuar
INTERVAL = 60  # segundos

# Contador para acciones
_critical_streak = 0


def _ram_free_mb():
    try:
        with open("/proc/meminfo") as f:
            for line in f:
                if line.startswith("MemAvailable:"):
                    return int(line.split()[1]) // 1024
    except Exception:
        pass
    return None


def _cpu_load_pct():
    try:
        with open("/proc/loadavg") as f:
            load1 = float(f.read().split()[0])
        # Asumimos 1 CPU para WSL típico
        return min(100, load1 * 100)
    except Exception:
        return None


def _bitaxe_ok():
    ip = os.environ.get("BITAXE_IP", "192.168.18.45")
    try:
        with urllib.request.urlopen(f"http://{ip}/api/system/info", timeout=3) as r:
            return r.status == 200
    except Exception:
        return False


def _services_active():
    """Devuelve número de los 3 procesos TEOS vivos (por nombre de proceso)."""
    import subprocess
    try:
        out = subprocess.run(
            ["pgrep", "-fc", "core.collector|core.scheduler|web/server"],
            capture_output=True, text=True, timeout=3
        )
        return int(out.stdout.strip() or 0)
    except Exception:
        return -1


def _try_email(subject, body):
    """Envía correo si config/guardian.ini existe. Falla silenciosa si no."""
    if not CONFIG_FILE.exists():
        return False
    try:
        import configparser
        import smtplib
        from email.mime.text import MIMEText
        cfg = configparser.ConfigParser()
        cfg.read(CONFIG_FILE)
        if not cfg.getboolean("email", "enabled", fallback=False):
            return False
        msg = MIMEText(body)
        msg["Subject"] = subject
        msg["From"] = cfg.get("email", "username")
        msg["To"] = cfg.get("email", "to")
        with smtplib.SMTP(
            cfg.get("email", "smtp_host"),
            cfg.getint("email", "smtp_port"),
            timeout=10,
        ) as s:
            s.starttls()
            s.login(cfg.get("email", "username"), cfg.get("email", "password"))
            s.send_message(msg)
        return True
    except Exception as e:
        logging.warning(f"Email falló: {e}")
        return False


def _notify(severity, subject, message):
    """Registra evento + intenta email."""
    logging.log(
        logging.CRITICAL if severity == "CRITICAL" else logging.WARNING,
        f"{subject}: {message}"
    )
    event = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "severity": severity,
        "subject": subject,
        "message": message,
    }
    with EVENTS_FILE.open("a", encoding="utf-8") as f:
        f.write(json.dumps(event) + "\n")
    _try_email(f"[TEOS {severity}] {subject}", message)


def check_once():
    global _critical_streak

    ram = _ram_free_mb()
    cpu = _cpu_load_pct()
    btx = _bitaxe_ok()
    svc = _services_active()

    if ram is None or cpu is None:
        state = "UNKNOWN"
        severity = "WARNING"
        reason = "No se pudo leer /proc"
    elif ram < RAM_CRITICAL_MB:
        _critical_streak += 1
        if _critical_streak >= CONSECUTIVE_CRITICAL:
            state = "CRITICAL"
            severity = "CRITICAL"
            reason = f"RAM crítica: {ram}MB por {_critical_streak} checks seguidos"
        else:
            state = "WARNING"
            severity = "WARNING"
            reason = f"RAM baja: {ram}MB ({_critical_streak}/{CONSECUTIVE_CRITICAL})"
    else:
        _critical_streak = 0
        if ram < RAM_WARNING_MB or cpu > CPU_WARNING_PCT or not btx:
            state = "WARNING"
            severity = "WARNING"
            reason = f"RAM={ram}MB, CPU={cpu:.0f}%, Bitaxe={'OK' if btx else 'NO'}"
        else:
            state = "OK"
            severity = None
            reason = f"RAM={ram}MB, CPU={cpu:.0f}%, Bitaxe=OK"

    # Acción: pausar learning_loop si crítica sostenida
    if state == "CRITICAL" and not PAUSE_FLAG.exists():
        PAUSE_FLAG.write_text(datetime.now(timezone.utc).isoformat())
        _notify("CRITICAL", "Sistema crítico", f"{reason}. He pausado learning_loop.")
    elif state != "CRITICAL" and PAUSE_FLAG.exists():
        PAUSE_FLAG.unlink()
        _notify("WARNING", "Recuperación", f"{reason}. Reanudo learning_loop.")

    elif state == "WARNING" and severity == "WARNING":
        _notify("WARNING", "Advertencia", reason)

    # Estado para el panel
    payload = {
        "state": state,
        "reason": reason,
        "ram_free_mb": ram,
        "cpu_load_pct": round(cpu, 1) if cpu is not None else None,
        "bitaxe_ok": btx,
        "services_active": svc,
        "learning_paused": PAUSE_FLAG.exists(),
        "ts_utc": datetime.now(timezone.utc).isoformat(),
    }
    STATE_FILE.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def main():
    logging.info("TEOS Guardian v1.0 iniciado")
    while True:
        try:
            check_once()
        except Exception as e:
            logging.error(f"Error en check: {e}")
        time.sleep(INTERVAL)


if __name__ == "__main__":
    main()
