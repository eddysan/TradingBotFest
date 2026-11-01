# Spec Delta

## Purpose

Turns resting orders into fill facts the trade session can act on, so the assistant knows when an entry, safety order or stop has executed without the trader having to confirm it.

## ADDED Requirements

### Requirement: Active orders are polled

While a trade has resting orders, the assistant SHALL query their state from the exchange on a fixed interval, defaulting to one second, and the interval MUST be configurable.

#### Scenario: Fill observed within the interval

- **WHEN** an order fills and the next poll occurs
- **THEN** the fill is reported to the trade session within one polling interval plus the request time

#### Scenario: No active orders

- **WHEN** no trade has resting orders
- **THEN** no polling requests are sent

### Requirement: Fills carry role, quantity and price

Each fill event SHALL identify the order's role (entry, safety or stop), the cumulative executed quantity, and the average fill price, so the session can size the position and the risk without a second lookup.

#### Scenario: Fill event contents

- **WHEN** a safety order fills 10 units at an average price of 99.5
- **THEN** the emitted event identifies it as a safety fill with those values

#### Scenario: Stop fill

- **WHEN** the stop order executes
- **THEN** the emitted event identifies it as a stop fill with the executed quantity and price needed to record the realised result

### Requirement: Partial fills are reported as they happen

An order that is partially filled SHALL produce an event carrying the quantity executed so far, and the session MUST be able to act on it before the order reaches its terminal state.

#### Scenario: Incremental partial fill

- **WHEN** an entry order fills 30% and later fills the remaining 70%
- **THEN** at least one event reflects the 30% state and the session's position size follows the executed quantity

### Requirement: Fill events are not duplicated

A fill MUST be reported only when the executed quantity changes, so that repeated polls of an unchanged order produce no additional events.

#### Scenario: Repeated poll with no change

- **WHEN** the same order state is observed on two consecutive polls
- **THEN** only one event is emitted for that state

#### Scenario: Restart after an observed fill

- **WHEN** the assistant restarts after already acting on a fill
- **THEN** the already-applied fill does not produce a second stop placement

### Requirement: Fill source is replaceable

The trade session SHALL consume fills from a source-agnostic stream, so that polling can be replaced by a push-based source without changing how the session reacts to a fill.

#### Scenario: Replacing the source

- **WHEN** the fill source is replaced with a push-based implementation
- **THEN** the session's reactions to entry, safety and stop fills are unchanged

### Requirement: Transient failures do not lose fills

When an exchange query fails, the assistant SHALL retry on subsequent intervals and MUST reconcile the order's full state once queries succeed again, rather than assuming the order is unchanged or cancelled.

#### Scenario: Temporary outage

- **WHEN** three consecutive polls fail and the fourth succeeds
- **THEN** a fill that occurred during the outage is still detected and acted upon

#### Scenario: Sustained failure

- **WHEN** queries continue to fail beyond the configured tolerance
- **THEN** the trader is alerted and no new trade actions are taken until state can be confirmed

### Requirement: Restart reconciliation

On startup the assistant SHALL load unfinished trades from storage, query the exchange for their orders and position, and apply any state change that happened while it was not running before resuming polling.

#### Scenario: Fill occurred while the assistant was down

- **WHEN** the entry filled while the assistant was stopped
- **THEN** on restart the assistant treats the entry as filled and places the stop and safety order

#### Scenario: Stop filled while the assistant was down

- **WHEN** the stop filled while the assistant was stopped
- **THEN** the trade is closed on restart with its realised result recorded

#### Scenario: Orders vanished

- **WHEN** an order recorded as active is no longer known to the exchange
- **THEN** the assistant resolves it from the exchange's order history or reports it as unresolved instead of leaving it active

### Requirement: Unknown orders are reported, not adopted

An order carrying the assistant's client order ID but matching no stored trade MUST be reported to the trader and MUST NOT be silently attached to an existing trade.

#### Scenario: Orphan order found

- **WHEN** reconciliation finds an order with an assistant client order ID and no matching trade
- **THEN** the trader is shown the order and the assistant takes no automatic action on it
