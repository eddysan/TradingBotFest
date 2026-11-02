# User Data Stream and Dispatch Specification

## Purpose

Defines the long-running user-data listener: listen-key lifecycle, WebSocket connection and keepalive, reconnection, event filtering, and how fills are routed to the strategy that owns a symbol.

## Requirements

### Requirement: Listen-key lifecycle
The system SHALL create a listen key before connecting, build the user-data WebSocket URL from the selected environment and that key, renew the key every 30 minutes while connected, and attempt to close the key when the connection ends.

#### Scenario: Stream starts
- **WHEN** the bot binary starts
- **THEN** it requests a listen key and connects to the corresponding testnet or production user-data URL

#### Scenario: Key renewal
- **WHEN** 30 minutes elapse on a live connection
- **THEN** the listener sends a keepalive for the current listen key

#### Scenario: Clean shutdown
- **WHEN** the operator presses Ctrl-C
- **THEN** the keepalive task stops and the listener attempts to close the listen key

### Requirement: Connection maintenance
The system SHALL send a WebSocket ping every 120 seconds, answer exchange pings with pongs, and treat a close frame, transport error, or ended stream as a disconnect.

#### Scenario: Idle connection
- **WHEN** no messages arrive for two minutes
- **THEN** the listener sends a ping to keep the connection alive

#### Scenario: Exchange ping
- **WHEN** the server sends a ping frame
- **THEN** the listener replies with a matching pong

### Requirement: Reconnection with backoff
On disconnect the system SHALL log the failure, wait a retry delay that starts at 5 seconds and doubles up to 120 seconds, and reconnect until Ctrl-C. A `listenKeyExpired` event SHALL force an immediate reconnect rather than being treated as an ordinary order event.

#### Scenario: Stream drop
- **WHEN** the WebSocket closes unexpectedly
- **THEN** the listener waits and reconnects, increasing the delay on repeated failures

#### Scenario: Expired listen key
- **WHEN** a `listenKeyExpired` event is received
- **THEN** the current stream ends and the reconnect loop creates a new listen key

### Requirement: Event filtering
The system SHALL parse incoming text as a user-data event, ignore event types other than `ORDER_TRADE_UPDATE` and `listenKeyExpired`, and continue after malformed JSON or an order update with no order payload while logging the problem.

#### Scenario: Non-order account event
- **WHEN** an account update or margin call event arrives
- **THEN** it is ignored without affecting the stream

#### Scenario: Malformed message
- **WHEN** a text frame cannot be parsed as a user-data event
- **THEN** the error is logged and the listener continues reading

#### Scenario: Missing order payload
- **WHEN** an `ORDER_TRADE_UPDATE` has no order object
- **THEN** the error is logged and the listener continues

### Requirement: Strategy routing
For each order event the system SHALL read `ops/{SYMBOL}.json`, inspect its `strategy` field, and dispatch to `THE_LOAD_UNLOAD_GRID`, `CARDIAC`, or `RECOVERY_ZONE`. A missing state file SHALL be ignored; an unknown strategy name SHALL be logged and ignored.

#### Scenario: Known strategy
- **WHEN** the state file names `CARDIAC`
- **THEN** the event is handed to the CARDIAC handler

#### Scenario: No state file
- **WHEN** no `ops/{SYMBOL}.json` exists
- **THEN** the event is ignored without an error

#### Scenario: Unknown strategy name
- **WHEN** the state file names a strategy the dispatcher does not implement
- **THEN** a warning is logged and no work is performed

### Requirement: Per-symbol ordering and bounded concurrency
The system SHALL process events for the same symbol in arrival order using one lock per symbol, SHALL allow different symbols to proceed independently, and SHALL allow at most ten event handlers in flight at once.

#### Scenario: Two fills for one symbol
- **WHEN** two order updates for the same symbol arrive back to back
- **THEN** the second waits for the first handler to finish

#### Scenario: Fills for two symbols
- **WHEN** updates for two different symbols arrive together
- **THEN** they may be processed concurrently

### Requirement: Handler failures do not stop the listener
When a strategy handler returns an error, the system SHALL log it and keep the stream running.

#### Scenario: Strategy error
- **WHEN** a handler fails while updating state or posting an order
- **THEN** the error is logged and the listener continues processing further events

## Provenance

- `src/exchange/ws.rs` implements the listen key, WebSocket loop, keepalive, ping, backoff, parsing, locks, and semaphore.
- `src/strategies/mod.rs` implements strategy lookup and dispatch.
- `src/bin/bot.rs` is the service entry point.

## Assumptions

- Binance delivers `ORDER_TRADE_UPDATE` for every order state change, including fills.
- Only one bot process consumes the account's user-data stream at a time.

## Known deviations

- Strategy handlers act only on `status == "FILLED"`. Partially filled orders, expirations, and cancellations are ignored, so a partial fill never updates the stored position or protection orders.
- The WebSocket does not request or replay missed events. Fills that occur while the bot is disconnected or restarting are lost until a strategy is run manually.
- The retry delay is not reset after a successful connection; a later disconnect can inherit a long delay from an earlier failure sequence.
- There is no jitter, maximum attempt count, heartbeat timeout, or explicit detection of a silently dead connection beyond the two-minute ping.
- Event handling is spawned and not awaited by the reader, so a process exit can discard handlers that have not completed.
- Only one listen key is supported; the bot does not coordinate multiple instances or detect that another process consumed the same key.
