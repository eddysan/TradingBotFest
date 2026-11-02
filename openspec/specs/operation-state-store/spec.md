# Operation State Store Specification

## Purpose

Defines the persistent per-symbol state document used to survive restarts and to hand positions between the Python and Rust implementations, including file layout, accessors, write format, and concurrency behavior.

## Requirements

### Requirement: State file location
The system SHALL store one JSON document per symbol at `ops/{SYMBOL}.json`, resolved relative to the working directory, and SHALL treat the directory as runtime data excluded from version control.

#### Scenario: Existing symbol
- **WHEN** a strategy loads `BTCUSDT`
- **THEN** it reads `ops/BTCUSDT.json`

#### Scenario: New symbol
- **WHEN** a strategy writes a symbol that has no state file
- **THEN** the file is created under `ops/`

### Requirement: Optional and required reads
The system SHALL distinguish a missing file from invalid JSON. Optional reads SHALL return no value for a missing file, required reads SHALL fail with a missing-configuration error naming the path, and invalid JSON SHALL fail with a parse error.

#### Scenario: Missing optional file
- **WHEN** a caller performs an optional read of a path that does not exist
- **THEN** the result is an empty value rather than an error

#### Scenario: Required file missing
- **WHEN** a strategy requires `ops/BTCUSDT.json` and it does not exist
- **THEN** the call fails with the missing path in the error

#### Scenario: Corrupt file
- **WHEN** the file contains invalid JSON
- **THEN** the call fails with a JSON parse error

### Requirement: Write format
The system SHALL create the target directory when needed, write indented JSON with four spaces per level, preserve insertion order, append a trailing newline, and replace the entire target file.

#### Scenario: State is saved
- **WHEN** a strategy saves its grid
- **THEN** `ops/{SYMBOL}.json` is rewritten with the four-space format and a trailing newline

#### Scenario: Directory absent
- **WHEN** `ops/` does not exist at save time
- **THEN** it is created before writing

### Requirement: Typed accessors
The system SHALL read nested values by key path and SHALL support numbers supplied as JSON numbers or numeric strings, booleans, strings, arrays, and optional values with defaults. Required accessors SHALL fail with the path and symbol when a key is missing or has the wrong type. Numeric-to-integer conversion SHALL truncate toward zero.

#### Scenario: Numeric string
- **WHEN** a stored price is the string `"100.5"`
- **THEN** the numeric accessor returns `100.5`

#### Scenario: Missing required key
- **WHEN** a required key is absent
- **THEN** the accessor fails with the dotted path and symbol context

#### Scenario: Default for optional key
- **WHEN** an optional key is absent
- **THEN** the supplied default is returned

### Requirement: Strategy lookup
The system SHALL expose a lookup that returns the document's top-level `strategy` string, or no value when the file is missing, unreadable, or has no string strategy field.

#### Scenario: Strategy present
- **WHEN** the document contains `"strategy": "CARDIAC"`
- **THEN** the lookup returns `CARDIAC`

#### Scenario: Strategy absent
- **WHEN** the document exists without a strategy field
- **THEN** the lookup returns no value

### Requirement: Whole-document replacement
Each save SHALL rewrite the complete document. Merging a strategy's updates into an existing document SHALL be the responsibility of the caller, and the store SHALL NOT merge, lock, version, or compare-and-swap documents.

#### Scenario: Two writers
- **WHEN** two processes save the same symbol concurrently
- **THEN** the last write replaces the other and no conflict is reported

#### Scenario: Caller merge
- **WHEN** a caller wants to preserve keys owned by another strategy
- **THEN** it must read the document, merge in memory, and write the whole result

## Provenance

- `src/store/mod.rs` implements reading, pretty writing, typed accessors, strategy lookup, and the `Grid` wrapper.
- `MIGRATION.md` records schema compatibility with the Python `ops/{SYMBOL}.json` files.
- `config/cardiac.json`, `config/theloadunload.json`, and `config/recoveryzone.json` are templates for the stored shapes.

## Assumptions

- The document shape differs by strategy and is intentionally untyped at the store layer.
- The Python and Rust versions must be able to read each other's state, so key names, nesting, and status strings are preserved.

## Known deviations

- Writes are not atomic: there is no temporary file plus rename, no fsync, and no backup. A crash during a write can leave a truncated document.
- There is no file locking or inter-process coordination. The long-running listener and an interactive strategy binary can both write `ops/{SYMBOL}.json`, and the later write silently discards the other's changes.
- The store performs no schema validation. Missing keys fail at the point a strategy reads them, which may be after orders have already been placed.
- Status strings (`NEW`, `FILLED`, `CANCELLED`) have no enum type or validation; unexpected values are handled ad hoc by each strategy.
- Numeric values are read into `f64`, and integer conversion truncates rather than rejects a fractional value.
