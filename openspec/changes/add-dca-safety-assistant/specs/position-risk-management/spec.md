# Spec Delta

## Purpose

Derives the single stop-loss price that makes the trader's stated risk amount true for the whole position, and rejects trade plans whose requested risk cannot be honoured by any stop price.

## ADDED Requirements

### Requirement: Stop price for the whole position

The system SHALL compute one stop price for the entire open position such that a stop fill at its trigger produces a total loss, including fees, equal to the risk amount `R` supplied by the trader. When the position grows through a safety fill, the stop MUST be recomputed from the combined size and combined average entry price, never from only the most recently filled order.

#### Scenario: Long position, single fill

- **WHEN** the trader enters LONG at price 100 with notional 1000 USDT and risk 10 USDT, and no fees apply
- **THEN** the derived stop price is 99.0 and a stop fill at 99.0 loses exactly 10 USDT

#### Scenario: Short position, single fill

- **WHEN** the trader enters SHORT at price 100 with notional 1000 USDT and risk 10 USDT, and no fees apply
- **THEN** the derived stop price is 101.0 and a stop fill at 101.0 loses exactly 10 USDT

#### Scenario: Averaged position uses combined size and average price

- **WHEN** a LONG of 10 units at 100 fills, the safety order of 10 units at 99.5 then fills, and risk is 10 USDT
- **THEN** the stop is computed from size 20 and average price 99.75, giving 99.25, and a stop fill there loses 10 USDT rather than the 5 USDT that newest-line sizing would produce

### Requirement: Stop covers the whole position at all times

Once the entry fills, the position MUST NOT exist without a stop covering its full size. This includes the interval between a safety fill and the replacement of the stop, during which the existing stop MUST still cover the enlarged position.

#### Scenario: Safety fills while stop replacement is pending

- **WHEN** the safety order fills and the recalculated stop has not yet been accepted by the exchange
- **THEN** the stop in force still applies to the full position, and a stop trigger during that interval closes the entire size

### Requirement: Risk is net of fees

The derived stop distance SHALL account for maker fees already paid on filled entry and safety orders and for the taker fee charged on the stop exit, so that realised loss equals `R` when the stop fills at its trigger price.

#### Scenario: Fees push the stop further from the average

- **WHEN** maker fee 0.02% and taker fee 0.05% apply to a LONG with 1000 USDT notional and 10 USDT risk
- **THEN** the stop is placed further from the average entry price than the fee-free stop, and the net loss after all fees equals 10 USDT

#### Scenario: Stop exit is always charged taker

- **WHEN** the stop is a market order
- **THEN** the taker fee rate is used for the exit cost even if the entry and safety orders paid maker rates

### Requirement: Fee rates come from configuration

Fee rates SHALL be read from configuration, defaulting to 0.02% maker and 0.05% taker, and MUST be overridable without recompiling.

#### Scenario: Configured taker rate changes the stop

- **WHEN** the configured taker rate is raised from 0.05% to 0.08%
- **THEN** the derived stop for an otherwise identical plan moves further from the average entry price

### Requirement: Rounding never increases loss beyond the risk amount

Stop prices SHALL be rounded to the symbol's tick size toward the average entry price, so that rounding cannot increase the loss above `R`. Entry and safety quantities MUST be rounded down to the symbol's step size.

#### Scenario: Tick rounding pulls the stop toward entry

- **WHEN** the exact stop for a LONG is 99.2537 and the tick size is 0.1
- **THEN** the stop is placed at 99.3 and the loss at that price does not exceed the risk amount

#### Scenario: Quantity rounding truncates

- **WHEN** notional 1000 USDT is divided by price 100 with a step size of 0.001
- **THEN** the entry quantity is 10.000

### Requirement: Quantity is derived from notional

Entry quantity SHALL be derived as the notional amount divided by the entry price, then rounded down to the symbol's step size. The notional amount is the position's value, not the margin committed, so leverage MUST NOT multiply it.

#### Scenario: Leverage does not change the size

- **WHEN** the trader supplies notional 1000 USDT at price 100 with leverage 10x
- **THEN** the entry quantity is 10 units and the required margin is 100 USDT

#### Scenario: Size below the exchange minimum

- **WHEN** rounding the derived quantity leaves a size of zero, or a notional below the symbol's minimum
- **THEN** the plan is rejected and no order is sent

### Requirement: Reject plans whose risk does not exceed fees

The system MUST reject a trade plan when `R` is not greater than the fees needed to enter and exit the position, because no stop price can satisfy the risk target in that case.

#### Scenario: Risk below round-trip cost

- **WHEN** the trader supplies risk 0.50 USDT for a position whose entry and exit fees total 1.00 USDT
- **THEN** the plan is rejected before any order is placed

### Requirement: Reject safety prices that leave no room for the stop

The system MUST reject a trade plan when a safety fill would place the recomputed stop at or beyond the safety fill price, which occurs when the safety price's distance from entry exceeds `R` divided by the entry notional.

#### Scenario: Safety too deep for the stated risk

- **WHEN** the trader enters LONG at 100 with notional 1000 USDT, risk 10 USDT and safety price 98
- **THEN** the plan is rejected, because after the safety fill the stop that preserves 10 USDT of risk would sit above the safety fill price and the exchange would refuse it

#### Scenario: Safety inside the feasible depth

- **WHEN** the same plan uses safety price 99.5 instead
- **THEN** the plan is accepted, because the recomputed stop at 99.25 sits below the safety fill price

### Requirement: Reject safety prices that would fill before the entry

A supplied safety price MUST lie strictly beyond the entry in the averaging direction: below the entry price for a LONG and above it for a SHORT.

#### Scenario: Safety on the wrong side

- **WHEN** the trader enters LONG at 100 and supplies safety price 101
- **THEN** the plan is rejected

#### Scenario: Safety equal to entry

- **WHEN** the safety price equals the entry price
- **THEN** the plan is rejected

### Requirement: Reject stops beyond the liquidation price

The system MUST reject a plan whose derived stop lies at or beyond the position's liquidation price for the configured leverage, because the exchange would close the position before the stop is reached and the stated risk would not describe the real outcome.

#### Scenario: Liquidation closer than the stop

- **WHEN** a 20x LONG has liquidation price 95.5 and the derived stop is 94.0
- **THEN** the plan is rejected

#### Scenario: Stop inside liquidation

- **WHEN** the same position has liquidation price 90.0 and the derived stop is 94.0
- **THEN** the plan is accepted

### Requirement: Decimal arithmetic

All risk computations SHALL use decimal arithmetic and MUST NOT depend on binary floating point, so that identical inputs always produce an identical stop price.

#### Scenario: Repeated computation is identical

- **WHEN** the same plan is evaluated twice
- **THEN** both evaluations produce a bit-identical stop price

#### Scenario: No floating point drift

- **WHEN** quantities and prices that are not exactly representable in binary floating point are used
- **THEN** the computed stop reflects the exact decimal inputs rather than an accumulated rounding error
