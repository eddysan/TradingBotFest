# Design

## Context

See `proposal.md` for motivation. The constraints from the existing codebase that shape this design:

- `src/bin/trading_bot_fest.rs` creates `tx_ex_cmd` and drops the receiver, so `ExchangeCommands` currently goes nowhere; `exchange_service::run` is never spawned. Nothing can place an order today.
- `src/exchange_service/handlers.rs::PlaceOrder` is a `println!` stub. `websocket.rs` is a placeholder that never emits a price.
- `src/db/handlers.rs` leaves `DbCommand::PostOrder` and `GetOrder` empty; `orders` is insert-only in practice and nothing writes a fill.
- Two style camps exist: `cardiacbot` uses `f64`, DB models use `rust_decimal::Decimal`. Money math must use `Decimal`.
- `migrations/001_create_tables.sql` already has `orders` with `label`, `position_side`, `label_order`, `reduce_only`, and a `positions` table shaped after Binance's position payload. There is no trade-level table, so nothing associates an entry, a safety order and a stop with one decision.
- `binance-sdk 44.0.1` is present with `derivatives_trading_usds_futures`; `client.order_service()` is the entry point the stub's TODO names. No cargo toolchain is available in this environment, so SDK call shapes must be verified against the crate docs at implementation time.

## Goals / Non-Goals

**Goals:**

- One place owns "what is this trade's stop price", usable as a pure function with unit tests that need no network.
- The plan can be validated *before* any order is placed, so an infeasible plan costs nothing.
- A crash, `^C`, or network loss never leaves the position without a stop.
- Hedge mode is a first-class assumption, not an afterthought: identity is `(symbol, position_side)` everywhere.
- Replacing the fill source does not touch the state machine.

**Non-Goals:**

- No autonomous entries, no indicators, no take-profit leg.
- No more than one safety order per trade (no ladder, no re-anchoring).
- No portfolio-level risk, correlation, or funding-cost accounting.
- No changes to `cardiacbot`, `rest_api_service`, `trade.rs`, or the `strategies` stubs.
- No attempt at exact fill-price prediction: the stop is a trigger, and slippage remains the trader's residual risk.

## Decisions

### Risk math is closed-form, not iterative

Solving `Q·(Pa − SL) + F_in + f_t·|SL|·Q = R` directly gives:

```
LONG :  SL = (Q·Pa − R + F_in) / (Q·(1 − f_t))
SHORT:  SL = (Q·Pa + R − F_in) / (Q·(1 + f_t))
```

where `Q` = total position size, `Pa` = average entry price, `F_in` = maker fees already paid, `f_t` = taker rate, `R` = net risk. This reproduces the trader's original `distance = (R·100)/(price·qty)` when `F_in = f_t = 0` and `Q` is a single line, so the intuition behind the Python snippet is preserved exactly.

*Alternative considered:* keep the percentage-distance formulation and multiply back. Rejected: with fees in play it needs iteration to converge, and it invites the `distance` round-trip the trader's snippet performs (`distance = (price − SL)/price`), which loses precision and is only cosmetic anyway.

### Whole-position risk, and the feasibility bound it implies

`R` applies to the entire position, so averaging shrinks the price distance. For a LONG where `d = P1 − P_safety` with equal line sizes `q`:

```
room from the safety fill to the stop = R/(2q) − d/2  > 0   ⇒   d < R/q   ⇒   d/P1 < R/N
```

That is the check the assistant runs at input time. Worked example: notional 1000, `R` 10 (1%) makes any safety price 2% below entry infeasible, because the doubled position's stop that preserves 10 USDT of risk lands *above* the safety fill price and Binance rejects it with `-2021 Order would immediately trigger`. The trader would be left with a doubled position and no valid stop.

*Alternative considered:* let the stop land where it lands and only warn. Rejected: the failure mode is discovered after the money is committed. Validating up front is the whole value of an assistant.

### Stop is `STOP_MARKET` + `closePosition=true`

Chosen over `reduceOnly` with an explicit quantity for two reasons:

1. **`reduceOnly` cannot be sent in hedge mode** — Binance rejects the combination, so `closePosition` is the only primitive that closes a hedge-mode side.
2. **It removes the sizing race.** Fills are learned by polling, so up to ~1s elapses between the safety fill and the stop replacement. A `closePosition` stop always covers the current size; a fixed-quantity stop would leave the newly added half unprotected during that window, or close only part of the position.

Consequence: the stop carries no quantity, so recalculation must be *replace*, not *amend* (cancel + place a new order). `workingType=MARK_PRICE` and `priceProtect=true` guard against last-price wicks, which matter more when both sides of a symbol can be open.

*Alternative considered:* `STOP_LIMIT` with a slippage buffer. Rejected: in a fast move it goes unfilled and the position survives the "stop" — the opposite of the intent. `R` is therefore a trigger-price target, and realized loss may exceed it by slippage; the spec's fee requirement is exact only for a fill at the trigger.

### Recalculation order: place-then-cancel

New stop is accepted first, old stop cancelled second. Both are `closePosition`, so for the brief overlap both would attempt to close the same position; the exchange closes it once and the second order becomes a no-op or is rejected as would-close-nothing. A gap without a stop is impossible; a shadow order is harmless.

*Alternative considered:* cancel-then-place. Rejected: a rejected placement after a successful cancel leaves the position naked.

### Fill detection by polling, behind an event stream

A 1s ticker queries the active trades' orders and emits `FillEvent { trade_id, role, executed_qty, avg_price, status }` only when `executedQty` changes (so duplicate polls emit nothing). The session consumes the stream; a user-data websocket later becomes a second producer of the same events.

