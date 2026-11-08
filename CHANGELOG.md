# Changelog

All notable changes to TEOS Neurona Nexus will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Planned
- **Unify the main dashboard.** Currently there are two dashboards:
  - `pitch.html` → cinematic, responsive, 9 panels connected (canonical).
  - `index.html` → legacy, cluttered, 3 panels still empty.
  In an upcoming release, `pitch.html` will become the default `index.html`
  and the legacy one will be archived as `legacy.html`. All documentation
  will be updated to reflect a single, verified screen for everything.
- **Meta-learner design document** (`docs/META_LEARNER_DESIGN.md`).
- **2 reference letters** for OpenSats application.

## [1.0.0] - 2026-11-08

### Added
- **AI prediction engine:** Ridge regression model with APE ~2.3% over 71,951 predictions.
- **Autonomous hardware control:** Undervolting achieving 10.5% energy efficiency improvement on a Bitaxe Gamma 602.
- **Canonical dashboard (`pitch.html`):** Cinematic, responsive UI with 9 live panels.
- **Built-in audit engine:** `tools/teos_audit.py` — read-only health check (SANO / ADVERTENCIA / CRITICO).
- **Startup script (`start_teos.sh`):** launches exactly 3 processes without WSL/systemd duplicate bug.
- **Security layer:** GPG-signed commits, Apache 2.0 license, `SECURITY.md`, protected `main` branch, 2FA.
- **Validation report:** `data/processed/validation_report.json` (38.5% improvement over baseline).

### Changed
- **Bitaxe IP is now configurable** via `BITAXE_IP` environment variable.
- **`/api/status` fast path:** ~5ms by reading only the last sample.
- **`/api/services`** queries systemd for the 3 real services.
- **`/api/pitch-data`** consolidates all dashboard data in a single JSON payload.

### Fixed
- **WSL/systemd duplicate bug:** systemd services disabled, startup managed by `start_teos.sh`.
- **Historic IP leak:** `git-filter-repo` replaced all instances with `192.168.1.100`.

### Security
- All commits GPG-signed and GitHub-Verified.
- Branch ruleset (block force-push, require signed commits).
- Secret scanning and push protection enabled.
- 2FA enforced.
- `SECURITY.md` added.

## [0.1.0] - 2026-10-21

### Added
- Initial prototype: collector, ridge regression predictor, anomaly detector.
- Historical memory reports: `trend_memory_report.json`, `controlled_adaptation_report.json`.
- First README defining vision and principles.

## [0.0.1] - 2026-10-19

### Added
- Initial repository snapshot with core modules, docs, tests.
- First telemetry samples from the Bitaxe Gamma 602.
