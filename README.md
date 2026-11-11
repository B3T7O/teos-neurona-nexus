# TEOS Neurona Nexus

**AI-powered telemetry and predictive analytics for open-source Bitcoin mining.**

[![Status](https://img.shields.io/badge/status-prototype--functional-brightgreen)](.)
[![License: Apache 2.0](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.12-blue)](.)

---

## What is TEOS?

TEOS Neurona Nexus is a lightweight, open-source AI core that observes, predicts, and evaluates the performance of Bitcoin mining hardware in real time. Unlike traditional dashboards that only display historical data, TEOS runs a continuous learning loop: it predicts the next hashrate sample, measures its own error, detects anomalies, and - when conditions allow - decides whether to adjust the ASIC frequency or voltage.

The current prototype manages a **Bitaxe Gamma 602** (SHA-256), demonstrating predictive accuracy (APE) of **~2%** over 70,000+ evaluated predictions.

## The Problem

Open-source mining tools today are limited to *monitoring* - they show you what happened, not what is about to happen. Commercial solutions exist but are closed, expensive, and locked to industrial-scale operators. Individual miners have no intelligent layer to protect their hardware, optimize power efficiency, or learn from their own telemetry.

## The Solution

TEOS is a **self-hosted, dependency-light AI layer** that runs on consumer hardware (even a 4 GB laptop) and provides:

- **Real-time telemetry:** a web dashboard showing hashrate, ASIC temperature, VR temperature, and frequency, updated every few seconds.
- **Predictive engine:** a ridge-regression model that forecasts the next hashrate sample, evaluated against real data (MAE/RMSE/APE tracked live).
- **Neuron state machine:** the system classifies its own state in real time (Learning, Idle, Jump, Anomaly, Record) and reflects it visually.
- **Persistent audit:** every prediction, evaluation, and decision is logged to append-only JSONL files. Nothing is overwritten.
- **Safety policy:** the controller **never** increases frequency or voltage automatically. It only reduces them if thermal or performance thresholds are breached.

## Current Status (November 2026)

TEOS is a **functional prototype** running continuously on the developer machine:

| Metric | Value |
|---|---|
| Samples collected (raw) | **18,600+** |
| Predictions evaluated | **72,000+** |
| Mean Absolute Percentage Error (APE) | **~2.30%** |
| Bitaxe shares accepted | **120,000+** |
| Bitaxe shares rejected | **363** (0.3%) |
| Uptime (Bitaxe) | **~5 days continuous** |

### Hardware Control Verified

The controller successfully downgraded the Bitaxe from 525 MHz to 500 MHz, verified the change (temperature dropped 0.4 C), and safely restored the original configuration.

### Energy Optimization Verified

Undervolting from 1150 mV to 1100 mV improved energy efficiency by **10.5%** (from 20.57 to 18.40 J/TH) without loss of hashrate or rejected shares.

### The Honest Bottleneck

Development runs on a **4 GB RAM laptop** (Windows + WSL2). This is not enough to run the full learning_loop_v2 module simultaneously with the collector, scheduler, and web server. The deep-learning loop is therefore **temporarily disabled**; the lighter scheduler continues predicting and evaluating on its own.

The code for the full loop is written, tested, and committed. It is waiting for **more RAM** to run 24/7 without starving the operating system.

This constraint is also a design feature: TEOS runs on almost nothing. Scaling it to adequate hardware will only amplify what it already does well.

## Architecture

```
teos-neurona-nexus/
├── core/          # Collection, scheduling, prediction, evaluation
├── web/           # Dashboard (HTTP server, neuron state, security layer)
├── data/raw/      # Immutable raw telemetry (JSONL)
├── data/processed/# Validated predictions and outcomes (JSONL)
├── tools/         # Audit engine and utilities
├── docs/          # Technical documentation and closure reports
└── tests/         # Unit tests
```

Key components:
- core/collector.py - reads the Bitaxe REST API every ~60 s, appends raw samples.
- core/scheduler.py - orchestrates prediction and evaluation cycles.
- core/neurona_ridge_live.py - live ridge-regression predictor.
- core/bitaxe_control.py - safe controller (dry-run by default; only reduces frequency under stress).
- core/learning_loop_v2.py - full learning loop (currently disabled for RAM).
- web/server.py - HTTP dashboard + API endpoints.
- web/security.py - host validation, rate limiting, path-traversal protection.
- tools/teos_audit.py - read-only system audit (health, freshness, duplicate detection, quality).


### Dashboard access

- **Canonical dashboard (today):** `http://127.0.0.1:8765/pitch.html` — cinematic, responsive, all 9 data panels connected.
- **Legacy dashboard:** `http://127.0.0.1:8765/` — older layout, some panels still pending. Will be archived soon.
- **Planned unification:** In the next release, `pitch.html` will become the default `index.html` and the legacy dashboard will move to `legacy.html`. From that point, `http://127.0.0.1:8765/` will always show the canonical screen. See `CHANGELOG.md` for details.

## Quick Start

```bash
git clone https://github.com/B3T7O/teos-neurona-nexus.git
cd teos-neurona-nexus

# Configure your Bitaxe IP
export BITAXE_IP=192.168.1.100   # change to your miner LAN IP

# Install systemd user services (Linux/WSL2)
cp systemd/*.service ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now teos-colector teos-scheduler teos-web

# Open the dashboard
xdg-open http://127.0.0.1:8765
```

Full operational guide: see RUNBOOK.md.

## Roadmap

- [x] **Phase 1 - Observation.** Reliable raw telemetry with deduplication and validation.
- [x] **Phase 2 - Prediction.** Live ridge-regression predictor with self-evaluation.
- [x] **Phase 3 - Decision.** Safe controller with dry-run and applied-mode logging.
- [x] **Phase 4 - Dashboard.** Real-time web interface with neuron state machine.
- [x] **Phase 4.5 - Hardware Control.** Verified downgrade/restore + undervolting (-10.5% energy).
- [ ] **Phase 5 - Multi-Device.** Fleet orchestration (many miners, one brain). *Blocked by RAM.*
- [ ] **Phase 6 - Efficiency Optimization.** Dynamic undervolting with A/B testing.
- [ ] **Phase 7 - Protocol Integration.** Connection to Stratum V2 and the Mining Development Kit (MDK).

## Why Open Source?

The Bitcoin mining stack is increasingly centralized. A handful of firmware vendors and pool operators control the tooling that individual miners depend on. TEOS aims to give that intelligence back to the individual: transparent code, auditable decisions, no vendor lock-in.

If you are a solo miner, a small farm operator, or a researcher in distributed systems, TEOS is built for you.

## Reference Implementation

This repository is the **canonical, original implementation** of TEOS Neurona Nexus, created by **Luis Alberto Siguencia Andrade (B3T7O)** in Ecuador starting November 2026.

Forks and derivative works are welcome under the terms of the Apache 2.0 license. If you build on this work, please credit the original:

> *"Based on TEOS Neurona Nexus by Luis Alberto Siguencia Andrade (B3T7O), https://github.com/B3T7O/teos-neurona-nexus"*

## License

This project is licensed under the **Apache License 2.0** - see LICENSE for details.

## Contact & Contributing

- **Author:** Luis Alberto Siguencia Andrade (B3T7O)
- **Location:** Ecuador
- **Email:** teos.neurona@proton.me
- **Telegram:** @B3T7O (optional)
- **GitHub Issues:** welcome for bug reports and feature requests

For grant inquiries, please reach out via email. For general collaboration, open a GitHub Issue or contact via Telegram.

---

*TEOS - Optimize. Distribute. Evolve.*
 


---

## Auto-reparacion y evolucion autonoma (v1.1)

A partir del 2026-11-11, TEOS incluye dos procesos autonomicos en produccion:

### tools/auto_healer.py --execute
- Frecuencia: cada 5 minutos
- Que hace: verifica los 3 servicios systemd (collector, scheduler, api), el Bitaxe
  y la frescura del collector. Si algo esta caido, lo reinicia via systemctl restart.
- Que NO hace: no borra archivos, no modifica codigo, no cambia configuracion.
- Log: data/healer/healer_log.jsonl
- Modo simulacion: sin --execute solo reporta, no actua.

### tools/evolve_runner.py --execute
- Frecuencia: cada 6 horas
- Que hace: ejecuta core/evolve_lab.py (algoritmo genetico de 100 individuos x
  50 generaciones) para encontrar los pesos optimos de combinacion de los 5 metodos
  de prediccion. Guarda el campeon en data/processed/evolve_champion.json.
- Log: data/evolve/evolve_log.jsonl
- Modo simulacion: sin --execute solo reporta, no evoluciona.

### tools/backfill_ridge_outcomes.py (one-shot)
- Rellena outcomes huerfanos del ridge_live (predicciones sin evaluacion).
- Idempotente: no duplica si ya existe.

### Champion actual (2026-11-11)
- ape_mean: 2.2668%
- weights: referencia_1h=0.8294, referencia_10m=0.0928,
  adaptativo_neurona=0.0585, media_ultimas_5=0.0139, ultimo_hashrate=0.0055
- El ensamble supera al mejor metodo individual (2.2668% < 2.27%).
