# Spec Delta

## Purpose

Defines the trader-driven lifecycle of one assisted trade: what the trader is asked for, which states the trade moves through, and what the trader can do at each point.

## ADDED Requirements

### Requirement: Required trade inputs

The terminal SHALL collect the symbol, side (LONG or SHORT), entry price, notional amount in USDT, and risk amount in USDT before any order is placed. A safety order price MAY also be supplied; leaving it blank means the trade has no averaging order.

#### Scenario: Complete input

- **WHEN** the trader supplies symbol BTCUSDT, side LONG, price 100, notional 1000, risk 10 and safety price 99.5
- **THEN** the assistant records the plan and proceeds to validation

#### Scenario: No safety price

- **WHEN** the trader leaves the safety price blank
- **THEN** the trade is created with no averaging order and the stop is the only protection

### Requirement: Unambiguous input parsing

Symbol input SHALL accept a bare base asset such as BTC or ETH and resolve it to the exchange's contract symbol, and the assistant MUST confirm the resolved symbol, derived quantity and derived stop price before submitting anything.

#### Scenario: Bare base asset resolves

- **WHEN** the trader types BTC
- **THEN** the assistant resolves it to a USDS-M perpetual symbol and shows the resolved symbol in the confirmation

#### Scenario: Unknown symbol

- **WHEN** the trader types a symbol the exchange does not list for USDS-M futures
- **THEN** the assistant refuses the input and places no order

### Requirement: One active trade per symbol and side

At most one active trade SHALL exist for each `(symbol, position_side)` pair. A second attempt on the same pair MUST be refused while the first is active.

#### Scenario: Duplicate on the same side

- **WHEN** an active BTCUSDT LONG trade exists and the trader starts another BTCUSDT LONG
- **THEN** the assistant refuses the new trade and reports the existing one

#### Scenario: Opposite side is independent

- **WHEN** an active BTCUSDT LONG trade exists and the trader starts a BTCUSDT SHORT
- **THEN** the new trade is accepted and both are tracked separately

### Requirement: Nothing is sent when validation fails

The entry order SHALL be placed only after risk validation succeeds. When validation rejects the plan, no order of any kind MUST reach the exchange.

#### Scenario: Rejected plan leaves no orders

- **WHEN** a plan is rejected because its risk does not exceed fees
- **THEN** no entry, safety or stop order is created and no order record is stored as active

### Requirement: Safety order is placed only after the entry fills

The safety order SHALL be submitted only once the entry order has filled. While the entry is pending, no safety order MAY exist on the exchange.

#### Scenario: Entry pending

- **WHEN** the entry order is resting unfilled
- **THEN** no safety order has been submitted

#### Scenario: Entry fills

- **WHEN** the entry order reaches a filled state
- **THEN** the assistant places the stop and, if a safety price was supplied, the safety order

### Requirement: Stop is replaced after a safety fill

When the safety order fills, the assistant SHALL recompute the stop for the new combined size and average price and replace the existing stop with it, keeping total risk equal to `R`.

#### Scenario: Risk unchanged after averaging

- **WHEN** the safety order fills and the stop is replaced
- **THEN** the new stop satisfies the whole-position risk target and the reported risk remains the amount the trader entered

### Requirement: Position never unprotected

The assistant MUST NOT cancel the existing stop before its replacement is accepted by the exchange, so that no interval exists in which the position has no stop.

#### Scenario: Replacement ordering

- **WHEN** the stop is being replaced after a safety fill
- **THEN** the new stop is acknowledged by the exchange before the previous stop is cancelled

#### Scenario: Replacement rejected

- **WHEN** the exchange rejects the replacement stop
- **THEN** the previous stop stays in force and the trader is alerted

### Requirement: Partial fills size the risk to the actual position

When an entry or safety order fills only partially, the stop SHALL be computed from the quantity actually executed, and MUST be recomputed as further quantity fills.

#### Scenario: Safety partially filled

- **WHEN** the safety order executes 40% of its quantity
- **THEN** the stop is sized for the position that actually exists and the reported risk still equals `R`

#### Scenario: Entry partially filled

- **WHEN** the entry order executes half its quantity and rests
- **THEN** a stop for the executed half is placed and the risk target applies to that half

### Requirement: Trade ends when the stop fills

When the stop fills, the assistant SHALL record the realised result and the fees paid, cancel any remaining order belonging to that trade, and return to an idle state.

#### Scenario: Stopped out

- **WHEN** the stop order fills
- **THEN** the trade is marked closed, the realised loss including fees is recorded, and no order of that trade remains open

#### Scenario: Safety order still resting after the stop fills

- **WHEN** the stop fills while the safety order is still resting
- **THEN** the safety order is cancelled so it cannot open a new position

### Requirement: Position closed outside the assistant

When the position reaches zero without the assistant's stop filling, the trade MUST be marked as closed externally, any of its remaining orders cancelled, and the trader informed.

#### Scenario: Manual close in the exchange app

- **WHEN** the trader closes the position manually and the assistant observes zero position size
- **THEN** the trade is marked closed externally and its resting orders are cancelled

### Requirement: Trader can cancel an active trade

The trader SHALL be able to cancel an active trade from the terminal. Cancellation MUST cancel only that trade's own orders and MUST NOT affect orders belonging to the opposite side of the same symbol.

#### Scenario: Cancelling one side

- **WHEN** the trader cancels a BTCUSDT LONG trade while a BTCUSDT SHORT trade is active
- **THEN** only the LONG trade's orders are cancelled and the SHORT trade's stop remains in force

#### Scenario: Cancelling a pending entry

- **WHEN** the trader cancels while the entry is still unfilled
- **THEN** the entry is cancelled, no stop or safety order is created, and the trade ends

### Requirement: Session state is durable

Every trade state transition SHALL be persisted so the trade can be identified after a restart, including the orders it owns and the risk amount it must preserve.

#### Scenario: State survives a restart

- **WHEN** the assistant is killed while a trade is active and started again
- **THEN** the trade is found in its last persisted state and its orders are still associated with it

### Requirement: Status reporting

The assistant SHALL report the current state of a trade on demand, including average entry price, position size, current stop price, remaining risk and any resting orders.

#### Scenario: Status of a hedged trade

- **WHEN** the trader asks for status while the entry and safety orders are filled
- **THEN** the assistant shows the combined size, the average price and the stop currently protecting it

#### Scenario: Status with a pending entry

- **WHEN** the trader asks for status while the entry is unfilled
- **THEN** the assistant reports the trade as awaiting the entry fill and shows that no stop exists yet
