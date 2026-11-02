# Tasks

## 1. Inventory and evidence

- [x] 1.1 Read every Rust source file under `src/`, including binaries, exchange, strategies, store, orders, logging, config, and utilities
- [x] 1.2 Read every strategy template in `config/`, the systemd unit, `update.sh`, the deployment workflow, `Cargo.toml`, `README.md`, and `MIGRATION.md`
- [x] 1.3 Inspect `migrations/001_create_tables.sql` and confirm no running path opens a database
- [x] 1.4 Inspect the archived Python files only to validate claimed compatibility and intentional fixes
- [x] 1.5 Run `cargo test` and record the result (28 passed, 0 failed); note that `cargo clippy` is unavailable
- [x] 1.6 Confirm the flow image is not referenced by code and cannot be used as evidence

## 2. Baseline capability specifications

- [x] 2.1 Write `runtime-configuration` covering dotenv discovery, environment flag precedence, and credential resolution
- [x] 2.2 Write `exchange-connectivity` covering base URLs, clock sync, signing, REST surface, error translation, and single-attempt transport
- [x] 2.3 Write `market-metadata-and-conventions` covering filters, rounding, formatting, distance, and base-asset naming
- [x] 2.4 Write `order-execution-and-cancellation` covering order shapes, grid batches, cancellation scopes, and absorbed errors
- [x] 2.5 Write `user-data-stream-and-dispatch` covering listen key, keepalive, reconnect, filtering, routing, and per-symbol ordering
- [x] 2.6 Write `operation-state-store` covering file layout, reads, writes, accessors, strategy lookup, and whole-document replacement
- [x] 2.7 Write `strategy-cardiac` covering input, adoption, sizing, entry, fill handling, stop loss, unload, and take profit
- [x] 2.8 Write `strategy-load-unload-grid` covering input, adoption, grid math, constant-risk stop, placement, classification, and fill branches
- [x] 2.9 Write `strategy-recovery-zone` covering entries, hedge, recovery escalation, distances, targets, trailing stop, and terminal fills
- [x] 2.10 Write `runtime-operations` covering binaries, logging, service, deployment, secrets, and continuity
- [x] 2.11 Add `Provenance`, `Assumptions`, and `Known deviations` to every capability spec

## 3. Audit record

- [x] 3.1 Write the proposal explaining why the baseline is needed and what it changes
- [x] 3.2 Write the design with method, verification boundary, capability boundaries, defect treatment, contradictions, and out-of-scope items
- [x] 3.3 Record a severity-ranked risk register with consequence-oriented findings
- [x] 3.4 Record the recommended follow-up sequence without implementing it
- [x] 3.5 Add project context to `openspec/config.yaml` clarifying that the specs describe current behavior and that deviations are not approved intent

## 4. Verification

- [x] 4.1 Confirm no application source, config template, migration, service file, or deployment script was modified
- [x] 4.2 Validate all specs and changes with `openspec validate --all --no-interactive`
- [x] 4.3 Confirm the stale `add-dca-safety-assistant` change is left untouched and marked superseded in this audit

## 5. Follow-up (not part of this change)

- [ ] 5.1 Propose a separate change for environment selection and fail-closed startup (R1)
- [ ] 5.2 Propose a separate change for order-error propagation and position protection state (R2)
- [ ] 5.3 Propose a separate change for startup reconciliation and fill recovery (R3, R4)
- [ ] 5.4 Propose separate changes for filters, idempotency, cancellation scope, and state atomicity (R5-R10)
