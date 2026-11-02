# Python → Rust migration notes

The original Python implementation is archived in `assets/old_python/` and is
no longer part of the running system. This document records how the two
versions line up, what is guaranteed compatible, and where the Rust port
deliberately differs.

## Entry point mapping

| Python | Rust | Purpose |
| --- | --- | --- |
| `wsbin.py` | `cargo run --bin bot` | user-data WebSocket listener, dispatches fills to strategies |
| `postCARDIAC.py` | `cargo run --bin cardiac` | CARDIAC strategy |
| `postLCD.py` | `cargo run --bin load_unload` | THE_LOAD_UNLOAD_GRID strategy |
| `postRECOVERYZONE.py` | `cargo run --bin recovery_zone` | RECOVERY_ZONE strategy |
| `cleanORDERS.py` | `cargo run --bin clean_orders` | cancel open orders |
| `package_common.py` | `src/orders.rs`, `src/util.rs`, `src/exchange/` | order posting/cancelling, formatting, exchange access |
| `package_connection.py` | `src/config.rs`, `src/exchange/client.rs` | credentials and signed REST client |
| `package_cardiac.py` | `src/strategies/cardiac.rs` | CARDIAC |
| `package_theloadunload.py` | `src/strategies/load_unload.rs` | THE_LOAD_UNLOAD_GRID |
| `package_recoveryzone.py` | `src/strategies/recovery_zone.rs` | RECOVERY_ZONE |

The interactive prompts (symbol, side, prices, quantities, defaults) are
unchanged, so existing runbooks still apply.

## State compatibility

`ops/{SYMBOL}.json` keeps the Python schema: same file names, same keys, same
nesting, same `status` strings (`NEW`, `FILLED`, `CANCELLED`). A position opened
by the Python bot can be taken over by the Rust bot without a migration step,
and the reverse is also true.

Formatting differences that do not affect readers:

- Python wrote `json.dump(..., indent=4, separators=(',', ':'))` (no space after
  `:`); Rust writes indented JSON with a space after `:`.
- Rust appends a trailing newline.
- Key order is preserved in both (Python `dict`, Rust `serde_json` with the
  `preserve_order` feature), so field order in the file is unchanged.

The strategy config files are also unchanged: `config/cardiac.json`,
`config/theloadunload.json`, `config/recoveryzone.json`. The `.toml` files in
`config/` are leftovers from an earlier experiment and are not read.

## Rounding

`round()` in Python rounds binary floats with ties-to-even. Rust's
`f64::round()` rounds half away from zero, so `src/util.rs` implements
`py_round()` using `round_ties_even`, with a `10^digits` scaling factor.

Caveat: Python's `round(x, n)` first converts to a decimal string and applies
correctly-rounded decimal rounding, while `py_round` multiplies by a power of
ten in binary floating point. For prices and quantities used here the two agree
on every value that matters, but a value exactly halfway between two
representable decimals can still differ in the last digit. All money values
sent to the exchange are rounded through `py_round` (or `round_to_tick`, which
uses the tick size), so this rarely matters in practice.

## Intentional behaviour fixes

These are Python bugs that would have prevented the corresponding feature from
working; the Rust port implements the intended behaviour.

1. **RECOVERY_ZONE config path.** Python read `config/recoveryzone.config`
   (a file that does not exist) and therefore started from an empty state. Rust
   reads `config/recoveryzone.json`, matching the other strategies.
   (`assets/old_python/package_recoveryzone.py`, `input_data`)

2. **CARDIAC take-over of an existing position.** Python built an event as
   `{"o": {"ps": ...}}` and passed it to `attend_message`, which immediately
   reads `message['o']['X']` and raised `KeyError`. Rust calls `attend_filled`
   directly, which is what the code intended.
   (`assets/old_python/package_cardiac.py`, end of `input_data`)

3. **THE LOAD UNLOAD take-profit / stop-loss classification.** The Python
   mapping keyed these on `('TAKE_PROFIT_MARKET', None, None)` and
   `('STOP_MARKET', None, None)`, but real events always carry `ps` and `S`, so
   the lookup returned `None` and the branches were unreachable. Rust classifies
   by order type. LIMIT fills keep the exact same GRID/UNLOAD mapping.
   (`assets/old_python/package_theloadunload.py`, `get_transaction_type`)

4. **RECOVERY_ZONE SHORT `lost_distance`.** Python computed
   `distance * target_factor + 1` instead of `distance * (target_factor + 1)`
   for the SHORT side, making it asymmetric with the LONG side (which used the
   parentheses). Rust uses the symmetric formula on both sides.
   (`assets/old_python/package_recoveryzone.py`, `generate_distances`)

5. **Grid loop termination.** `generate_grid` loops until the stop-loss price is
   crossed. With `grid_distance == 0` the Python loop never terminates and
   floods order lines; with a negative distance it walks the wrong way. Rust
   rejects `grid_distance <= 0`, stops on non-finite prices or quantities, and
   caps the grid at 10,000 lines with a warning.
   (`assets/old_python/package_theloadunload.py`, `generate_grid`)

6. **Errors are not swallowed silently.** Python wrapped several exchange calls
   in bare `try/except` and only logged at debug level (for example
   `update_current_position`), which could leave a position unprotected with no
   visible error. Rust propagates those errors to the caller, which logs them at
   ERROR level; the WebSocket loop still reconnects and keeps running.

## Implementation differences (same behaviour)

- `python-binance` is replaced by a hand-rolled signed REST client
  (`reqwest` + HMAC-SHA256) against the same `fapi` endpoints, and
  `tokio-tungstenite` for the user-data stream. Testnet and production base URLs
  match the Python client.
- Python's `ThreadPoolExecutor(max_workers=10)` fan-out is now a tokio
  `buffer_unordered(10)` stream; the 10-way concurrency for order posting and
  cancellation is preserved.
- The Python WebSocket dispatched every event into a shared thread pool with no
  ordering guarantee per symbol. Rust adds one async mutex per symbol so fills
  for the same symbol are applied in order, while different symbols still run
  concurrently (10 in flight).
- Logging still writes INFO to the console and DEBUG to `logs/positions.log`;
  the message text is kept as close to the original as practical.

## Not ported

- The SQLite schema in `migrations/` and the previous Rust DB layer were unused
  by the Python bot and are not wired into the Rust version.
- `openspec/changes/add-dca-safety-assistant/` describes a feature for the
  earlier Rust prototype that was deleted before this port; it is not
  implemented here.
