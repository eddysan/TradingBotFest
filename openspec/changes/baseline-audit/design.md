# Design

## Context

This change establishes a baseline, not a target architecture. The working tree is mid-migration and uncommitted, so the audit targets the files that are present now rather than `HEAD`. The original Python implementation is archived under `assets/old_python/` and is not run; it is used only to confirm which Rust behaviors were inherited, intentionally changed, or lost.

The runtime is a set of Rust binaries that talk directly to Binance USDS-M futures. There is no database in the running path, no service layer, and no reconciliation loop. State lives in `ops/{SYMBOL}.json`, which is also the handover format between the Python and Rust versions. The systemd unit runs only the user-data listener; strategy binaries are interactive setup tools.

## Goals / Non-Goals

**Goals:**

- State what each capability does today, with enough precision that a future change can cite a requirement.
- Separate verified behavior from assumptions and from suspected defects.
- Preserve the Python-compatible state and order conventions as observed, including behavior that looks wrong.
- Give reviewers one consolidated risk register instead of scattering findings across code comments.

**Non-Goals:**

- No source, configuration, schema, or deployment changes.
- No decision that a documented deviation should be fixed, accepted, or removed.
- No attempt to reconstruct intended business rules that the code does not express.
- No coverage of deleted modules, unused migrations, or the archived Python bot as live behavior.

## Method

1. Read every Rust source file, configuration template, migration, service unit, deployment script, README, and `MIGRATION.md`.
2. Run `cargo test` to confirm the current unit-test baseline. Result: 28 passed, 0 failed. `cargo clippy` was unavailable because the component is not installed.
3. Trace each binary from prompt to order placement and each WebSocket event from frame to strategy branch.
4. Compare the Rust code with `MIGRATION.md` and the archived Python only where the Rust comments claim compatibility or an intentional fix.
5. Record each statement in one of three classes:
   - **Verified**: directly visible in code and, where available, covered by a unit test.
   - **Assumption**: required for the behavior to make sense but not enforced or documented by the code.
   - **Undocumented / deviation**: behavior that is real but unstated, contradictory, or evidently defective.
6. Write the capability specs first, then this change as the audit trail.

## Verification boundary

- The 28 unit tests exercise pure calculations: rounding, distance, filter parsing, operation filtering, state accessors, strategy math, and symbol locks.
- Nothing is tested against a live or mocked exchange. Order shapes, signing, WebSocket behavior, restart behavior, and exchange error handling are verified by reading code, not by execution.
- The image `trading bot fest flow process.png` is not referenced by code and could not be read during the audit. It is not evidence for any requirement.

## Capability boundaries

| Capability | Owns | Does not own |
| --- | --- | --- |
| `runtime-configuration` | dotenv files, environment flag, credential pair | signing, endpoint behavior |
| `exchange-connectivity` | HTTP client, signing, REST surface, error translation | symbol filters, order shapes |
| `market-metadata-and-conventions` | filters, rounding, formatting, distance | order placement |
| `order-execution-and-cancellation` | order shapes, batches, cancellation scopes | strategy decisions, fill classification |
| `user-data-stream-and-dispatch` | listen key, socket, reconnect, routing | what a handler does with a fill |
| `operation-state-store` | file format, accessors, write semantics | per-strategy schema and merge policy |
| `strategy-*` | inputs, calculations, order choices, fill branches | transport and storage primitives |
| `runtime-operations` | binaries, logging, service, deployment | trading logic |

## Defect treatment

A suspected defect is documented in two places: the current behavior is stated as a normative requirement, and the same spec carries a `Known deviations` entry explaining why the behavior is risky or contradictory. This keeps the baseline executable as a description of the system while preventing a future reader from mistaking a bug for an approved rule.

Remediation is deliberately excluded. Any fix should be proposed as a separate change that cites the affected requirement and the deviation it removes.

## Contradictions found

1. **`MIGRATION.md` says errors are not swallowed.** `src/orders.rs::report_api_error` logs every placement failure and returns `Ok(())`. Strategy call sites therefore continue and save state as if the order succeeded. This is the most consequential documentation/code contradiction in the repository.
2. **`MIGRATION.md` describes the stop-loss and take-profit classification fix as restoring intended behavior.** That is plausible, but it means the current Rust mapping is not a Python-compatible baseline; it is a deliberate divergence.
3. **`MIGRATION.md` says the Rust state is Python-compatible.** File shape is compatible, but merge behavior is not uniform: CARDIAC and THE_LOAD_UNLOAD_GRID merge only their own side when the existing strategy matches, while RECOVERY_ZONE always replaces the entire document.
4. **`config/recoveryzone.json` ships `reduce_hedge: 0`.** The recovery line then targets the opposite hedge price itself, which makes the recovery order likely to be rejected or immediately triggered. The shipped default contradicts the purpose of a recovery line.
5. **`stop_loss_protection` and `protection_distance` exist in RECOVERY_ZONE but are never used.** The configuration surface implies a protection feature that the runtime does not provide.
6. **The README presents strategy binaries as normal usage without stating they are one-shot setup tools.** A reader can infer that the strategy runs continuously, but only `bot` is long-running.

## Out of scope

