#!/usr/bin/env python3
import json
import subprocess
import math
import sys
from pathlib import Path
from datetime import datetime, timezone
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from teos_pow_adapter import build_pow_status

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from core.audit_reader import build_audit_summary
WEB = ROOT / "web"
RAW = ROOT / "data/raw/bitaxe_samples.jsonl"
ANALYSIS = ROOT / "data/processed/analysis_history.jsonl"
NEURON_STATE = ROOT / "data/processed/prospective_eval_state.json"
NEURON_SIGNALS = ROOT / "data/processed/prospective_signals.jsonl"
NEURON_OUTCOMES = ROOT / "data/processed/prospective_outcomes.jsonl"
V2_PREDICTIONS = ROOT / "data/processed/learning_predictions_v2.jsonl"
V2_OUTCOMES = ROOT / "data/processed/learning_outcomes_v2.jsonl"
TREND_MEMORY_REPORT = ROOT / "data/processed/trend_memory_report.json"
CONTEXTUAL_ADAPTATION_REPORT = ROOT / "data/processed/contextual_adaptation_report.json"
ANOMALY_EVENTS = ROOT / "data/processed/anomaly_events.jsonl"


def read_jsonl(path, limit=90):
    try:
        with path.open("r", encoding="utf-8") as f:
            lines = f.readlines()[-limit:]
        result = []
        for line in lines:
            try:
                item = json.loads(line)
                if isinstance(item, dict):
                    result.append(item)
            except json.JSONDecodeError:
                continue
        return result
    except (OSError, UnicodeError):
        return []



def read_all_jsonl(path):
    rows = []
    try:
        with path.open("r", encoding="utf-8") as stream:
            for line in stream:
                try:
                    item = json.loads(line)
                    if isinstance(item, dict):
                        rows.append(item)
                except json.JSONDecodeError:
                    continue
    except (OSError, UnicodeError):
        pass
    return rows


def read_json_file(path):
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, UnicodeError, json.JSONDecodeError):
        return {}


def build_experience_memory():
    methods = (
        "ultimo_hashrate",
        "referencia_10m",
        "referencia_1h",
        "media_ultimas_5",
    )
    predictions = read_all_jsonl(V2_PREDICTIONS)
    outcomes = read_all_jsonl(V2_OUTCOMES)

    pred_by_id = {}
    for row in predictions:
        pid = row.get("prediction_id")
        if pid:
            pred_by_id[pid] = row

    # Evitar contar resultados duplicados y resultados sin predicción.
    out_by_id = {}
    for row in outcomes:
        pid = row.get("prediction_id")
        if pid in pred_by_id and pid not in out_by_id:
            out_by_id[pid] = row

    pending_ids = set(pred_by_id) - set(out_by_id)
    pending_rows = [
        row for row in predictions
        if row.get("prediction_id") in pending_ids
    ]

    method_stats = []
    for method in methods:
        method_preds = [
            row for row in pred_by_id.values()
            if row.get("method") == method
        ]
        errors = []
        percentage_errors = []

        for prediction in method_preds:
            outcome = out_by_id.get(prediction.get("prediction_id"))
            if not outcome:
                continue
            try:
                error = float(outcome["error_GHs"])
                actual = float(outcome["actual_hashRate_GHs"])
                if not math.isfinite(error) or not math.isfinite(actual):
                    continue
                errors.append(error)
                if actual != 0:
                    percentage_errors.append(abs(error) / abs(actual) * 100)
            except (KeyError, TypeError, ValueError):
                continue

        n = len(errors)
        mae = sum(abs(e) for e in errors) / n if n else None
        rmse = math.sqrt(sum(e * e for e in errors) / n) if n else None
        bias = sum(errors) / n if n else None
        mape = (
            sum(percentage_errors) / len(percentage_errors)
            if percentage_errors else None
        )

        method_stats.append({
            "method": method,
            "predictions": len(method_preds),
            "evaluated": n,
            "pending": sum(
                1 for row in method_preds
                if row.get("prediction_id") in pending_ids
            ),
            "mae_GHs": round(mae, 4) if mae is not None else None,
            "rmse_GHs": round(rmse, 4) if rmse is not None else None,
            "bias_GHs": round(bias, 4) if bias is not None else None,
            "mape_pct": round(mape, 4) if mape is not None else None,
        })

    ranked = [
        row for row in method_stats if row["mae_GHs"] is not None
    ]
    best = min(ranked, key=lambda row: row["mae_GHs"]) if ranked else None

    def compact(row):
        if not row:
            return None
        return {
            "prediction_id": row.get("prediction_id"),
            "method": row.get("method"),
            "source_timestamp": row.get("source_timestamp"),
            "target_timestamp": row.get("target_timestamp"),
            "predicted_hashRate_GHs": row.get("predicted_hashRate_GHs"),
            "actual_hashRate_GHs": row.get("actual_hashRate_GHs"),
            "error_GHs": row.get("error_GHs"),
        }

    recent = []
    seen = set()
    latest = None
    for row in reversed(outcomes):
        pid = row.get("prediction_id")
        if not pid or pid not in pred_by_id or pid in seen:
            continue
        seen.add(pid)
        item = compact(row)
        if latest is None:
            latest = item
        recent.append(item)
        if len(recent) >= 8:
            break

    last_pending = None
    if pending_rows:
        row = pending_rows[-1]
        last_pending = {
            "prediction_id": row.get("prediction_id"),
            "method": row.get("method"),
            "source_timestamp": row.get("source_timestamp"),
            "predicted_hashRate_GHs": row.get("predicted_hashRate_GHs"),
        }

    return {
        "status": "MEMORIA DISPONIBLE",
        "prediction_count": len(pred_by_id),
        "evaluated_count": len(set(pred_by_id) & set(out_by_id)),
        "pending_count": len(pending_ids),
        "best_method": best["method"] if best else None,
        "best_mae_GHs": best["mae_GHs"] if best else None,
        "methods": method_stats,
        "latest_outcome": latest,
        "latest_pending": last_pending,
        "recent_experiences": recent,
        "source": "learning_predictions_v2.jsonl + learning_outcomes_v2.jsonl",
        "read_only": True,
    }


