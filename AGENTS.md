# Trading Bot Fest

Rust port of the original Python Binance futures trading bot. The original
Python implementation is archived in `assets/old_python/` for reference and is
no longer run.

## Build & Run

```bash
cargo build                      # debug build
cargo build --release            # release build used by systemd
cargo test                       # unit tests

cargo run --bin bot              # user-data WebSocket listener (service entrypoint)
cargo run --bin cardiac          # CARDIAC strategy
cargo run --bin load_unload      # THE_LOAD_UNLOAD_GRID strategy
cargo run --bin recovery_zone    # RECOVERY_ZONE strategy
cargo run --bin clean_orders     # cancel open orders for a symbol
```

All binaries are interactive: they prompt on stdin for symbol, side, prices and
quantity, exactly like the Python version.

## Project Structure

```
src/
├── bin/              # bot.rs, cardiac.rs, load_unload.rs, recovery_zone.rs, clean_orders.rs
├── exchange/         # signed REST client (client.rs), filters, models, user-data ws.rs
├── strategies/       # cardiac.rs, load_unload.rs, recovery_zone.rs
├── store/            # ops/{SYMBOL}.json state access
├── config.rs         # credentials from config/.credentials.env or .env
├── orders.rs         # order placement, cancellation, filtering
├── logging.rs        # console INFO + logs/positions.log DEBUG
└── util.rs           # rounding, distance, prompts
config/               # strategy defaults (*.json) and tradingbot.service
ops/                  # live per-symbol state, created at runtime (gitignored)
assets/old_python/    # archived Python implementation (not run)
migrations/           # SQLite schema, unused by the bot
```

## Environment

`config/.credentials.env` (or `.env`) must provide:

- `TESTNET=True` (or `USE_TESTNET`) to use the testnet
- `BINANCE_TEST_API_KEY` / `BINANCE_TEST_API_SECRET` for testnet
- `BINANCE_PROD_API_KEY` / `BINANCE_PROD_API_SECRET` for production

## Notes

- `ops/{SYMBOL}.json` keeps the exact Python schema. A position opened by the
  Python version can be picked up by the Rust version and vice versa.
- `config/*.toml` are leftovers from an older experiment; the bot reads
  `config/cardiac.json`, `config/theloadunload.json` and
  `config/recoveryzone.json`.
- `cargo test` covers rounding, filters, order filtering and the pure
  strategy calculations. Nothing here is exercised against a live exchange.
- See `MIGRATION.md` for the intentional behaviour fixes made during the port.
