# Runtime Configuration Specification

## Purpose

Defines how every binary discovers local configuration files, chooses between Binance testnet and production, and resolves the API credentials required before any exchange call.

## Requirements

### Requirement: Environment file discovery
The system SHALL load `config/.credentials.env` when that file exists and SHALL then load `.env` when that file exists, without failing when neither file is present. Loading SHALL NOT overwrite variables that are already set in the process environment.

#### Scenario: Both files exist
- **WHEN** `config/.credentials.env` and `.env` both exist and define the same variable
- **THEN** the value already loaded from the earlier file remains in effect

#### Scenario: Neither file exists
- **WHEN** neither configuration file exists
- **THEN** loading continues using only the process environment

#### Scenario: Only the fallback file exists
- **WHEN** only `.env` exists
- **THEN** its variables are loaded before credential resolution

### Requirement: Environment flag precedence
The system SHALL read `TESTNET` first and `USE_TESTNET` second. A flag SHALL be considered true when its trimmed, lower-cased value is `true`, `1`, or `yes`; any other defined value SHALL be false. When neither flag is defined, the system SHALL select production.

#### Scenario: Testnet flag set
- **WHEN** `TESTNET` is `True`
- **THEN** the selected environment is testnet

#### Scenario: Alias flag set
- **WHEN** `TESTNET` is absent and `USE_TESTNET` is `yes`
- **THEN** the selected environment is testnet

#### Scenario: Explicit false wins over alias
- **WHEN** `TESTNET` is `false` and `USE_TESTNET` is `true`
- **THEN** the selected environment is production

#### Scenario: No flag defined
- **WHEN** neither `TESTNET` nor `USE_TESTNET` is defined
- **THEN** the selected environment is production

### Requirement: Credential pair selection
The system SHALL resolve credentials as an all-or-nothing pair for the selected environment. Testnet SHALL require `BINANCE_TEST_API_KEY` and `BINANCE_TEST_API_SECRET`; production SHALL require `BINANCE_PROD_API_KEY` and `BINANCE_PROD_API_SECRET`. A missing or whitespace-only value SHALL fail with an error that names the missing variable, and the system SHALL NOT fall back to the other environment's keys.

#### Scenario: Testnet credentials resolved
- **WHEN** testnet is selected and both test key variables are non-empty
- **THEN** the client receives the test key pair and the testnet flag

#### Scenario: Production credentials resolved
- **WHEN** production is selected and both production key variables are non-empty
- **THEN** the client receives the production key pair and a false testnet flag

#### Scenario: Selected key is missing
- **WHEN** production is selected but `BINANCE_PROD_API_SECRET` is absent or blank
- **THEN** startup fails with a missing-environment-variable error for that variable

### Requirement: Configuration is read from the working directory
The system SHALL resolve `config/.credentials.env`, `.env`, `config/*.json`, `ops/`, and `logs/` relative to the process working directory rather than relative to the executable.

#### Scenario: Service working directory
- **WHEN** the systemd unit starts the bot with `WorkingDirectory=%h/TradingBotFest`
- **THEN** configuration and state are read from that repository checkout

## Provenance

- `src/config.rs` implements file loading, flag parsing, and credential selection.
- `README.md` documents the expected variable names.
- `config/tradingbot.service` sets the working directory used by the service.

## Assumptions

- Operators supply credentials through the process environment or one of the two dotenv files; there is no secret manager integration.
- The absence of `TESTNET` is treated as an intentional production choice by the current code, not as a missing setting to reject.

## Known deviations

- Production is the default whenever the testnet flag is absent, false, misspelled, or empty. There is no explicit confirmation, environment banner gate, or refusal to start against production.
- The two dotenv files are both loaded if present; because existing variables are not overwritten, the first file supplies values and the second only fills gaps. This precedence is implicit in the loader, not documented for operators.
- Credentials are validated only for presence. API key validity and permissions are discovered from the first signed request or the initial ping.
