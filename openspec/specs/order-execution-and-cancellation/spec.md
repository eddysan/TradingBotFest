# Order Execution and Cancellation Specification

## Purpose

Defines the order shapes the bot sends, how batches of grid orders are posted, which scopes can be cancelled, and how exchange rejections during placement or cancellation are reported to callers.

## Requirements

### Requirement: Limit order shape
For entry and grid lines the system SHALL post `LIMIT` orders with `GTC`, the line's `side` and `position_side`, and its price and quantity. A line whose quantity is missing or exactly zero SHALL be logged and skipped without contacting the exchange.

#### Scenario: Normal limit line
- **WHEN** a line has a non-zero quantity, a side, a position side, and a price
- **THEN** a `LIMIT` `GTC` order is posted for that symbol

#### Scenario: Zero quantity line
- **WHEN** a line's quantity is zero or absent
- **THEN** no order is posted and the skip is logged

### Requirement: Close-position protective orders
Take-profit and stop-loss orders SHALL be posted as `TAKE_PROFIT_MARKET` and `STOP_MARKET` respectively, with `closePosition=true`, the line's stop price, and no explicit quantity.

#### Scenario: Stop-loss placement
- **WHEN** a stop-loss line is posted
- **THEN** the request uses `STOP_MARKET`, `closePosition=true`, and the line price as `stopPrice`

#### Scenario: Take-profit placement
- **WHEN** a take-profit line is posted
- **THEN** the request uses `TAKE_PROFIT_MARKET`, `closePosition=true`, and the line price as `stopPrice`

### Requirement: Hedge and trailing-stop shapes
Hedge orders SHALL be `STOP_MARKET` with `GTC`, an explicit quantity, a stop price, and `closePosition=false`. Trailing-stop orders SHALL be `TRAILING_STOP_MARKET` with `GTC`, an explicit quantity, an activation price, a callback rate, and `closePosition=false`.

#### Scenario: Hedge order
- **WHEN** a recovery-zone hedge line is posted
- **THEN** the order is a quantity-bearing `STOP_MARKET` that does not close the whole position

#### Scenario: Trailing stop
- **WHEN** a trailing stop is posted
- **THEN** the request carries `activationPrice`, `callbackRate`, and the hedge quantity

### Requirement: Grid batch posting
The system SHALL post only grid lines whose status is `NEW`, SHALL allow at most ten order placements in flight at once, SHALL continue after individual failures, and SHALL return success for the batch after logging every failure.

#### Scenario: Mixed grid statuses
- **WHEN** a grid contains lines with `NEW` and `FILLED` statuses
- **THEN** only the `NEW` lines are submitted

#### Scenario: One grid line rejected
- **WHEN** one line in a ten-line batch is rejected by the exchange
- **THEN** the remaining lines are still attempted and the batch call returns success after logging the rejection

### Requirement: Placement errors are logged and absorbed
When an individual order placement fails, the system SHALL log the exchange error and return success to its caller. Binance code `-2021` SHALL be logged with the `TRIGGERED` label; all other codes SHALL be logged as API errors.

#### Scenario: Order would immediately trigger
- **WHEN** the exchange rejects a protective order with code `-2021`
- **THEN** the event is logged as `TRIGGERED` and the caller continues as if the placement completed

#### Scenario: Any other rejection
- **WHEN** the exchange rejects an order for insufficient margin or an invalid parameter
- **THEN** the error is logged and the caller still receives success

### Requirement: Cancel all orders for a symbol
The system SHALL support cancelling every open order for a symbol via the exchange's cancel-all endpoint. A response indicating that no orders exist SHALL be treated as success; any other error SHALL be logged and returned.

#### Scenario: Open orders exist
- **WHEN** cancel-all succeeds
- **THEN** the caller receives success and the cancellation is logged

#### Scenario: Nothing to cancel
- **WHEN** the exchange reports no orders to cancel
- **THEN** the caller receives success

#### Scenario: Cancel-all fails for another reason
- **WHEN** the exchange returns an unrelated error
- **THEN** the error is logged and returned to the caller

### Requirement: Cancel by position side
The system SHALL list open orders for the symbol, keep only those whose `positionSide` matches the requested side, cancel each in parallel with at most ten in flight, and return success even when individual cancellations fail.

#### Scenario: Both sides have open orders
- **WHEN** cancellation is requested for `LONG`
- **THEN** only `LONG` orders are cancelled and `SHORT` orders remain

#### Scenario: No matching orders
- **WHEN** no open order matches the requested side
- **THEN** the call logs that there is nothing to cancel and returns success

### Requirement: Cancel by operation kind
The system SHALL support cancelling only the orders belonging to one operation, identified by the pair of order type, order side, and `closePosition` value. The supported kinds SHALL be `GRID`, `UNLOAD`, `TAKE_PROFIT`, `STOP_LOSS`, `HEDGE`, and `TRAILING_STOP_MARKET`; any other kind SHALL fail.

#### Scenario: Grid cancellation
- **WHEN** `GRID` is cleaned for a `LONG` position
- **THEN** only open `LIMIT` `BUY` orders on `LONG` with `closePosition=false` are cancelled

#### Scenario: Stop-loss cancellation
- **WHEN** `STOP_LOSS` is cleaned for a `LONG` position
- **THEN** only `STOP_MARKET` `SELL` orders on `LONG` with `closePosition=true` are cancelled

#### Scenario: Unknown operation
- **WHEN** an unsupported operation name is supplied
- **THEN** the call fails with an unknown-operation error

### Requirement: Cancellation errors are logged per order
When a single-order cancellation fails, the system SHALL log code `-2011` as an already-cancelled or missing order and any other code as an error, then continue with the remaining cancellations. The per-operation call SHALL return success.

#### Scenario: Order already gone
- **WHEN** the exchange reports `-2011` for one order
- **THEN** a warning is logged and the remaining orders are still cancelled

## Provenance

- `src/orders.rs` defines every order shape, the grid batch, all cancellation scopes, and the operation filter.
- `src/exchange/client.rs` maps `NewOrder` fields to Binance form parameters.
- Unit tests in `src/orders.rs` cover the operation filter.

## Assumptions

- Hedge mode is enabled, so every order carries `positionSide`.
- Protective orders intentionally close the whole position rather than a fixed quantity.

## Known deviations

- Placement failures are converted to success. Callers cannot distinguish a posted protection order from a rejected one, and `MIGRATION.md`'s claim that errors are not swallowed is contradicted by this behavior.
- No `clientOrderId` or other idempotency key is sent, so a retried or duplicated call can place duplicate orders.
- Cancel-all removes every order for the symbol, including manually placed orders and the opposite position side. Strategy call sites use it when closing a recovery-zone position.
- Batch and per-order cancellation always return success after logging, so a caller cannot detect a partially cancelled set.
- Orders are not checked against `stepSize`, `minQty`, `maxQty`, or `minNotional` before submission; the exchange is the only validator.
- `post_hedge_order` and `post_trailing_stop_order` send `timeInForce=GTC` on order types where the exchange may ignore or reject it.
- `post_limit_order` logs the requested price and quantity before the exchange confirms the order; the log line says `POSTED` even when the response later proves otherwise.
