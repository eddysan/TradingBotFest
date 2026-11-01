# Tasks

## 1. Foundations

- [ ] 1.1 Verify the `binance-sdk 44.0.1` call shapes needed by this change — `place_order` with `closePosition` and `positionSide`, `query_order`, `cancel_order`, `set_leverage`, and the liquidation price field — with a throwaway example binary; verify by compiling it and recording the exact signatures in `design.md` under Open Questions
- [ ] 1.2 Add `migrations/002_assistant.sql` with the `trades` table, the partial unique index on `(symbol, position_side)` for active statuses, and the `trade_id`/`role` columns on `orders`; verify by running `cargo run --bin init_db` against a copy of an existing database and confirming old rows survive
- [ ] 1.3 Add `config/assistant.toml` with maker/taker fee rates, poll interval and working type, documented with inline comments; verify by loading it and asserting the defaults match the spec (0.02% maker, 0.05% taker, 1s interval)
- [ ] 1.4 Spawn `exchange_service::run` in `src/bin/trading_bot_fest.rs` and hold its receiver instead of dropping it; verify a command sent through the channel reaches the handler by logging a placeholder response

## 2. Risk math

- [ ] 2.1 Implement `src/assistant/risk.rs` with the fee-aware stop formula for LONG and SHORT and verify unit tests cover a single fill at 100/1000/10 giving 99.0 and 101.0 with zero fees
- [ ] 2.2 Add averaging support to the stop computation and verify a test asserts the 10@100 + 10@99.5 case yields 99.25 from combined size 20 and average 99.75
- [ ] 2.3 Implement the fee model (`F_in` from filled maker fees, taker rate on the exit) and verify a test asserts the fee-adjusted stop is further from the average than the fee-free one and that net loss equals `R` exactly
- [ ] 2.4 Implement tick rounding toward the average and step rounding down for quantity, and verify a test asserts 99.2537 becomes 99.3 at a 0.1 tick for a LONG and that loss does not exceed `R`
- [ ] 2.5 Implement the feasibility checks (`R` above round-trip fees, safety depth below `R/N`, safety direction, stop inside liquidation, minimum size) and verify each check has a test using the rejection examples from the spec
- [ ] 2.6 Add a test that the safety-depth boundary is exact — 99.5 accepted and 98.0 rejected for entry 100, notional 1000, `R` 10 — and document the bound `d/P1 < R/N` in the module rustdoc with its derivation
- [ ] 2.7 Verify `cargo test` passes with `Decimal` throughout and no `f64` in `src/assistant/risk.rs` (grep as the check)

## 3. Persistence

- [ ] 3.1 Extend `DbCommand::PostOrder` to carry every field `insert_order` needs and add a `oneshot` reply to `GetOrder`; verify the compiler accepts the new variants and the DB service replies to a query
- [ ] 3.2 Add trade repository functions over `src/db/queries.rs` (create, transition status, fetch active, attach orders) and verify tests round-trip a trade through an in-memory SQLite database
- [ ] 3.3 Enforce the one-active-trade-per-side rule and verify a test asserts the second insert for the same `(symbol, position_side)` fails while the opposite side succeeds
- [ ] 3.4 Verify a state transition is written before the following exchange call by asserting on the stored status after an injected exchange failure

## 4. Exchange execution

- [ ] 4.1 Implement real `PlaceOrder` in `src/exchange_service/handlers.rs` for LIMIT and stop orders, including `positionSide`, `closePosition`, `workingType`, `priceProtect` and `clientOrderId`; verify against testnet that a LIMIT order appears in open orders with the expected ID
- [ ] 4.2 Implement cancel-by-client-order-id and query-by-client-order-id; verify on testnet that cancelling one trade's order leaves an order with a different ID untouched
- [ ] 4.3 Apply symbol filters (step, tick, minimum quantity, minimum notional) read from the active environment's `exchangeInfo`; verify a test rejects a quantity whose rounded notional is below the minimum
- [ ] 4.4 Implement leverage setting and liquidation-price read-back per position side; verify on testnet that the returned liquidation price changes when leverage changes
- [ ] 4.5 Surface exchange rejections with code and message and leave the trade state unchanged; verify a test asserts `-2021` on stop placement leaves the previous stop in force and marks the trade as needing intervention
- [ ] 4.6 Enforce environment selection from `USE_TESTNET` with no fallback; verify the assistant refuses to start when the selected environment's credentials are absent

## 5. Fill detection

- [ ] 5.1 Implement the polling task over active trades' orders with a configurable interval; verify with a fake exchange that a fill is emitted within one interval
- [ ] 5.2 Emit `FillEvent` with role, cumulative executed quantity and average price, and emit nothing when the quantity is unchanged; verify a test asserts two identical polls yield one event
- [ ] 5.3 Handle partial fills incrementally; verify a test asserts a 30% then 100% sequence produces position sizes that follow the executed quantity
- [ ] 5.4 Add retry with full state reconciliation after failures; verify a test asserts a fill is still detected after three failed polls
- [ ] 5.5 Implement startup reconciliation from stored trades plus live exchange state; verify tests cover "entry filled while down", "stop filled while down", and "recorded order no longer known"
- [ ] 5.6 Report orders carrying an assistant client ID with no matching trade without adopting them; verify a test asserts the orphan is reported and no trade row changes

## 6. Trade session and terminal

- [ ] 6.1 Implement the state machine in `src/assistant/state.rs` with the transitions from `design.md`; verify tests drive IDLE → ENTRY_PENDING → HEDGED → CLOSED_STOPPED against a fake exchange and fake fill source
- [ ] 6.2 Place the safety order only on entry fill and never before; verify a test asserts no safety submission occurs while the entry is pending
- [ ] 6.3 Replace the stop after a safety fill using place-then-cancel and keep risk equal to `R`; verify a test asserts the new stop is accepted before the old is cancelled and that the reported risk is unchanged
- [ ] 6.4 Handle stop close, external close and cancellation, including cancelling a resting safety order when the stop fills; verify tests for each path assert no order remains and the trade's terminal status is correct
- [ ] 6.5 Size risk from executed quantity on partial fills; verify a test asserts a 40%-filled safety yields a stop for the position that actually exists
- [ ] 6.6 Build `src/bin/assistant.rs` with prompts for symbol, side, price, notional, risk and optional safety price, plus a pre-submission confirmation showing resolved symbol, quantity and stop; verify manually that a blank safety price creates a trade with no averaging order
- [ ] 6.7 Implement a status command reporting state, average price, size, stop and remaining risk; verify manually in both the pending-entry and hedged states
- [ ] 6.8 Verify a duplicate attempt on the same symbol and side is refused while the opposite side is accepted, using the running binary

## 7. Integration verification

- [ ] 7.1 Run the full cycle on testnet with `USE_TESTNET=true` — entry, stop placement, safety fill, stop replacement, stop close — and verify the recorded realised loss equals `R` within one tick plus fees
- [ ] 7.2 Verify recovery by killing the assistant mid-trade at each state and confirming reconciliation places or preserves a stop and does not duplicate orders
- [ ] 7.3 Verify the cancellation path on testnet with two opposite-side trades open and confirm only one side's orders are cancelled
- [ ] 7.4 Review `proposal.md`, `design.md` and the four specs against what was built and record any drift as follow-up changes rather than silent edits

## Workflow follow-up

- Archive the change once the integration checks pass and the trader has reviewed the realised-risk results.
