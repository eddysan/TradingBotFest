# Proposal

## Why

The repository has no OpenSpec baseline, so there is no shared statement of what the bot currently does, which behaviors are intentional, and which are suspected defects. Without that baseline, later changes cannot distinguish a deliberate behavior change from an accidental one, and the risks already present in the live trading path are invisible to reviewers.

## What Changes

- Add ten baseline capability specifications under `openspec/specs/`, written from the current working tree rather than from `HEAD`.
- Record provenance, assumptions, and known deviations in every specification. Requirements describe observed behavior; suspected defects are marked as deviations instead of being silently treated as intent.
- Add this `baseline-audit` change as the provenance record: method, scope, evidence, contradictions between documentation and code, and a consolidated risk register.
- Record what is explicitly out of scope: the unused SQLite migrations and deleted database layer, the unused TOML configs, the archived Python implementation, and the stale `add-dca-safety-assistant` proposal for a deleted prototype.
- Do not modify application source code.

## Capabilities

### New Capabilities

- `runtime-configuration`: dotenv discovery, testnet/production selection, credential resolution.
- `exchange-connectivity`: Binance USD-M REST base URLs, clock sync, signing, endpoint surface, error translation.
- `market-metadata-and-conventions`: symbol filters, rounding, formatting, distance math.
- `order-execution-and-cancellation`: order shapes, grid batches, cancellation scopes, error handling.
- `user-data-stream-and-dispatch`: listen key, WebSocket keepalive, reconnection, event routing.
- `operation-state-store`: `ops/{SYMBOL}.json` layout, accessors, writes, concurrency behavior.
- `strategy-cardiac`: CARDIAC input, sizing, entry, stop-loss, unload, take-profit.
- `strategy-load-unload-grid`: THE_LOAD_UNLOAD_GRID input, grid math, constant-risk stop, fill branches.
- `strategy-recovery-zone`: RECOVERY_ZONE entries, hedge, recovery escalation, targets, trailing stop.
- `runtime-operations`: binaries, logging, systemd service, deployment, operational continuity.

### Modified Capabilities

None. `openspec/specs/` was empty before this change.

## Impact

- **Added files**: `openspec/specs/*/spec.md` for the ten capabilities, plus `openspec/changes/baseline-audit/{proposal,design,tasks}.md` and `.openspec.yaml`.
- **Configuration**: `openspec/config.yaml` gains project context explaining that the specs are a behavioral baseline and that deviations are not approved intent.
- **Code**: none. No Rust source, config, migration, or deployment file is changed.
- **Risk**: the baseline documents unsafe current behavior but deliberately does not fix it. Readers must not confuse a documented deviation with an accepted design decision.
