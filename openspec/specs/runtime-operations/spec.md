# Runtime Operations Specification

## Purpose

Defines how the binaries are run, logged, installed as a service, and deployed, and the operational guarantees that surround the long-running listener.

## Requirements

### Requirement: Binary roles
The system SHALL provide five binaries: `bot` as the long-running user-data listener, `cardiac`, `load_unload`, and `recovery_zone` as interactive one-shot trade setup tools, and `clean_orders` as an interactive cancellation tool.

#### Scenario: Service starts
- **WHEN** the systemd unit starts
- **THEN** only the `bot` binary runs

#### Scenario: Operator creates a trade
- **WHEN** the operator runs a strategy binary
- **THEN** it prompts for input, performs its exchange calls, and exits

#### Scenario: Operator cancels orders
- **WHEN** the operator runs `clean_orders`
- **THEN** it prompts for symbol and `LONG`, `SHORT`, or `ALL`, then cancels the matching open orders

### Requirement: Logging configuration
Every binary SHALL initialise logging before exchange work, SHALL create the log directory when needed, SHALL write INFO and above to the console, and SHALL append DEBUG and above to `logs/positions.log` without ANSI colour codes.

#### Scenario: Normal run
- **WHEN** a binary starts successfully
- **THEN** human-readable INFO lines appear on the console and DEBUG detail is appended to the log file

#### Scenario: Missing log directory
- **WHEN** `logs/` does not exist
- **THEN** it is created before the file is opened

### Requirement: Service definition
The system SHALL install a user-level systemd unit named `tradingbot` that runs `target/release/bot` from `%h/TradingBotFest`, restarts on failure after five seconds, and starts with the user's default target.

#### Scenario: Process crash
- **WHEN** the `bot` process exits unexpectedly
- **THEN** systemd restarts it after the configured delay

#### Scenario: Host reboot
- **WHEN** the user session starts
- **THEN** the enabled unit starts the listener

### Requirement: Deployment script
The update script SHALL fetch and hard-reset the checkout to `origin/main`, pull, require `cargo`, build the release binaries, install the unit file, reload systemd, enable the service, create `logs/`, `ops/`, and `config/` when absent, and restart the service.

#### Scenario: Successful update
- **WHEN** `update.sh` runs on a clean checkout with cargo installed
- **THEN** the release build is installed and the service restarts with the new binary

#### Scenario: Cargo missing
- **WHEN** `cargo` is not on `PATH`
- **THEN** the script exits non-zero before building or restarting

#### Scenario: Local changes present
- **WHEN** the checkout has uncommitted changes
- **THEN** `git reset --hard origin/main` discards them before building

### Requirement: Continuous deployment
The repository SHALL deploy on every push to `main` by connecting to the configured host over SSH with repository secrets and running `update.sh`.

#### Scenario: Merge to main
- **WHEN** a commit lands on `main`
- **THEN** the workflow connects to the droplet and invokes the update script

### Requirement: Secret handling
Credentials SHALL live in `config/.credentials.env` or `.env`, both excluded from version control, and SHALL NOT be committed or embedded in the service unit or deployment script.

#### Scenario: Repository contents
- **WHEN** the repository is inspected
- **THEN** no API key or secret file is tracked

### Requirement: Runtime continuity
The listener SHALL keep running across strategy handler errors and WebSocket disconnects. It SHALL NOT reconcile state, replay missed fills, or verify open orders at startup.

#### Scenario: Handler error
- **WHEN** a strategy handler fails
- **THEN** the listener logs the error and keeps consuming events

#### Scenario: Restart after downtime
- **WHEN** the service restarts after being down
- **THEN** it resumes from the next live event without reconstructing positions or orders from `ops/` or the exchange

## Provenance

- `Cargo.toml` declares the five binaries.
- `src/bin/*.rs` and `src/logging.rs` define the entry points and log setup.
- `config/tradingbot.service`, `update.sh`, and `.github/workflows/deploy.yml` define installation and deployment.
- `README.md` and `MIGRATION.md` document the operating model.

## Assumptions

- The service runs under a user account with permission to write the checkout, `ops/`, and `logs/`.
- The branch deployed to production is `main`.
- Only one instance of the service runs per account.

## Known deviations

- `update.sh` performs a hard reset of the production checkout on every deployment, so any local operational edit, including a credentials file or a hotfix, is discarded.
- The deployment workflow has no build, test, or validation gate before restarting the production service.
- There is no startup reconciliation, order audit, or alert for an unprotected position after a restart or a handler failure.
- Logs are a single append-only file with no rotation, retention, or size limit.
- Console output and file output contain order identifiers and raw WebSocket payloads at DEBUG level; credentials are not logged, but account and order detail is.
- There is no health endpoint, heartbeat monitor, or external alert. `Restart=always` restarts the process but does not repair missing protection orders.
- The strategy binaries exit immediately after setup, so a failed follow-up order is only visible in the log and not retried by the service.
