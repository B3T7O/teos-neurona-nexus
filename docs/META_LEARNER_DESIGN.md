# Meta-Learner Design Document (Planned Feature)

**Status:** Design phase, not yet implemented
**Target milestone:** Phase 5.5 (after multi-device orchestration)
**Author:** Luis Alberto Siguencia Andrade (B3T7O)
**Date:** 2026-11-08

---

## 1. Motivation

TEOS Neurona Nexus currently uses **5 prediction methods** evaluated in parallel:

| Method | Description | Current APE |
|---|---|---|
| adaptativo_neurona | Ridge regression with adaptive weights | ~2.30% |
| referencia_10m | 10-minute moving reference | ~2.61% |
| referencia_1h | 1-hour reference | ~2.61% |
| media_ultimas_5 | Average of the last 5 samples | ~2.91% |
| ultimo_hashrate | Last observed value (naive baseline) | ~3.74% |

The validation report shows that `adaptativo_neurona` beats the naive baseline by 38.5%.
However, this is a **fixed comparison**: we always take the winner of the last evaluation.
A meta-learner would learn **which method is most reliable in which context**
(e.g., stable periods vs. jumps, cold vs. hot hardware, morning vs. evening)
and switch dynamically.

## 2. Goal

Build a lightweight second-level model that:

- Takes the **context** as input (recent hashrate variance, temperature, time of day, current method winners).
- Outputs a **probability distribution** over the 5 methods.
- Is trained **online** on the 71,951+ outcomes already recorded.
- Never modifies the production predictor: it only advises which method to trust.

## 3. Architecture

    +----------------------+
    |  Context Extractor   |  -> variance, temp, volatility, trend, ...
    +----------+-----------+
               |
               v
    +----------------------+
    |  Meta-Learner Model  |  (logistic regression or small MLP)
    +----------+-----------+
               |
               v
    +----------------------+
    |  Method Weight Mixer |  -> weighted prediction
    +----------------------+

## 4. Data Requirements

- **Input source:** `data/processed/learning_outcomes_v2.jsonl` (currently 72,516 records).
- **Per record:** `target_timestamp`, `method`, `predicted`, `actual`, `absolute_percentage_error`.
- **Derived features:** rolling APE (30 min and 2 h) per method, hashrate volatility,
  temperature at prediction time, hour of day, day of week, time since last jump (>20% change).

## 5. Model Choice

| Model | Pros | Cons |
|---|---|---|
| Multinomial logistic regression | Small, fast, interpretable | Linear boundaries only |
| Small MLP (3 hidden layers, 64 neurons) | Handles non-linear patterns | Larger, needs more data |

**Recommendation:** Start with logistic regression to prove the concept, upgrade to MLP if validation shows promise.

## 6. Training Plan

- **Offline training:** Use the 72k+ historical outcomes.
- **Walk-forward validation:** Train on months 1-6, test on month 7, then roll forward. Avoids look-ahead bias.
- **Metric:** Compare meta-learner APE vs. `adaptativo_neurona` APE on the test set.
- **Success criterion:** Meta-learner APE < `adaptativo_neurona` APE by at least 0.3 percentage points.

## 7. Hardware Requirements

- **Current laptop (4 GB RAM):** Cannot run offline training.
- **Required:** >= 16 GB RAM to train on the full 72k dataset in memory.
- **Inference (online):** < 1 MB of memory. Can run on current hardware.

## 8. Integration Plan

1. Add `core/meta_learner.py` (inference only, initially).
2. Add `core/meta_learner_train.py` (offline training script).
3. Add a new endpoint `/api/meta` to the dashboard.
4. Add a panel in `pitch.html` showing the meta-learner recommendation.
5. Run in **shadow mode** for 2 weeks (observe but don't act).
6. If shadow mode shows improvement, promote to production.

## 9. Risks and Mitigations

| Risk | Mitigation |
|---|---|
| Overfitting to historical data | Walk-forward validation |
| Slow inference on 4 GB laptop | Keep model small (logistic regression first) |
| Confusing UX | Shadow mode; display advice, not action |
| Data drift | Retrain monthly or trigger on APE degradation |

## 10. Timeline (Post-Grant)

- **Month 1:** Design finalization, feature extraction.
- **Month 2:** Model training, walk-forward validation.
- **Month 3:** Shadow mode deployment, dashboard integration.
- **Month 4:** (if successful) Promote to production.

## 11. References

- `data/processed/validation_report.json` — current method performance
- `data/processed/learning_outcomes_v2.jsonl` — training data
- `tools/analyze_predictions.py` — baseline analysis script
