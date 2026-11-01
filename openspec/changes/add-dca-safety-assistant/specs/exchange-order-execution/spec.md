# Spec Delta

## Purpose

Defines how the assistant's orders reach Binance USDS-M futures: the order shapes required in hedge mode, the exchange constraints that must be satisfied before submission, and how failures are surfaced to the trader.

## ADDED Requirements

### Requirement: Hedge-mode order shape

Every order SHALL carry a `positionSide` of LONG or SHORT matching the trade's side, and closing orders MUST use the opposite order side from the position they close.

#### Scenario: Long entry

- **WHEN** a LONG trade's entry is submitted
- **THEN** the order uses order side BUY and position side LONG

#### Scenario: Long stop

- **WHEN** a LONG trade's stop is submitted
- **THEN** the order uses order side SELL and position side LONG

### Requirement: Stop is a full-position market stop

The stop SHALL be a STOP_MARKET order with close-position behaviour, working type MARK_PRICE, and price protection enabled. It MUST NOT carry a quantity or a reduce-only flag.

#### Scenario: Stop request shape

- **WHEN** the assistant submits a stop
- **THEN** the request closes the entire position on its side without specifying quantity

#### Scenario: Position grew before replacement

- **WHEN** the safety order fills before the stop is replaced
- **THEN** the stop in force still closes the whole enlarged position because its size is implied by the position, not fixed at submission

### Requirement: Entries and safety orders are limit orders

Entry and safety orders SHALL be LIMIT orders with an explicit price and time in force GTC. The assistant MUST NOT submit market orders to open or add to a position.

#### Scenario: Safety order type

- **WHEN** a safety order is submitted
- **THEN** it is a LIMIT order at the price the trader supplied

### Requirement: Order identity ties orders to a trade

Every submitted order SHALL carry a client order ID that encodes the trade and the order's role, and that ID MUST be unique on the exchange. The assistant SHALL use these IDs to query and cancel its own orders.

#### Scenario: Cancel by identity

- **WHEN** the assistant cancels a trade
- **THEN** it cancels exactly the orders whose client order IDs belong to that trade

#### Scenario: ID collision

- **WHEN** the exchange rejects a submission because the client order ID is already in use
- **THEN** the rejection is surfaced and the trade is not advanced to a new state

### Requirement: Exchange filters are applied before submission

Quantities SHALL be rounded down to the symbol's step size and prices rounded to its tick size before submission. The assistant MUST verify the rounded values satisfy the symbol's minimum quantity and minimum notional, and MUST refuse to submit when they do not.

#### Scenario: Quantity below minimum notional

- **WHEN** the rounded quantity's notional is below the symbol's minimum notional
- **THEN** no order is submitted and the trader is told which limit was violated

#### Scenario: Stop price off the tick grid

- **WHEN** a derived stop price does not lie on the tick grid
- **THEN** the submitted trigger price is the tick-rounded value used in the risk calculation

### Requirement: Leverage is configured before the entry

The assistant SHALL set the symbol's leverage to the requested value and read back the resulting liquidation price for the relevant position side before submitting the entry. If either step fails, the trade MUST be abandoned before any order is placed.

#### Scenario: Leverage change rejected

- **WHEN** the exchange rejects the leverage setting
- **THEN** no entry order is submitted and the trader sees the exchange's error

#### Scenario: Leverage is per symbol

- **WHEN** leverage is changed for a symbol that already holds a position on the opposite side
- **THEN** the assistant reports that the opposite side's liquidation price changed as a result

### Requirement: Exchange rejections are surfaced, never swallowed

Every rejection from the exchange SHALL be reported to the trader with the exchange's error code and message, and the trade MUST remain in its previous state.

#### Scenario: Stop would trigger immediately

- **WHEN** the exchange rejects a stop because it would trigger immediately
- **THEN** the trader is alerted with that reason and the trade is marked as requiring intervention rather than silently continuing

#### Scenario: Insufficient margin

- **WHEN** the entry is rejected for insufficient margin
- **THEN** the trade ends without a stop or safety order and the reason is recorded

### Requirement: Environment selection is explicit and never mixed

The assistant SHALL direct every order, query and cancel to either the testnet or the production endpoint based on the `USE_TESTNET` setting, and MUST refuse to run when that setting is missing or contradictory.

#### Scenario: Testnet run

- **WHEN** `USE_TESTNET` is true and testnet credentials are present
- **THEN** all exchange traffic goes to the testnet endpoint

#### Scenario: Missing credentials

- **WHEN** the credentials for the selected environment are absent
- **THEN** the assistant refuses to start rather than falling back to the other environment

### Requirement: No order is sent without a client order identity

The assistant MUST NOT submit an order it cannot later identify, so every submission SHALL persist the symbol, side, position side, type, price, quantity, role and client order ID before or atomically with the exchange call.

#### Scenario: Crash during submission

- **WHEN** the process dies immediately after the exchange accepts an order
- **THEN** the persisted record allows the order to be found and reconciled on restart
