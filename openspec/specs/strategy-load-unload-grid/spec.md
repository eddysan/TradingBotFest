# THE_LOAD_UNLOAD_GRID Strategy Specification

## Purpose

Defines the load/unload averaging grid: operator input, geometric grid generation, constant-risk stop-loss recalculation, initial order placement, and the state transitions driven by grid, unload, stop-loss, and take-profit fills.

## Requirements

### Requirement: Interactive input and persistence
The system SHALL prompt for a base symbol, append `USDT`, prompt for `LONG` or `SHORT` with `LONG` as the blank default, load `config/theloadunload.json`, store the symbol's exchange filters, and persist the document to `ops/{SYMBOL}.json`.

#### Scenario: New grid
- **WHEN** the operator enters `BTC` and leaves the side blank
- **THEN** a `LONG` grid for `BTCUSDT` is prepared with the symbol's tick and step metadata

### Requirement: Existing position adoption
When a non-zero position exists on the requested side, the system SHALL write the exchange entry price, absolute quantity, and cost into both `current_line` and `entry_line`, and mark both statuses `FILLED`.

#### Scenario: Grid takes over a position
- **WHEN** a `LONG` position of `1` at `100` exists
- **THEN** both current and entry lines contain price `100`, quantity `1`, cost `100.00`, and status `FILLED`

### Requirement: Risk and grid inputs
The system SHALL compute risk amount as wallet balance multiplied by the configured percentage divided by 100, rounded to two decimals. For a new entry it SHALL prompt for entry price and entry notional in USDT, derive quantity as notional divided by price at the quantity precision, and reject a non-positive entry price. It SHALL then prompt for grid distance, quantity increment percentage, and stop-loss amount, each with the configured value as the default.

#### Scenario: Default new entry
- **WHEN** the risk amount is 100 USDT and the operator accepts the default entry notional
- **THEN** the entry quantity is `100 / entry_price` rounded to the quantity precision

#### Scenario: Zero entry price
- **WHEN** the operator supplies an entry price of zero
- **THEN** the binary fails before any order is posted

### Requirement: Grid generation
The system SHALL clear the existing body, seed the average line from the current line, and repeatedly add a line on the averaging side at a price one grid distance away and a quantity multiplied by one plus the increment percentage. Each iteration SHALL update the weighted average price and quantity. The loop SHALL stop when the next price would cross the recalculated stop price, when a value becomes non-finite, or after 10,000 generated lines.

#### Scenario: Long grid
- **WHEN** the current price is 100, grid distance is 2 percent, and increment is 40 percent
- **THEN** the first body line is at `98.0`, subsequent lines step down, and every body line is below 100

#### Scenario: Short grid
- **WHEN** a SHORT grid starts at 100 with a 2 percent distance
- **THEN** the first body line is at `102.0` and subsequent lines step up

#### Scenario: Zero grid distance
- **WHEN** the configured grid distance is zero or negative
- **THEN** generation fails instead of looping forever

#### Scenario: Runaway grid
- **WHEN** more than 10,000 lines would be generated
- **THEN** generation stops with a warning and the lines produced so far are kept

### Requirement: Constant-risk stop loss
At every grid iteration the system SHALL recompute stop distance as `stop_loss_amount * 100 / (average_price * average_quantity)` and move the stop to that distance from the average, below for a LONG and above for a SHORT. The stop loss quantity and cost SHALL accumulate the quantities and notional of every generated line, so total risk remains approximately constant as the average moves.

#### Scenario: Averaging widens safety
- **WHEN** the average price moves toward the grid as quantities are added
- **THEN** the stop price is recalculated from the new average and the configured stop-loss amount

#### Scenario: Long stop direction
- **WHEN** a LONG grid generates a line above the current stop price
- **THEN** generation continues and the stop is recalculated below the new average

### Requirement: Initial order placement
The system SHALL generate the grid, post the entry line only when it is not already `FILLED`, post every body line whose status is `NEW`, post the stop loss, and post the take profit when enabled.