def api_data():
    samples = read_jsonl(RAW)
    analyses = read_jsonl(ANALYSIS)
    latest = samples[-1] if samples else {}
    analysis = analyses[-1] if analyses else {}

    online_state = read_json_file(
        ROOT / "data/processed/online_error_learner_state.json"
    )
    if not isinstance(online_state, dict):
        online_state = {}
    online_learning = {
        "updates": online_state.get("updates", 0),
        "last_update": online_state.get("last_update"),
        "read_only": True,
    }

    timestamp = latest.get("timestamp")
    age = None
    if timestamp:
        try:
            dt = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            age = max(0, (datetime.now(timezone.utc) - dt.astimezone(timezone.utc)).total_seconds())
        except (ValueError, TypeError):
            pass

    try:
        neuron_state = json.loads(NEURON_STATE.read_text(encoding="utf-8"))
        if not isinstance(neuron_state, dict):
            neuron_state = {}
    except (OSError, UnicodeError, json.JSONDecodeError):
        neuron_state = {}

    pending = neuron_state.get("pending", [])
    if not isinstance(pending, list):
        pending = []

    latest_signal_rows = read_jsonl(NEURON_SIGNALS, limit=1)
    latest_outcome_rows = read_jsonl(NEURON_OUTCOMES, limit=1)

    if pending:
        neuron_status = "EVALUANDO PERSISTENCIA"
    elif latest_outcome_rows:
        neuron_status = "RESULTADO REGISTRADO"
    elif neuron_state:
        neuron_status = "OBSERVANDO"
    else:
        neuron_status = "EVALUADOR SIN INICIALIZAR"

    return {
        "online_learning": online_learning,
        "experience_memory": build_experience_memory(),
        "trend_memory": read_json_file(TREND_MEMORY_REPORT),
        "contextual_adaptation": read_json_file(CONTEXTUAL_ADAPTATION_REPORT),
        "neurona": {
            "initialized": bool(neuron_state),
            "status": neuron_status,
            "pending_count": len(pending),
            "last_processed_timestamp": neuron_state.get("last_processed_timestamp"),
            "latest_signal": latest_signal_rows[-1] if latest_signal_rows else None,
            "latest_outcome": latest_outcome_rows[-1] if latest_outcome_rows else None,
        },
        "ok": bool(latest),
        "timestamp": timestamp,
        "age_seconds": age,
        "sample_count": len(samples),
        "analysis_time": analysis.get("analysis_time"),
        "analysis": analysis,
        "latest": latest,
        "anomaly_events": read_jsonl(ANOMALY_EVENTS, limit=500),
            "history": [
            {
                "timestamp": s.get("timestamp"),
                "hashRate": s.get("hashRate"),
                "hashRate_10m": s.get("hashRate_10m"),
                "temp": s.get("temp"),
                "vrTemp": s.get("vrTemp"),
                "frequency": s.get("frequency"),
            }
            for s in samples
        ],
    }


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(WEB), **kwargs)

    # SECURITY GUARD V2 - override de end_headers (forma segura)
    def end_headers(self):
        try:
            from security import security_headers
            for k, v in security_headers().items():
                self.send_header(k, v)
        except Exception:
            pass
        super().end_headers()

    def do_GET(self):
        # SECURITY GUARD V2 - validacion al inicio de do_GET
        try:
            from security import check_rate_limit, validate_host, is_blocked_path, log_block
            client_ip = self.client_address[0] if self.client_address else "unknown"
            host = self.headers.get("Host", "")
            if not validate_host(host):
                log_block(client_ip, self.path, "bad_host")
                self.send_response(403)
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            if not check_rate_limit(client_ip):
                log_block(client_ip, self.path, "rate_limit")
                self.send_response(429)
                self.send_header("Retry-After", "60")
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            if is_blocked_path(self.path):
                log_block(client_ip, self.path, "blocked_path")
                self.send_response(404)
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
        except Exception:
            pass
        # FAST /api/services - consulta systemd real
        if self.path.startswith("/api/services"):
            try:
                import subprocess as _sp
                real = {}
                for name in ["teos-web.service", "teos-colector.service", "teos-scheduler.service"]:
                    try:
                        r = _sp.run(["systemctl", "--user", "is-active", name],
                                    capture_output=True, text=True, timeout=2)
                        real[name] = r.stdout.strip() or "unknown"
                    except Exception:
                        real[name] = "unknown"
                payload = json.dumps({"services": real}).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)
            except Exception as e:
                try:
                    self.send_response(200)
                    self.end_headers()
                except Exception:
                    pass
            return
        # FAST /api/status - lectura directa del ultimo sample
        if self.path.startswith("/api/status"):
            try:
                dp = Path(__file__).parent.parent / "data" / "raw" / "bitaxe_samples.jsonl"
                size = dp.stat().st_size
                with dp.open("rb") as f:
                    if size > 20000:
                        f.seek(size - 20000)
                        f.readline()
                    raw = f.read().decode("utf-8", errors="ignore").strip()
                lines = raw.split(chr(10))
                last = json.loads(lines[-1])
                out = dict(last)
                out["latest"] = dict(last)
                payload = json.dumps(out).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Cache-Control", "no-store")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)
            except Exception as e:
                payload = json.dumps({"error": str(e)}).encode("utf-8")
                try:
                    self.send_response(500)
                    self.send_header("Content-Length", str(len(payload)))
                    self.end_headers()
                    self.wfile.write(payload)
                except Exception:
                    pass
            return
        if self.path.startswith("/api/neuron-state"):
            try:
                from neuron_state import get_state
                payload = json.dumps(get_state()).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Cache-Control", "no-store")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)
            except Exception as e:
                msg = json.dumps({"state": "error", "detail": str(e)}).encode("utf-8")
                try:
                    self.send_response(500)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", str(len(msg)))
                    self.end_headers()
                    self.wfile.write(msg)
                except Exception:
                    pass
            return
        if self.path.split("?")[0] == "/api/audit/summary":
            payload = build_audit_summary()
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if self.path.split("?")[0] == "/api/pow/status":
            payload = build_pow_status()
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(200 if payload.get("ok") else 503)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if self.path.split("?")[0] == "/api/services":
            units = (
                "teos-neurona-api.service",
                "teos-nexus-collector.service",
                "teos-neurona-scheduler.service",
            )
            services = {}
            for unit in units:
                try:
                    result = subprocess.run(
                        ["systemctl", "is-active", unit],
                        capture_output=True,
                        text=True,
                        timeout=3,
                        check=False,
                    )
                    lines = result.stdout.strip().splitlines()
                    state = lines[0].lower() if lines else "unknown"
                    if state not in (
                        "active", "inactive", "failed",
                        "activating", "deactivating", "reloading"
                    ):
                        state = "unknown"
                    services[unit] = state
                except (OSError, subprocess.TimeoutExpired):
                    services[unit] = "unknown"

            body = json.dumps(
                {"services": services}, ensure_ascii=False
            ).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        if self.path.split("?")[0] == "/api/bitaxe/control-status":
            control_log = ROOT / "data/raw/bitaxe_control.jsonl"
            latest = None
            try:
                with control_log.open("r", encoding="utf-8") as stream:
                    for line in stream:
                        try:
                            item = json.loads(line)
                            if isinstance(item, dict):
                                latest = item
                        except json.JSONDecodeError:
                            continue
            except (OSError, UnicodeError):
                pass

            payload = {
                "ok": True,
                "mode": "read-only-status",
                "control_log_exists": control_log.exists(),
                "latest_decision": latest,
                "writes_enabled": False,
            }
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if self.path.split("?")[0] == "/api/status":
            body = json.dumps(api_data(), ensure_ascii=False).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if self.path.split("?")[0] == "/":
            self.path = "/index.html"
        return super().do_GET()

    def log_message(self, fmt, *args):
        print("[NEXUS]", fmt % args)


if __name__ == "__main__":
    server = ThreadingHTTPServer(("127.0.0.1", 8765), Handler)
    print("TEOS NEURONA NEXUS")
    print("Abre en tu navegador: http://localhost:8765")
    print("API local: http://localhost:8765/api/status")
    print("Solo lectura. Para detener: Ctrl+C")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nServidor detenido.")
    finally:
        server.server_close()