*Alternatives considered:* user-data websocket — lowest latency, but `websocket.rs` is a stub, listenKey lifecycle and stream parsing are the largest single chunk of new infrastructure, and it makes the first working version much harder to test. Manual terminal confirmation — cheapest, but contradicts "the bot manages the stop" whenever the trader is away from the keyboard. Polling keeps the change to REST, which the SDK already exposes.

### Trade state machine is explicit and durable

```
IDLE
 └─ input → validate ─fail→ reject (nothing sent)
      └─ ENTRY_PENDING      entry LIMIT resting
           ├─ filled → place stop + place safety → HEDGED
           └─ cancelled/expired → ABANDONED
 HEDGED
   ├─ safety filled → recompute → replace stop (still HEDGED)
   ├─ stop filled → CLOSED_STOPPED
   ├─ position size 0 without stop fill → CLOSED_EXTERNAL
   └─ trader cancel → CANCELLED
```

Every transition writes to SQLite before the next exchange call, so persistence is never behind an in-flight order. This also gives restart reconciliation something to read.

*Alternative considered:* derive state from the exchange on every tick instead of storing it. Rejected: it loses intent (was the safety order *meant* to exist?) and cannot distinguish a bot-placed stop from one the trader placed manually.

### Safety order is placed after the entry fills, not alongside it

If both resting orders were placed together and the entry were rejected or expired, the safety order would remain live and open a position at the safety price with nothing tagging it as an entry. Placing it on the entry fill removes that class of orphan entirely.

### Schema: a `trades` table plus role linkage on `orders`

`migrations/002_assistant.sql`:

```sql
CREATE TABLE trades (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  symbol TEXT NOT NULL,
  position_side TEXT NOT NULL,      -- LONG | SHORT
  status TEXT NOT NULL,             -- ENTRY_PENDING | HEDGED | CLOSED_STOPPED | ...
  entry_price TEXT NOT NULL,
  notional TEXT NOT NULL,
  risk TEXT NOT NULL,
  safety_price TEXT,
  avg_price TEXT NOT NULL,
  position_qty TEXT NOT NULL,
  stop_price TEXT,
  realized_pnl TEXT,
  fees_paid TEXT NOT NULL DEFAULT '0',
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE UNIQUE INDEX idx_trades_active
  ON trades(symbol, position_side)
  WHERE status IN ('ENTRY_PENDING','HEDGED');

ALTER TABLE orders ADD COLUMN trade_id INTEGER;
ALTER TABLE orders ADD COLUMN role TEXT;   -- ENTRY | SAFETY | STOP
```

The partial unique index enforces "one active trade per symbol and side" in the database rather than in a check that a race could bypass. Money columns are `TEXT` holding decimal strings, consistent with the existing `orders`/`positions` tables.

All exchange-facing values stay `Decimal`; the existing `f64` usage in `cardiacbot` is untouched and not reused.

### Terminal is a separate binary sharing the library

`src/bin/assistant.rs` runs the same channel topology the main binary should have: DB service, exchange service (with its receiver held), poller, and the session task. `src/bin/trading_bot_fest.rs` gains the exchange-service spawn and keeps its receiver, but its remaining stubs stay stubs — the assistant does not depend on Cardiac.

## Risks / Trade-offs

- **Polling latency (~1s) widens the window between a safety fill and the new stop.** → `closePosition` keeps the old stop covering the enlarged position during that window, so the exposure is a wrong *price*, not an absent stop. Mitigation: configurable interval, and the risk target is recomputed on every partial fill.
- **`R` is exact only at the trigger price; market stops slip.** → Documented in the spec; `priceProtect` reduces wick triggers. A trader wanting tighter control can lower the poll interval, which does not remove slippage.
- **Averaging in this design is shallow by construction (`d < R/N`).** → This is a property of fixed-risk averaging, not a bug, and the input check reports the maximum allowed depth instead of a cryptic exchange rejection.
- **Hedge mode means leverage changes affect both sides.** → Liquidation price is re-read per side after setting leverage, and the plan is rejected if the stop is outside it.
- **A race remains between "exchange accepted the order" and "row committed".** → Client order IDs are deterministic per trade and role, so reconciliation can find an order whose row is missing, and the spec requires reporting such orders rather than adopting them.
- **Exchange error codes and SDK call shapes are unverified in this environment (no cargo).** → First implementation task is a testnet smoke test of place/query/cancel/closePosition before any logic is built on top.
- **Testnet behaves differently from mainnet on filters and minimums.** → Symbol filters are always read from the live `exchangeInfo` of the active environment, never hardcoded.

## Migration Plan

1. Ship `migrations/002_assistant.sql`; it is purely additive, so an existing database keeps working and the old `trade.rs`/REST path is unaffected.
2. Ship with `USE_TESTNET=true` and run the full cycle (entry → stop → safety → replacement → close) on testnet.
3. Flip to mainnet only with a deliberately small notional; verification is that the stop's implied loss equals `R` within one tick plus fees.
4. **Rollback:** stop the assistant binary and cancel its orders by client order ID. Trade rows stay for audit; no existing table is altered destructively, so code rollback needs no data migration.

## Open Questions

- Exact `binance-sdk 44.0.1` signatures for `place_order` with `closePosition`, `query_order` and `cancel_order` — to be settled by compiling against the crate during the first implementation task.
- Whether fee rates should be fetched from the account's commission endpoint in addition to configuration; configuration alone is sufficient for v1, and the spec allows either.
- Whether the poller should batch symbols with Binance's multi-symbol open-orders query once more than a couple of trades exist; irrelevant at one trade per side.
