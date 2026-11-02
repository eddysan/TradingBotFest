# RECOVERY_ZONE Strategy Specification

## Purpose

Defines the recovery-zone strategy: one or two entry levels, an opposite-side hedge, escalating recovery, break-even and take-profit/stop-loss grids, and an optional trailing stop after an entry fills.

## Requirements

### Requirement: Interactive input
The system SHALL prompt for a base symbol, append `USDT`, prompt for `LONG` or `SHORT` with `LONG` as the blank default, prompt for one or two entries with one as the default, read the symbol filters, and build entry and take-profit data. It SHALL load `config/recoveryzone.json` as the template.

#### Scenario: Single-entry long
- **WHEN** the operator enters `BTC`, leaves the side blank, and chooses one entry
- **THEN** a `LONG` recovery zone with one entry is prepared for `BTCUSDT`

#### Scenario: Two-entry short
- **WHEN** the operator chooses `SHORT` and two entries
- **THEN** both entry lines are created on the SHORT side

### Requirement: Existing position adoption
When a non-zero position exists on the requested side, the system SHALL build the first entry from the exchange entry price and absolute quantity with status `FILLED`, prompt for a second entry price and a take-profit price, and create the second entry with status `NEW` for two entries or `CANCELLED` with zero quantity for one entry.

#### Scenario: Adopted position with two entries
- **WHEN** a position exists and two entries are selected
- **THEN** the first line is filled from the exchange and the second line is new at the prompted price

#### Scenario: Adopted position with one entry
- **WHEN** a position exists and one entry is selected
- **THEN** the second line has zero quantity and status `CANCELLED`

### Requirement: New entry construction and sizing
For a new zone the system SHALL prompt for first entry price, second entry price, and take-profit price, reject zero prices and identical entry prices, compute distance between the entries, and suggest USDT quantity as `wallet_balance * min_risk / distance`. One entry SHALL receive the full quantity; two entries SHALL split it in half and convert each half at its own entry price.

#### Scenario: Two entry quantities
- **WHEN** the suggested notional is 100 USDT and the entries are at 100 and 90
- **THEN** each entry receives `50 / price` converted at 100 and 90 respectively

#### Scenario: Identical entries
- **WHEN** both entry prices are equal
- **THEN** input fails because the recovery distance is zero

#### Scenario: Zero entry price
- **WHEN** either entry price is zero
- **THEN** input fails before any order is posted

### Requirement: Product factor and hedge line
The system SHALL compute `product_factor` as `(target_factor + 1) / target_factor` rounded to two decimals, rejecting a zero target factor. It SHALL anchor the opposite-side hedge to the second entry price, offset by the configured hedge distance in the opposite direction, and size it as `product_factor * total_entry_quantity` rounded to the quantity precision.

#### Scenario: Hedge sizing
- **WHEN** total entry quantity is 2 and product factor is 1.5
- **THEN** the hedge quantity is `3.000` at the configured precision

#### Scenario: Zero target factor
- **WHEN** `risk.target_factor` is zero
- **THEN** input fails instead of dividing by zero

### Requirement: State replacement
The system SHALL write the complete recovery-zone document to `ops/{SYMBOL}.json`, replacing any existing document for that symbol.

#### Scenario: Existing state of another strategy
- **WHEN** `ops/BTCUSDT.json` already exists
- **THEN** the recovery-zone document replaces it

### Requirement: Initial order placement
The system SHALL post every `NEW` entry line, post the opposite-side hedge order, and post the take profit when enabled.

#### Scenario: Fresh two-entry zone
- **WHEN** both entry lines are `NEW`
- **THEN** both entries, the hedge, and the enabled take profit are submitted

#### Scenario: Adopted position
- **WHEN** the first entry is `FILLED` and the second is `NEW`
- **THEN** only the second entry is submitted along with the hedge and take profit

### Requirement: Entry fill and trailing stop
On a `LIMIT` fill the system SHALL refresh both sides' hedge lines from the exchange positions. When the filled side has trailing stop enabled it SHALL cancel that side's existing trailing-stop orders, generate a new trailing stop, and post it.

#### Scenario: Entry fills
- **WHEN** an entry limit order fills
- **THEN** the current hedge lines are refreshed and an enabled trailing stop is replaced

#### Scenario: Trailing stop disabled
- **WHEN** the trailing stop is disabled on the filled side
- **THEN** only the position refresh occurs

