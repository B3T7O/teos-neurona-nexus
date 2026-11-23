#!/usr/bin/env python3
"""
TEOS Shadow Learner V3.1 - honest evaluation.

Fix vs V3:
  - Option 1 trains ONLY on pre-error samples (current error < 1%)
    -> measures ability to PREDICT error ONSET, not continuation
  - Compares against NULL model (always predict majority class)
  - Rejects if f1_test <= null_f1_test + MIN_IMPROVEMENT
  - Option 2 (residual MLP) unchanged
"""
import json
import numpy as np
from pathlib import Path
from datetime import datetime, timezone

BASE = Path(__file__).resolve().parents[2]
DATA = BASE / "data/raw/bitaxe_samples.marked.jsonl"
OUT = BASE / "data/processed/shadow_learner_v3"

FEATURES = [
    "hashRate", "hashRate_1m", "hashRate_10m", "hashRate_1h",
    "temp", "vrTemp", "power", "voltage", "frequency", "fanrpm",
    "errorPercentage", "wifiRSSI",
]
LOOKAHEAD = 5
MIN_IMPROVEMENT = 0.05
TRAIN_RATIO, VAL_RATIO = 0.70, 0.15


def load():
    samples = []
    with DATA.open() as f:
        for line in f:
            try:
                d = json.loads(line)
                if all(k in d for k in FEATURES[:5]):
                    samples.append(d)
            except Exception:
                pass
    return samples


def build_preerror(samples):
    """Only pre-error samples (current error < 1%). Tests onset prediction."""
    X, y = [], []
    for i, s in enumerate(samples):
        if float(s.get("errorPercentage") or 0) >= 1.0:
            continue
        row = [float(s.get(f) or 0) for f in FEATURES]
        fut = 0
        for j in range(i + 1, min(i + 1 + LOOKAHEAD, len(samples))):
            if (samples[j].get("errorPercentage") or 0) > 1.0:
                fut = 1
                break
        X.append(row); y.append(fut)
    return np.array(X, dtype=float), np.array(y)


def build_delta(samples):
    """All samples: delta hashrate t+1."""
    X, y = [], []
    n = len(samples)
    for i, s in enumerate(samples):
        row = [float(s.get(f) or 0) for f in FEATURES]
        if i + 1 < n:
            delta = float(samples[i + 1].get("hashRate") or 0) - float(s.get("hashRate") or 0)
        else:
            delta = 0.0
        X.append(row); y.append(delta)
    return np.array(X, dtype=float), np.array(y)


def split(n):
    a = int(n * TRAIN_RATIO)
    b = int(n * (TRAIN_RATIO + VAL_RATIO))
    return np.arange(0, a), np.arange(a, b), np.arange(b, n)


def standardize(X_tr, X_va, X_te):
    m = X_tr.mean(axis=0); s = X_tr.std(axis=0)
    s[s < 1e-8] = 1.0
    return (X_tr - m) / s, (X_va - m) / s, (X_te - m) / s, m, s


def train_logreg(X, y, epochs=500, lr=0.1):
    n, d = X.shape
    w = np.zeros(d); b = 0.0
    pos = max(y.sum(), 1); neg = max(len(y) - pos, 1)
    weights = np.where(y == 1, len(y) / (2 * pos), len(y) / (2 * neg))
    for _ in range(epochs):
        z = X @ w + b
        p = 1 / (1 + np.exp(-np.clip(z, -500, 500)))
        dz = weights * (p - y) / n
        w -= lr * (X.T @ dz); b -= lr * dz.sum()
    return w, b


def metrics(y, yp):
    tp = ((yp == 1) & (y == 1)).sum(); fp = ((yp == 1) & (y == 0)).sum()
    fn = ((yp == 0) & (y == 1)).sum()
    prec = tp / max(tp + fp, 1); rec = tp / max(tp + fn, 1)
    f1 = 2 * prec * rec / max(prec + rec, 1e-10)
    acc = (yp == y).mean()
    return dict(acc=float(acc), prec=float(prec), rec=float(rec), f1=float(f1))


def null_f1(y):
    """F1 of always predicting the majority class."""
    pos = y.sum(); n = len(y)
    if pos >= n - pos:
        return metrics(y, np.ones_like(y))["f1"]
    else:
        return metrics(y, np.zeros_like(y))["f1"]


def train_mlp(X, y, hidden=8, epochs=300, lr=0.01):
    n, d = X.shape
    np.random.seed(42)
    W1 = np.random.randn(d, hidden) * 0.1; b1 = np.zeros(hidden)
    W2 = np.random.randn(hidden, 1) * 0.1; b2 = np.zeros(1)
    for _ in range(epochs):
        Z1 = X @ W1 + b1; A1 = np.maximum(0, Z1); Z2 = A1 @ W2 + b2
        dZ2 = 2 * (Z2.flatten() - y) / n
        dW2 = A1.T @ dZ2.reshape(-1, 1); db2 = dZ2.sum()
        dA1 = dZ2.reshape(-1, 1) @ W2.T; dZ1 = dA1 * (Z1 > 0)
        W1 -= lr * (X.T @ dZ1); b1 -= lr * dZ1.sum(axis=0)
        W2 -= lr * dW2; b2 -= lr * db2
    return W1, b1, W2, b2


def predict_mlp(X, W1, b1, W2, b2):
    return (np.maximum(0, X @ W1 + b1) @ W2 + b2).flatten()


