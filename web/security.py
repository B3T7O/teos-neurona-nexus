"""
TEOS Security Layer - Defensas mínimas para servidor local.
No requiere dependencias externas. ~1MB de RAM.
"""
import time
import threading
from collections import defaultdict, deque

# --- Configuración ---
ALLOWED_HOSTS = {"localhost", "127.0.0.1", "::1"}
RATE_LIMIT_PER_MIN = 300          # peticiones por minuto por IP
RATE_WINDOW_SEC = 60

# Rutas que NUNCA se sirven como archivos estáticos
BLOCKED_SUFFIXES = (
    ".py", ".pyc", ".pyo", ".pyd",
    ".log", ".env", ".ini", ".toml", ".cfg",
    ".db", ".sqlite", ".sqlite3",
    ".bak", ".backup", ".old", ".swp",
)
BLOCKED_PREFIXES = (
    "/.git", "/.env", "/__pycache__",
    "/data/raw", "/data/processed", "/logs",
    "/config", "/core", "/tests", "/tools",
)

# --- Rate limiting en memoria (por IP) ---
_rate_lock = threading.Lock()
_rate_buckets = defaultdict(deque)  # ip -> deque de timestamps


def check_rate_limit(client_ip: str) -> bool:
    """Devuelve True si la petición está permitida, False si excede el límite."""
    now = time.time()
    with _rate_lock:
        bucket = _rate_buckets[client_ip]
        # Limpiar timestamps fuera de la ventana
        while bucket and (now - bucket[0]) > RATE_WINDOW_SEC:
            bucket.popleft()
        if len(bucket) >= RATE_LIMIT_PER_MIN:
            return False
        bucket.append(now)
        return True


def validate_host(host_header: str) -> bool:
    """Acepta solo Host de localhost. Bloquea DNS rebinding."""
    if not host_header:
        return False
    host_only = host_header.split(":")[0].strip().lower()
    return host_only in ALLOWED_HOSTS


def is_blocked_path(path: str) -> bool:
    """Bloquea path traversal y archivos sensibles."""
    # Normalizar para detectar ../ y %2e%2e
    import urllib.parse
    decoded = urllib.parse.unquote(path).lower()
    if ".." in decoded or "\x00" in decoded:
        return True
    for prefix in BLOCKED_PREFIXES:
        if decoded.startswith(prefix):
            return True
    for suffix in BLOCKED_SUFFIXES:
        if decoded.endswith(suffix):
            return True
    return False


def security_headers() -> dict:
    """Cabeceras HTTP de seguridad estándar."""
    return {
        "X-Content-Type-Options": "nosniff",
        "X-Frame-Options": "DENY",
        "Referrer-Policy": "no-referrer",
        "Permissions-Policy": "geolocation=(), microphone=(), camera=()",
        "Content-Security-Policy": (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline'; "
            "style-src 'self' 'unsafe-inline'; "
            "connect-src 'self'; "
            "img-src 'self' data:; "
            "frame-ancestors 'none'"
        ),
    }


def log_block(client_ip: str, path: str, reason: str) -> None:
    """Registro simple de intentos bloqueados (sin dependencias)."""
    try:
        from datetime import datetime, timezone
        ts = datetime.now(timezone.utc).isoformat()
        with open("/tmp/teos_security.log", "a", encoding="utf-8") as f:
            f.write(f"{ts} | BLOCKED | {client_ip} | {path} | {reason}\n")
    except Exception:
        pass