#### Scenario: Fresh grid
- **WHEN** the entry is `NEW`
- **THEN** the entry, grid body, stop loss, and enabled take profit are all submitted

#### Scenario: Adopted grid
- **WHEN** the entry is `FILLED`
- **THEN** the entry order is skipped while body and protection orders are submitted

### Requirement: Fill classification
The system SHALL classify a filled order as `TAKE_PROFIT` for `TAKE_PROFIT_MARKET`, `STOP_LOSS` for `STOP_MARKET`, `GRID` for a `LIMIT` order in the position's opening direction, and `UNLOAD` for a `LIMIT` order in the closing direction. Unrecognized types SHALL produce no classification.

#### Scenario: Averaging fill
- **WHEN** a `LONG` limit `BUY` fills
- **THEN** it is classified as `GRID`

#### Scenario: Unload fill
- **WHEN** a `LONG` limit `SELL` fills
- **THEN** it is classified as `UNLOAD`

#### Scenario: Protective fill
- **WHEN** a `STOP_MARKET` fill arrives
- **THEN** it is classified as `STOP_LOSS`

### Requirement: Grid fill handling
On a `GRID` fill the system SHALL refresh the current position, and when unload is enabled SHALL cancel the existing unload orders, regenerate the unload line, and post it. When take profit is enabled it SHALL cancel the existing take-profit orders, regenerate the take-profit line, and post it.

#### Scenario: Average-down completes
- **WHEN** a grid line fills
- **THEN** the unload and take-profit orders are replaced using the refreshed position

#### Scenario: Disabled branches
- **WHEN** the unload or take-profit line is disabled
- **THEN** that branch is skipped

### Requirement: Unload fill handling
On an `UNLOAD` fill the system SHALL cancel every open order on the position side, refresh the current position, regenerate the grid, and post the stop loss, body lines, and enabled take profit.

#### Scenario: Partial exit fills
- **WHEN** an unload order fills
- **THEN** the old protection and grid orders are cancelled, the position is refreshed, and a new grid sized to the remaining position is posted

### Requirement: Terminal protective fills
On a `STOP_LOSS` or `TAKE_PROFIT` fill the system SHALL cancel every open order on the position side. It SHALL not generate a new grid.

#### Scenario: Stop loss fills
- **WHEN** the stop-loss order fills
- **THEN** all remaining orders on that position side are cancelled

## Provenance

- `src/strategies/load_unload.rs` implements input, adoption, grid generation, stop recalculation, placement, classification, and fill branches.
- `src/bin/load_unload.rs` wires the interactive binary.
- `config/theloadunload.json` is the template; `src/orders.rs` supplies posting and cancellation.
- Unit tests cover LONG and SHORT grids, zero distance rejection, and transaction classification.

## Assumptions

- The operator runs the binary to create the trade; the listener processes later fills.
- The entry notional prompt is in USDT even though the prompt text calls it a quantity.
- `stop_loss_amount` is the intended maximum loss in USDT for the averaged position.

## Known deviations

- Only `FILLED` events are handled; partial fills never refresh the grid or protection, so a partially filled averaging line leaves stored quantities and the stop out of date.
- `MIGRATION.md` describes the stop-loss classification fix, but the Python behavior it replaced made the stop-loss and take-profit branches unreachable. The specified classification is therefore current Rust behavior rather than a Python-compatible baseline.
- The grid loop can still stop early if the stop price crosses the next line, leaving fewer averaging levels than the operator may expect. It does not report the number of levels that fit.
- Disabled stop-loss or body lines are still posted in some paths because `post_order` posts the stop loss unconditionally and body lines are filtered only by `NEW` status.
- Take profit is regenerated from the current price on every grid and unload fill, so it moves with the average rather than staying at the original target.
- Unload quantity is `current - entry` with no lower bound; a position below the original entry size can produce a negative quantity.
- `ops/{SYMBOL}.json` is merged only when the existing file already belongs to `THE_LOAD_UNLOAD_GRID`; otherwise the whole document is replaced.
