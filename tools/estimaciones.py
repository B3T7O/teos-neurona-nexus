#!/usr/bin/env python3
"""
Estimaciones desde el ultimo sample:
  - Altura actual, tiempo hasta proximo ajuste de dificultad
  - Tiempo hasta proximo halving
  - Probabilidad de encontrar un bloque solo
  - Hashrate de red estimado desde networkDifficulty
"""
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SAMPLES = ROOT / "data" / "raw" / "bitaxe_samples.marked.jsonl"
DIFF_EPOCH = 2016
HALVING_EPOCH = 210000
NEXT_HALVING = 1050000
SEG_PER_BLOCK = 600  # 10 min


def num(o, k):
    v = o.get(k)
    if isinstance(v, (int, float)) and math.isfinite(v):
        return float(v)
    return None


def main():
    # Ultimo sample valido con blockHeight y networkDifficulty
    last = None
    with SAMPLES.open("r", encoding="utf-8", errors="ignore") as f:
        for ln in f:
            ln = ln.strip()
            if not ln:
                continue
            try:
                o = json.loads(ln)
            except Exception:
                continue
            if o.get("quality") != "ok":
                continue
            if num(o, "blockHeight") and num(o, "networkDifficulty"):
                last = o
    if last is None:
        print("No hay sample con blockHeight y networkDifficulty.")
        return

    h = int(num(last, "blockHeight"))
    net_diff = num(last, "networkDifficulty")
    pool_diff = num(last, "poolDifficulty")
    hr_ghs = num(last, "hashRate") or num(last, "hashRate_1m")
    expected_ghs = num(last, "expectedHashrate")
    ts = last.get("timestamp")

    print("=" * 60)
    print(" ESTIMACIONES")
    print("=" * 60)
    print(f"Sample:  {ts}")
    print(f"Altura:  {h}")
    print(f"Hashrate Bitaxe: {hr_ghs:.1f} GH/s  ({hr_ghs/1000:.2f} TH/s)")
    print(f"Expected HW:     {expected_ghs:.1f} GH/s")
    print(f"Network diff:    {net_diff:.0f}")
    print(f"Pool diff:       {pool_diff:.0f}")
    print()

    # ---- Ajuste de dificultad ----
    bloques_al_ajuste = DIFF_EPOCH - (h % DIFF_EPOCH)
    min_al_ajuste = bloques_al_ajuste * (SEG_PER_BLOCK / 60)
    dias_ajuste = min_al_ajuste / 1440
    print(f"=== Proximo ajuste de dificultad ===")
    print(f"  Altura actual:      {h}")
    print(f"  Altura del ajuste:  {h + bloques_al_ajuste} (multiplo de {DIFF_EPOCH})")
    print(f"  Bloques restantes:  {bloques_al_ajuste}")
    print(f"  Tiempo estimado:    {min_al_ajuste:.0f} min  ({dias_ajuste:.2f} dias)")
    print()

    # ---- Halving ----
    bloques_al_halving = NEXT_HALVING - h
    dias_halving = (bloques_al_halving * SEG_PER_BLOCK) / 86400
    anios_halving = dias_halving / 365.25
    print(f"=== Proximo halving ===")
    print(f"  Altura del halving: {NEXT_HALVING}")
    print(f"  Bloques restantes:  {bloques_al_halving}")
    print(f"  Tiempo estimado:    {dias_halving:.0f} dias  ({anios_halving:.2f} anios)")
    print()

    # ---- Hashrate de red estimado ----
    # hashrate_red = networkDifficulty * 2^32 / SEG_PER_BLOCK
    hr_red_hs = net_diff * (2**32) / SEG_PER_BLOCK
    hr_red_ghs = hr_red_hs / 1e9
    hr_red_phs = hr_red_hs / 1e15
    print(f"=== Hashrate de red (estimado desde networkDifficulty) ===")
    print(f"  {hr_red_ghs:.2e} GH/s   ({hr_red_phs:.2f} PH/s)")
    print()

    # ---- Probabilidad de encontrar bloque solo ----
    hr_bitaxe_hs = hr_ghs * 1e9
    prob_por_bloque = hr_bitaxe_hs / hr_red_hs
    bloques_por_dia = 144
    prob_diaria = prob_por_bloque * bloques_por_dia
    tiempo_esperado_dias = 1 / prob_diaria if prob_diaria > 0 else float("inf")
    tiempo_esperado_anios = tiempo_esperado_dias / 365.25

    print(f"=== Probabilidad de encontrar un bloque (solo) ===")
    print(f"  Prob por bloque:  {prob_por_bloque:.2e}")
    print(f"  Prob diaria:      {prob_diaria:.2e}")
    print(f"  Tiempo esperado:  {tiempo_esperado_dias:.2e} dias  "
          f"({tiempo_esperado_anios:.2e} anios)")
    print(f"  En perspectiva:   ~{tiempo_esperado_anios/13.8e9:.2f} veces la edad del universo")
    print()

    # ---- Comparativa: shares en pool ----
    if pool_diff and pool_diff > 0:
        # shares esperados por segundo
        shares_por_seg = hr_bitaxe_hs / (pool_diff * (2**32))
        shares_por_min = shares_por_seg * 60
        shares_por_hora = shares_por_seg * 3600
        print(f"=== Shares esperados (con pool diff = {pool_diff:.0f}) ===")
        print(f"  Por minuto:  {shares_por_min:.3f}")
        print(f"  Por hora:    {shares_por_hora:.2f}")
        print(f"  Por dia:     {shares_por_hora*24:.2f}")
        print()
        print("  (Compara con sharesAccepted reales en tools/shares_coherence.py)")

    print()
    print("=" * 60)


if __name__ == "__main__":
    main()
