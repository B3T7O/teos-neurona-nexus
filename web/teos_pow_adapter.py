#!/usr/bin/env python3
"""Adaptador de solo lectura para las evidencias documentadas de TEOS PoW."""

import hashlib
import json
from pathlib import Path

POW_DIR = Path.home() / "teos-lab-sha256" / "referencias"

CONTINUITY_FILE = POW_DIR / "informe_continuidad_405923_405926_20261025T033413Z.json"
EVIDENCE_FILE = POW_DIR / "evidencia_revalidacion_core_20261025T034337Z.json"
LEDGER_FILE = POW_DIR / "historial_revalidaciones_core.jsonl"


def _read_json(path):
    with path.open("r", encoding="utf-8") as stream:
        value = json.load(stream)
    if not isinstance(value, dict):
        raise ValueError(f"{path.name}: se esperaba un objeto JSON")
    return value


def _read_jsonl(path):
    rows = []
    with path.open("r", encoding="utf-8") as stream:
        for line in stream:
            if line.strip():
                row = json.loads(line)
                if isinstance(row, dict):
                    rows.append(row)
    return rows


def build_pow_status():
    """Resume las evidencias guardadas; no ejecuta minería ni consulta Bitcoin Core."""
    try:
        continuity = _read_json(CONTINUITY_FILE)
        evidence = _read_json(EVIDENCE_FILE)
        ledger = _read_jsonl(LEDGER_FILE)

        continuity_sha = hashlib.sha256(CONTINUITY_FILE.read_bytes()).hexdigest()
        evidence_sha = hashlib.sha256(EVIDENCE_FILE.read_bytes()).hexdigest()

        comparisons = evidence.get("comparaciones", [])
        if not isinstance(comparisons, list):
            comparisons = []

        heights = evidence.get("alturas_verificadas", [])
        if not isinstance(heights, list):
            heights = []

        matching_record = next(
            (
                row for row in reversed(ledger)
                if row.get("evidencia_archivo") == EVIDENCE_FILE.name
            ),
            None,
        )

        report_hash_matches = (
            evidence.get("sha256_informe_continuidad") == continuity_sha
        )
        evidence_hash_matches = (
            matching_record is not None
            and matching_record.get("evidencia_sha256") == evidence_sha
        )

        hashes_ok = sum(
            1 for row in comparisons if row.get("hash_coincide") is True
        )
        previous_ok = sum(
            1 for row in comparisons
            if row.get("previousblockhash_coincide") is True
        )

        continuity_ok = continuity.get("resultado_continuidad") == "CUMPLE"
        evidence_ok = (
            evidence.get("resultado") == "CUMPLE"
            and len(comparisons) == 4
            and hashes_ok == 4
            and previous_ok == 4
        )

        integrity_ok = all((
            report_hash_matches,
            evidence_hash_matches,
            continuity_ok,
            evidence_ok,
        ))

        return {
            "ok": integrity_ok,
            "module": "TEOS PoW",
            "mode": "stored_evidence_read_only",
            "read_only": True,
            "source": "TEOS PoW lab · saved evidence",
            "continuity": {
                "result": continuity.get("resultado_continuidad"),
                "blocks_documented": len(continuity.get("alturas", [])),
                "links_documented": len(continuity.get("enlaces", [])),
                "report_sha256": continuity_sha,
                "report_hash_matches_evidence": report_hash_matches,
            },
            "core_revalidation": {
                "result": evidence.get("resultado"),
                "heights": heights,
                "comparisons_documented": len(comparisons),
                "hash_matches": hashes_ok,
                "previousblockhash_matches": previous_ok,
                "evidence_sha256": evidence_sha,
                "evidence_hash_matches_ledger": evidence_hash_matches,
            },
            "documentary_integrity": (
                "VERIFICADA" if integrity_ok else "REQUIERE_REVISION"
            ),
            "consensus_complete": "NO VERIFICADO",
            "limitations": [
                "Los resultados proceden de evidencias guardadas.",
                "Esta ruta no consulta Bitcoin Core ni ejecuta nuevas pruebas PoW.",
                "La integridad documental no demuestra por sí sola el consenso completo."
            ],
        }
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
        return {
            "ok": False,
            "module": "TEOS PoW",
            "mode": "stored_evidence_read_only",
            "read_only": True,
            "documentary_integrity": "NO DISPONIBLE",
            "consensus_complete": "NO VERIFICADO",
            "error": f"{type(exc).__name__}: {exc}",
        }
