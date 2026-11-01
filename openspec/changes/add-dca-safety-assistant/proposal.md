# Proposal

## Why

The bot can currently take a manual entry order and then stops: `ExchangeCommands::PlaceOrder` only prints (`src/exchange_service/handlers.rs`), the exchange service is never spawned and its receiver is dropped (`src/bin/trading_bot_fest.rs`), and nothing observes a fill or manages a stop. The result is that a manual position is left with either no stop-loss or a stop the human has to babysit by hand.

The trader wants an assistant, not an autonomous strategy: they type the trade, the bot owns the risk mechanics from that point — placing the entry, deriving a stop whose loss equals the risk amount they typed, adding one averaging (safety) order at a price they choose, and replacing the stop after that fill while keeping total risk unchanged.

## What Changes

- New `assistant` module with an explicit trade state machine (`IDLE → ENTRY_PENDING → HEDGED → closed`) that persists every transition to SQLite, replacing the current fire-and-forget entry path for this workflow.
- New terminal binary that collects `symbol`, `side`, `price`, `notional (USDT)`, `risk (USDT)` and an optional `safety_price`, then reports state and PnL as the trade progresses.
- Real exchange order execution: place LIMIT entry, place LIMIT safety order, place `STOP_MARKET` stop with `closePosition=true`, cancel, and query by `clientOrderId`, all with `positionSide=LONG|SHORT` for hedge mode. Leverage is set and the liquidation price checked before the entry.
- Fill detection by polling open orders on a 1s ticker, emitting a `FillEvent` that the state machine consumes; the event source is an interface so a user-data websocket can replace polling later without touching the state machine.
- Risk math as pure, unit-testable functions over `Decimal`: stop price such that `|Pa − SL|·Q + fees = R` for the whole position, plus input-time feasibility validation that rejects trades the math cannot honour (risk below round-trip fees, safety depth at or beyond `R/N`, stop beyond liquidation, below `MIN_NOTIONAL`).
- Migration `002` adding a `trades` table and `trade_id`/`role`/`client_order_id` linkage on `orders`, since the current `orders` table cannot express which order is the entry, the safety order, or the stop for a given trade.
- Startup reconciliation: unfinished trades are reloaded from SQLite and re-queried from the exchange before polling resumes.
- **No change** to `src/cardiacbot/*`, `src/rest_api_service/*`, the REST entry path, or the strategies stubs. The assistant is a separate path and `trade.rs` keeps working as-is.

## Capabilities

### New Capabilities

- `position-risk-management`: how the stop price is derived from the risk amount for the whole position, the fee and slippage model, and the validation rules that reject a trade whose requested risk is unachievable.
- `assisted-trade-session`: the trade lifecycle exposed to the trader — terminal input, state transitions, one active trade per `(symbol, position_side)`, safety-order eligibility, cancellation, close handling, and persistence of the session.
- `exchange-order-execution`: how the bot talks to Binance USDS-M futures in hedge mode — order shapes for entry, safety and stop, leverage and liquidation checks, symbol filter rounding, and cancellation scoped to a trade's own orders.
- `fill-detection`: how the bot learns that an entry, safety order or stop has filled or partially filled, including the polling contract, the pluggable event source, and restart reconciliation against the exchange.

### Modified Capabilities

None. `openspec/specs/` is currently empty; no existing requirement changes.

## Impact

- **New code**: `src/assistant/{mod,state,risk}.rs`, `src/bin/assistant.rs`, and exchange-service additions (`order_service` calls, `poll_fills`, `set_leverage`).
- **Modified code**: `src/core/commands.rs` (`DbCommand::PostOrder` gains the fields `insert_order` needs, `GetOrder` gains a `oneshot` reply, new order-status and trade commands), `src/core/common.rs` (prompt helpers for notional, risk, optional safety price), `src/bin/trading_bot_fest.rs` (actually spawn the exchange service and hold its receiver), `src/exchange_service/{mod,handlers,helpers}.rs`, `src/db/{handlers,queries,models}.rs`.
- **Schema**: new `migrations/002_assistant.sql` (new `trades` table, additive columns on `orders`).
- **New config**: `config/assistant.toml` for fee rates, poll interval, and working type.
- **Dependencies**: none added; `binance-sdk 44.0.1` already exposes `derivatives_trading_usds_futures`. `rust_decimal` is already used by the DB models and will be used for all money math — the assistant will not use `f64`.
- **Risk**: the bot places real orders when `USE_TESTNET=false`. Testnet support is required to exercise every path before mainnet; no mainnet run should be attempted without it.
- **Out of scope**: autonomous entries, indicator-driven signals, take-profit orders, more than one safety level, position sizing by leverage, and any change to the Cardiac strategy.