def main():
    print("=== TEOS Shadow Learner V3.1 (honest) ===")
    samples = load()
    print(f"Samples totales: {len(samples)}")

    # ---------- OPTION 1 ----------
    print("\n=== OPTION 1: onset prediction (only pre-error samples) ===")
    X1, y1 = build_preerror(samples)
    print(f"Pre-error samples: {len(X1)} | error rate: {y1.mean()*100:.1f}%")
    if len(X1) < 1000:
        print("Too few pre-error samples"); opt1_status = "REJECTED"; opt1_rec = {}
    else:
        tr, va, te = split(len(X1))
        X_tr, X_va, X_te, m1, s1 = standardize(X1[tr], X1[va], X1[te])
        w, b = train_logreg(X_tr, y1[tr])
        # Predict
        p_va = (1/(1+np.exp(-np.clip(X_va @ w + b, -500, 500))) > 0.5).astype(int)
        p_te = (1/(1+np.exp(-np.clip(X_te @ w + b, -500, 500))) > 0.5).astype(int)
        m_va = metrics(y1[va], p_va)
        m_te = metrics(y1[te], p_te)
        n_va = null_f1(y1[va]); n_te = null_f1(y1[te])
        print(f"Null baseline F1: val={n_va:.4f} test={n_te:.4f}")
        print(f"Model       F1:   val={m_va['f1']:.4f} test={m_te['f1']:.4f}")
        print(f"Model   val: acc={m_va['acc']:.3f} prec={m_va['prec']:.3f} rec={m_va['rec']:.3f}")
        print(f"Model  test: acc={m_te['acc']:.3f} prec={m_te['prec']:.3f} rec={m_te['rec']:.3f}")
        delta_f1 = m_te['f1'] - n_te
        print(f"Delta vs null: {delta_f1*100:+.2f}%")
        if delta_f1 > MIN_IMPROVEMENT:
            opt1_status = "ACCEPTED"
        else:
            opt1_status = "REJECTED"
        print(f"Status: {opt1_status}")
        opt1_rec = {
            "null_f1_val": n_va, "null_f1_test": n_te,
            "model_f1_val": m_va['f1'], "model_f1_test": m_te['f1'],
            "delta_f1": float(delta_f1),
            "weights": w.tolist(), "intercept": float(b),
            "scaler_mean": m1.tolist(), "scaler_std": s1.tolist(),
            "preerror_samples": int(len(X1)),
        }

    # ---------- OPTION 2 ----------
    print("\n=== OPTION 2: residual MLP (delta hashrate) ===")
    X2, y2 = build_delta(samples)
    print(f"Delta samples: {len(X2)} | mean={y2.mean():.3f} std={y2.std():.3f}")
    tr2, va2, te2 = split(len(X2))
    X2_tr, X2_va, X2_te, m2, s2 = standardize(X2[tr2], X2[va2], X2[te2])
    W1, b1, W2, b2 = train_mlp(X2_tr, y2[tr2])
    pred_va = predict_mlp(X2_va, W1, b1, W2, b2)
    pred_te = predict_mlp(X2_te, W1, b1, W2, b2)
    mae_va = float(np.mean(np.abs(pred_va - y2[va2])))
    mae_te = float(np.mean(np.abs(pred_te - y2[te2])))
    persist_va = float(np.mean(np.abs(y2[va2])))
    persist_te = float(np.mean(np.abs(y2[te2])))
    imp = (persist_te - mae_te) / max(persist_te, 1e-10)
    print(f"Persistence MAE: val={persist_va:.4f} test={persist_te:.4f}")
    print(f"MLP MAE:         val={mae_va:.4f} test={mae_te:.4f}")
    print(f"Improvement: {imp*100:+.2f}%")
    opt2_status = "ACCEPTED" if imp > MIN_IMPROVEMENT else "REJECTED"
    print(f"Status: {opt2_status}")

    # ---------- SAVE ----------
    OUT.mkdir(parents=True, exist_ok=True)
    report = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "version": "v3.1_honest",
        "data_samples": len(samples),
        "lookahead": LOOKAHEAD,
        "min_improvement": MIN_IMPROVEMENT,
        "option1": {"status": opt1_status, **opt1_rec},
        "option2": {
            "status": opt2_status,
            "persist_mae_val": persist_va, "persist_mae_test": persist_te,
            "mlp_mae_val": mae_va, "mlp_mae_test": mae_te,
            "improvement": float(imp),
            "W1": W1.tolist(), "b1": b1.tolist(), "W2": W2.tolist(), "b2": b2.tolist(),
            "scaler_mean": m2.tolist(), "scaler_std": s2.tolist(),
        },
        "features": FEATURES,
    }
    (OUT / "training_report_v3_1.json").write_text(json.dumps(report, indent=2))
    if opt1_status == "ACCEPTED":
        (OUT / "classifier_v1_honest.json").write_text(json.dumps(opt1_rec, indent=2))
        print("✓ classifier_v1_honest.json guardado")
    if opt2_status == "ACCEPTED":
        (OUT / "residual_mlp_v3.json").write_text(json.dumps(report["option2"], indent=2))
        print("✓ residual_mlp_v3.json guardado")
    print(f"\nReport: {OUT / 'training_report_v3_1.json'}")


if __name__ == "__main__":
    main()