- `migrations/001_create_tables.sql`, the deleted `src/db/` layer, and the deleted `init_db` binary. No running path opens a database.
- `config/*.toml`. The bot reads only `config/cardiac.json`, `config/theloadunload.json`, and `config/recoveryzone.json`.
- `assets/old_python/`. Archived reference only; it is not run and its defects are not requirements.
- `openspec/changes/add-dca-safety-assistant/`. It targets a deleted Rust prototype (`src/bin/trading_bot_fest.rs`, `src/exchange_service/`, `src/db/`) and is not current behavior. It is left untouched and should be treated as superseded by this baseline.
- The unread flow image.
- Testnet or production execution. No live exchange call was made during the audit.

## Risk register

Severity reflects consequence for a live account, not likelihood alone.

| ID | Severity | Area | Finding | Consequence |
| --- | --- | --- | --- | --- |
| R1 | Critical | Configuration | Production is selected whenever `TESTNET` is absent, false, empty, or misspelled. | A missing flag silently trades real funds. |
| R2 | Critical | Order execution | Placement failures are logged and returned as success. | A position can be left without a stop while state records success. |
| R3 | Critical | Runtime operations | No startup reconciliation or replay of missed fills. | Restart or disconnect can leave positions and orders unmanaged. |
| R4 | Critical | User-data stream | Only `FILLED` events are acted on; partial fills are ignored. | A partially filled entry has no protection and stale state. |
| R5 | High | Order execution | No `clientOrderId` or idempotency key. | Retries or duplicate runs can create duplicate orders. |
| R6 | High | Order execution | Cancel-all removes every order for a symbol, including manual and opposite-side orders. | Unrelated protection can be removed. |
| R7 | High | Market metadata | Step size, minimum quantity, maximum quantity, and minimum notional are parsed but never enforced. | Orders are rejected by the exchange after the strategy assumes success. |
| R8 | High | Market metadata | Quantity is rounded by precision, not floored to step size. | Symbols whose precision and step disagree receive invalid quantities. |
| R9 | High | Market metadata | `tick_digits` is wrong for tick sizes that are not powers of ten. | Prices can round to the wrong number of decimals. |
| R10 | High | State store | Writes are non-atomic and unlocked. | A crash or concurrent writer can truncate or silently overwrite state. |
| R11 | High | Strategy CARDIAC | Unload quantity is `current - entry` with no lower bound. | A partial entry fill can produce a negative order quantity. |
| R12 | High | Strategy RECOVERY_ZONE | Shipped `reduce_hedge: 0` makes the recovery target the opposite hedge price. | Recovery order is likely rejected or immediately triggered. |
| R13 | High | Strategy RECOVERY_ZONE | Risk is escalated before the `max_risk` check and never reset or capped. | Recovery sizing can drift outside the intended risk ceiling. |
| R14 | Medium | Exchange connectivity | No retry, rate-limit handling, or request-weight accounting. | Transient errors are surfaced immediately; bursts can hit limits. |
| R15 | Medium | Exchange connectivity | Server-time offset is computed once at startup. | Long-running processes can drift outside `recvWindow`. |
| R16 | Medium | User-data stream | Retry delay is not reset after a successful connection. | A later disconnect can wait up to two minutes before reconnecting. |
| R17 | Medium | User-data stream | Handler tasks are spawned and not joined on shutdown. | In-flight fills can be lost during restart. |
| R18 | Medium | Order execution | Batch placement and per-order cancellation always return success. | Callers cannot detect partial failure. |
| R19 | Medium | Strategy calculations | All money and quantity math uses `f64`. | Rounding and comparison errors, including false hedge imbalance. |
| R20 | Medium | Strategy CARDIAC | Stop-loss amount is not validated against position notional. | Stop can land at or through zero, or on the wrong side. |
| R21 | Medium | Strategy LOAD_UNLOAD | Grid generation may stop early when the stop crosses the next line. | Fewer averaging levels than expected, without a count report. |
| R22 | Medium | Strategy RECOVERY_ZONE | `generate_stop_loss_protection` is dead code and `protection_distance` is inert. | Operators can believe a protection feature exists when it does not. |
| R23 | Medium | Runtime operations | `update.sh` hard-resets the production checkout. | Local fixes, including credentials changes, are discarded on deploy. |
| R24 | Medium | Runtime operations | Deployment restarts production with no test or validation gate. | A broken build or regression reaches the live account automatically. |
| R25 | Medium | Runtime operations | No alerting or health check; `Restart=always` only restarts the process. | An unprotected position can persist unnoticed. |
| R26 | Low | Runtime operations | Single append-only log with no rotation or retention. | Disk growth and loss of older evidence. |
| R27 | Low | State store | No schema validation or typed status enum. | Missing keys fail late, potentially after orders are placed. |
| R28 | Low | Documentation | `MIGRATION.md` and the README overstate error propagation and operating model. | Reviewers trust behavior that the code does not provide. |
| R29 | Low | Dead artifacts | Unused migrations, TOML configs, and the stale DCA change remain in the tree. | New contributors can mistake them for live components. |

## Recommended follow-up sequence

1. Make environment selection explicit and fail closed when the flag is missing or unrecognized (R1).
2. Stop absorbing placement errors; return them and mark the position as requiring intervention (R2).
3. Add startup reconciliation and a fill/event recovery path (R3, R4).
4. Add idempotency keys and narrow cancellation scopes (R5, R6).
5. Enforce symbol filters before submission and fix tick/step handling (R7-R9).
6. Make state writes atomic and single-writer, then address strategy math and recovery defaults (R10-R13).
7. Add observability and deployment gates (R23-R26).

These are proposals, not part of this baseline change.