### Requirement: Hedge fill and recovery escalation
On a `STOP_MARKET` fill with `closePosition=false` the system SHALL refresh positions, cancel every open order for the symbol, and compare the LONG and SHORT hedge quantities. When they differ it SHALL escalate: multiply `min_risk` by `product_factor`, resize the opposite hedge, post a recovery line, regenerate distances and target points, and post take-profit and stop-loss orders for both sides.

#### Scenario: Hedge fills below maximum risk
- **WHEN** the hedge fills and the escalated risk remains below `max_risk`
- **THEN** the opposite hedge is resized with the product factor and a recovery order is posted

#### Scenario: Hedge fills at maximum risk
- **WHEN** the escalated risk reaches or exceeds `max_risk`
- **THEN** the new opposite quantity is the plain difference between the position and opposite quantities

#### Scenario: Quantities already balanced
- **WHEN** the LONG and SHORT hedge quantities are equal
- **THEN** no recovery escalation occurs

### Requirement: Recovery line calculation
The system SHALL compute the inside distance between the opposite hedge price and the current position's hedge price, scale it by `reduce_hedge`, and place the recovery price on the opposite hedge at that scaled distance toward the current position. The recovery quantity SHALL equal the opposite hedge quantity.

#### Scenario: Recovery direction for a long position
- **WHEN** the current side is LONG and the opposite hedge price is the first argument
- **THEN** the recovery price is above the opposite hedge price by the scaled inside distance

### Requirement: Distance, break-even, and target grid
The system SHALL compute LONG and SHORT hedge distances from the two hedge prices, derive win and loss distances using `target_factor`, and derive break-even prices, break-even quantities and costs, take-profit prices, and stop-loss prices. The LONG stop-loss price SHALL equal the SHORT take-profit price and vice versa.

#### Scenario: Symmetric targets
- **WHEN** distances, break-even points, and target points are regenerated
- **THEN** each side's stop-loss price is the other side's take-profit price

#### Scenario: SHORT loss distance
- **WHEN** the SHORT loss distance is computed
- **THEN** it uses the same `distance * (target_factor + 1)` form as the LONG side

### Requirement: Terminal fills
On a `TAKE_PROFIT_MARKET` with `closePosition=true`, a `STOP_MARKET` with `closePosition=true`, or any `TRAILING_STOP_MARKET` fill, the system SHALL cancel the position side's `GRID` orders and the opposite side's `HEDGE` orders.

#### Scenario: Take profit fills
- **WHEN** a take-profit close-position order fills
- **THEN** the entry grid on that side and the hedge on the opposite side are cancelled

#### Scenario: Trailing stop fills
- **WHEN** a trailing stop fills
- **THEN** the same two cancellation scopes are applied

## Provenance

- `src/strategies/recovery_zone.rs` implements input, adoption, hedge sizing, posting, fill branches, recovery, distance, break-even, target, stop, and trailing-stop math.
- `src/bin/recovery_zone.rs` wires the interactive binary.
- `config/recoveryzone.json` is the template; `src/orders.rs` supplies posting and cancellation.
- Unit tests cover side symmetry, break-even and target points, recovery direction, and the trailing-stop cap.

## Assumptions

- `min_risk` is a USDT risk budget and `max_risk` is its escalation ceiling.
- Both position sides can be open simultaneously because hedge mode is enabled.
- A recovery-zone trade is operated as a pair of opposing positions rather than one net position.

## Known deviations

- `config/recoveryzone.json` ships `reduce_hedge: 0`. The recovery price then equals the opposite hedge price, so the recovery order is likely rejected or immediately triggered, and escalation cannot function until an operator edits the config.
- `generate_stop_loss_protection` exists but is never called. The `protection_distance` field is therefore inert.
- Hedge fills are detected only when `closePosition` is false and the order type is `STOP_MARKET`. A manually placed stop with the same shape on either side can be mistaken for a hedge fill.
- The quantity comparison uses exact `f64` inequality. A representation difference can trigger escalation even when the two positions are economically balanced.
- `update_current_position` overwrites both sides' hedge price and quantity from exchange positions, including a zero quantity for a side that is not open, which can make subsequent comparisons and recovery sizing operate on zero.
- Recovery escalates `min_risk` before checking `max_risk`; once the threshold is crossed it keeps using the unmultiplied difference but does not cap or reset the stored risk.
- `input_data` always replaces `ops/{SYMBOL}.json`, discarding documents owned by CARDIAC or THE_LOAD_UNLOAD_GRID.
- Only `FILLED` events are handled; partial fills do not refresh positions or regenerate protective orders.
