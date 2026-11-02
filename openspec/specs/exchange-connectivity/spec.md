# Exchange Connectivity Specification

## Purpose

Defines the Binance USDS-M futures REST connection used by every binary: endpoint selection, clock synchronisation, request signing, supported operations, and error translation.

## Requirements

### Requirement: Connection and clock synchronisation
The system SHALL select the Binance base URL from the configured environment, create an HTTP client with a 15-second timeout, call the ping endpoint, read the server time, and store the difference between server time and local time for later signed requests.

#### Scenario: Testnet connection
- **WHEN** the resolved environment is testnet
- **THEN** the client uses `https://testnet.binancefuture.com`, pings successfully, and records the server-time offset

#### Scenario: Production connection
- **WHEN** the resolved environment is production
- **THEN** the client uses `https://fapi.binance.com`, pings successfully, and records the server-time offset

#### Scenario: Endpoint unreachable
- **WHEN** the ping or server-time request fails
- **THEN** client construction fails and the binary exits before placing any order

### Requirement: Signed request contract
For signed requests the system SHALL append `recvWindow=5000` and a timestamp equal to local time plus the stored server offset, form-encode all parameters, sign the encoded query with HMAC-SHA256 using the API secret, append the lowercase hex signature, and send the API key in the `X-MBX-APIKEY` header. Unsigned requests SHALL omit credentials and signature parameters.

#### Scenario: Signed order request
- **WHEN** a create-order request is sent
- **THEN** the query contains `recvWindow`, `timestamp`, and `signature`, and the request carries `X-MBX-APIKEY`

#### Scenario: Unsigned metadata request
- **WHEN** exchange information or server time is requested
- **THEN** no API key header, timestamp, or signature is sent

### Requirement: Supported REST surface
The system SHALL expose only the operations the bot uses: ping, server time, exchange information, USDT futures balance, position risk, order creation, open-order listing, single-order cancellation, cancellation of all open orders for a symbol, and listen-key create, keepalive, and close.

#### Scenario: Order lifecycle calls
- **WHEN** a strategy places or cancels orders
- **THEN** it uses `POST /fapi/v1/order`, `GET /fapi/v1/openOrders`, `DELETE /fapi/v1/order`, or `DELETE /fapi/v1/allOpenOrders` as appropriate

#### Scenario: Position inspection
- **WHEN** a strategy updates its current position
- **THEN** it calls `GET /fapi/v2/positionRisk` for the symbol

### Requirement: Error translation
When a response has a non-success status, the system SHALL parse a Binance error body and return its numeric code and message. If no usable error body exists, the system SHALL return an error containing the HTTP status, path, and response body. A successful status with unparseable JSON SHALL also fail with a contextual error.

#### Scenario: Binance rejection
- **WHEN** an order is rejected with a Binance error body
- **THEN** the caller receives the exchange error code and message

#### Scenario: Non-JSON gateway failure
- **WHEN** the server returns a non-success status without a parsable error body
- **THEN** the caller receives an error containing the status and raw body

### Requirement: USDT balance semantics
The system SHALL return the futures wallet balance for the `USDT` asset rounded to two decimals, and SHALL return zero when no USDT balance entry is present.

#### Scenario: USDT balance present
- **WHEN** the balance response includes a USDT entry of `123.456`
- **THEN** the client reports `123.46`

#### Scenario: No USDT entry
- **WHEN** the balance response has no USDT asset
- **THEN** the client reports zero

### Requirement: Single-attempt transport
The system SHALL issue one HTTP request per client call and SHALL NOT retry, throttle, or apply request-weight backoff. Retry behaviour is owned by the caller.

#### Scenario: Transient network failure
- **WHEN** a request fails with a connection error
- **THEN** the error is returned immediately without an automatic retry

## Provenance

- `src/exchange/client.rs` defines base URLs, request construction, signing, endpoint methods, and error mapping.
- `src/exchange/models.rs` defines the accepted response shapes.
- `MIGRATION.md` records the replacement of `python-binance` with the hand-rolled client.

## Assumptions

- Binance USDS-M futures endpoints and HMAC-SHA256 signing remain stable.
- Hedging mode is enabled on the account, because orders carry `positionSide`.

## Known deviations

- The server-time offset is calculated once at startup. Clock drift after a long-running process starts is not corrected.
- `recvWindow` is fixed at 5000 ms and is not configurable.
- There is no request-weight accounting, rate-limit handling, or 429/418 backoff.
- The client does not validate key permissions, hedge-mode status, or account capabilities before the first order.
- A successful HTTP response whose body is empty or not the expected shape is reported as an invalid-response error; no partial recovery is attempted.
