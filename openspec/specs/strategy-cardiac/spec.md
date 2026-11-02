# CARDIAC Strategy Specification

## Purpose

Defines the CARDIAC workflow: operator input, risk-based entry sizing, one entry order, and the stop-loss, unload, and take-profit orders regenerated after a fill.

## Requirements

### Requirement: Interactive input and state persistence
The system SHALL prompt for a base symbol, append `USDT`, prompt for `LONG` or `SHORT` with `LONG` as the blank default, load `config/cardiac.json` as the template, and persist the resulting document to `ops/{SYMBOL}.json`.

#### Scenario: New long trade
- **WHEN** the operator enters `BTC` and leaves the side blank
- **THEN** the symbol is `BTCUSDT`, the side is `LONG`, and the state is written to `ops/BTCUSDT.json`

#### Scenario: Short trade
- **WHEN** the operator enters `ETH` and `SHORT`
- **THEN** the symbol is `ETHUSDT` and the SHORT section is configured

### Requirement: Existing position adoption
Before prompting for prices, the system SHALL query position risk for the symbol. When a non-zero position exists on the requested side, it SHALL write the exchange entry price and absolute quantity into that side's `entry_line` and mark its status `FILLED`.

#### Scenario: Position already open
- **WHEN** `BTCUSDT` has a `LONG` position of `0.5` at `100`
- **THEN** `entry_line.price` is `100`, `entry_line.quantity` is `0.5`, and `entry_line.status` is `FILLED`

#### Scenario: No matching position
- **WHEN** no non-zero position exists on the requested side
- **THEN** the status remains not filled and the operator is prompted for an entry price

### Requirement: Risk-based entry sizing
The system SHALL read the current USDT wallet balance, multiply it by the configured risk percentage divided by 100, round the result to two decimals, and store it as the risk amount. For a new entry it SHALL suggest quantity as risk amount divided by entry price rounded to the symbol quantity precision, and SHALL accept an operator override.

#### Scenario: Suggested quantity
- **WHEN** the wallet holds 1000 USDT, risk is 10 percent, the entry price is 100, and quantity precision is 3
- **THEN** the suggested quantity is `1.000`

#### Scenario: Quantity override
- **WHEN** the operator enters a different quantity at the prompt
- **THEN** the entered quantity is stored instead of the suggestion

### Requirement: Entry placement
For a new entry the system SHALL post the entry line as a `LIMIT` `GTC` order on the configured position side and save state after the call. When the adopted position is already filled, it SHALL skip entry placement and immediately run fill handling.

#### Scenario: New entry
- **WHEN** the entry line status is `NEW`
- **THEN** a limit entry order is posted and the state file is saved

#### Scenario: Adopted position
- **WHEN** the entry line status is `FILLED`
- **THEN** no entry order is posted and protection handling runs immediately

### Requirement: Fill handling
On an order event with status `FILLED`, the system SHALL cancel every open order for the event's position side, refresh the current position from the exchange, and then regenerate and post each enabled protection line: stop loss, unload, and take profit. When the current quantity is zero, it SHALL post no protection orders.

#### Scenario: Entry fills
- **WHEN** the entry order reaches `FILLED`
- **THEN** existing orders on that side are cancelled and the enabled protection orders are recreated from the current position

#### Scenario: Position already closed
- **WHEN** the refreshed current quantity is zero
- **THEN** no stop-loss, unload, or take-profit order is posted

#### Scenario: Non-filled update
- **WHEN** an order event has any status other than `FILLED`
- **THEN** the handler does nothing

### Requirement: Stop-loss calculation
The system SHALL compute stop distance as `stop_loss_amount * 100 / (current_price * current_quantity)`. For a LONG it SHALL place the stop below the current price; for a SHORT it SHALL place it above. The stop price SHALL be rounded to the tick size, and the stored fractional distance SHALL be the absolute price difference divided by the current price, rounded to four decimals.

#### Scenario: Long stop
- **WHEN** price is 100, quantity is 1, and stop-loss amount is 10
- **THEN** the distance is 10 percent and the stop price is `90.0`

#### Scenario: Short stop
- **WHEN** price is 100, quantity is 1, and stop-loss amount is 10 on a SHORT
- **THEN** the stop price is `110.0`

#### Scenario: Zero price or quantity
- **WHEN** the current price or quantity is zero
- **THEN** stop generation fails instead of dividing by zero

### Requirement: Take-profit calculation
The system SHALL compute the take-profit price from the current price and the configured percentage distance, above for a LONG and below for a SHORT, rounded to the tick size.

#### Scenario: Long take profit
- **WHEN** the current price is 100 and the configured distance is 1 percent
- **THEN** the take-profit price is `101.0`

#### Scenario: Short take profit
- **WHEN** the current price is 100 and the configured distance is 1 percent on a SHORT
- **THEN** the take-profit price is `99.0`

### Requirement: Unload calculation
The system SHALL compute the unload price from the current price and the configured percentage distance, above for a LONG and below for a SHORT, rounded to the tick size. It SHALL compute unload quantity as current quantity minus entry quantity, rounded to the quantity precision.

#### Scenario: No remaining excess
- **WHEN** current quantity equals entry quantity
- **THEN** the unload quantity is zero and the limit order posting path skips it

#### Scenario: Excess after averaging
- **WHEN** current quantity is larger than entry quantity
- **THEN** the unload quantity is the difference

## Provenance

- `src/strategies/cardiac.rs` implements input, risk sizing, adoption, entry, protection generation, and fill handling.
- `src/bin/cardiac.rs` wires the interactive binary to the strategy.
- `config/cardiac.json` is the template and `src/orders.rs` provides the order shapes.
- Unit tests cover LONG and SHORT stop, take-profit, and unload calculations.

## Assumptions

- The operator is available to answer prompts for a new trade; the service only handles fills afterward.
- Hedge mode is enabled and a position side is always `LONG` or `SHORT`.
- The risk percentage in `config/cardiac.json` expresses the fraction of wallet balance committed to the entry.

## Known deviations

- Only `FILLED` order events are handled. A partial entry fill does not refresh state or place protection, leaving the filled part unprotected.
- The unload quantity is `current - entry` with no lower bound. If a partial entry fill leaves current below entry, the computed quantity is negative and is sent to the exchange.
- Take profit and unload are anchored to the exchange's current entry price after each fill, not to the original trade thesis, so a later refresh can move the targets.
- The stop-loss amount is accepted without checking that it is below the position notional. A value at or above notional produces a stop at or through zero, or on the wrong side of the market.
- An adopted position bypasses the entry prompt but still prompts for stop-loss amount; the immediate protection pass also cancels every open order on that side, including manually placed orders.
- If protecting a position fails, the order-placement layer logs the error and returns success, so the state is still saved as if protection succeeded.
- `ops/{SYMBOL}.json` is merged only when the existing file already belongs to `CARDIAC`; otherwise the new CARDIAC document replaces the whole file.
