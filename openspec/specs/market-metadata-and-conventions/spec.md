# Market Metadata and Conventions Specification

## Purpose

Defines how the bot reads symbol constraints from Binance, rounds prices and quantities, formats exchange values, and computes the percentage distances shared by all strategies.

## Requirements

### Requirement: Symbol filter discovery
The system SHALL fetch the full exchange information and select the entry whose symbol exactly matches the requested symbol. It SHALL read `pricePrecision`, `quantityPrecision`, `PRICE_FILTER.tickSize`, `LOT_SIZE.stepSize`, `LOT_SIZE.minQty`, `LOT_SIZE.maxQty`, and `MIN_NOTIONAL.notional` or `minNotional`. Missing optional filters SHALL leave their defaults rather than failing.

#### Scenario: Complete filters
- **WHEN** the symbol exposes price, lot-size, and minimum-notional filters
- **THEN** the parsed filters contain the tick size, step size, quantity bounds, and minimum notional

#### Scenario: Missing optional filter
- **WHEN** a symbol omits the minimum-notional filter
- **THEN** the minimum notional is zero and filter parsing still succeeds

#### Scenario: Numeric filter is malformed
- **WHEN** a present filter value cannot be parsed as a number
- **THEN** filter discovery fails with the filter type and symbol in the error

### Requirement: Unknown symbol handling
When the requested symbol is absent from exchange information, the system SHALL fail with an unknown-symbol error rather than guessing defaults.

#### Scenario: Delisted or misspelled symbol
- **WHEN** the operator enters a symbol that is not in `exchangeInfo`
- **THEN** the binary stops with an unknown-symbol error before posting orders

### Requirement: Price rounding
The system SHALL round prices using the number of decimal places derived from the absolute base-10 logarithm of the tick size, applying round-half-to-even at that precision.

#### Scenario: One-decimal tick
- **WHEN** the tick size is `0.1` and the price is `99.2537`
- **THEN** the rounded price is `99.3`

#### Scenario: Halfway value
- **WHEN** a value is exactly halfway between two representable values
- **THEN** rounding selects the even neighbour, matching Python's `round`

### Requirement: Quantity rounding
The system SHALL round quantities to the symbol's `quantityPrecision`. The existing floor-to-step helper SHALL NOT be used by strategy order paths.

#### Scenario: Quantity precision
- **WHEN** the quantity precision is 3 and the computed quantity is `1.23456`
- **THEN** the quantity written to the order is `1.235`, not a value floored to the step size

### Requirement: Value formatting
The system SHALL send prices and quantities using Rust's default floating-point display, which omits a trailing `.0` and is the current representation used in form-encoded order parameters.

#### Scenario: Whole-number price
- **WHEN** a price is `100.0`
- **THEN** the request parameter is `100`

### Requirement: Percentage distance
The system SHALL compute percentage distance as the absolute difference divided by the first supplied price, multiplied by 100 and rounded to two decimals. The ordering of the two arguments therefore changes the result.

#### Scenario: Rising distance
- **WHEN** the first price is 100 and the second is 101
- **THEN** the distance is `1.0`

#### Scenario: Falling distance
- **WHEN** the first price is 101 and the second is 100
- **THEN** the distance is `0.99`

### Requirement: Base asset naming
The system SHALL derive the display base asset by stripping a trailing `USDT` suffix from the symbol, and SHALL leave the symbol unchanged when that suffix is absent.

#### Scenario: USDT pair
- **WHEN** the symbol is `BTCUSDT`
- **THEN** the displayed base asset is `BTC`

## Provenance

- `src/exchange/filters.rs` parses filters and exposes rounding helpers.
- `src/util.rs` implements `py_round`, `tick_digits`, `round_to_tick`, `get_distance`, `fmt_num`, and `base_asset`.
- Unit tests in both files establish the documented rounding and distance examples.

## Assumptions

- Tick and step sizes are the authoritative source; precision fields are treated as a convenience.
- All traded symbols quote in USDT.

## Known deviations

- `tick_digits` derives decimals from `log10(tick_size)`, which is only correct for tick sizes that are powers of ten. A tick such as `0.5` yields zero decimals and would round a price to a whole number.
- Quantities are rounded by `quantityPrecision` rather than floored to `stepSize`, so a symbol whose precision and step size disagree can receive an invalid quantity. `floor_quantity` and `meets_min_notional` exist but are not called by any order path.
- `minQty`, `maxQty`, and `minNotional` are parsed but never enforced before order submission.
- Money and quantity calculations use `f64` throughout, including `py_round`, so binary floating-point error is possible.
- `fmt_num` relies on Rust's `Display`; very small or very large magnitudes may use exponent notation rather than the plain decimal form Binance expects.
- `get_distance` divides by the first argument, so the same pair of prices produces different percentages depending on call order. Strategies rely on this asymmetric behavior.
