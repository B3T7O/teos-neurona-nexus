#!/usr/bin/env python3
"""Muestra el historial central de evoluciones."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.evolution_history import read_all, summarize_by_learner


def main():
    print("=" * 70)
    print(" HISTORIAL CENTRAL DE EVOLUCIONES")
    print("=" * 70)

    summary = summarize_by_learner()
    if not summary:
        print("\n(vacio - aun no hay evoluciones registradas)\n")
        return

    print("\n=== RESUMEN POR LEARNER ===")
    for learner, s in sorted(summary.items()):
        last_ts = s["last"]["ts"][:19] if s["last"] else "-"
        print(f"  {learner:20s}  total={s['total']:4d}  ok={s['ok']:4d}  "
              f"failed={s['failed']:3d}  ultimo={last_ts}")

    print("\n=== ULTIMAS 30 ENTRADAS ===")
    entries = read_all(limit=30)
    for e in entries:
        ts = e.get("ts", "?")[:19]
        learner = e.get("learner", "?")
        kind = e.get("kind", "?")
        detail = e.get("detail", "")[:50]
        print(f"  {ts} | {learner:18s} | {kind:15s} | {detail}")


if __name__ == "__main__":
    main()
