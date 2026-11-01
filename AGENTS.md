# Trading Bot Fest Rust

## Build & Run

```bash
cargo build
cargo run --bin init_db       # Initialize SQLite database
cargo run --bin repro         # Sync symbol from Binance
cargo run --bin postcardiac   # Run CARDIAC trading strategy
```

## Project Structure

```
src/
├── bin/              # init_db.rs, repro.rs, postcardiac.rs
├── core/             # exchange_service.rs, logger.rs, common.rs
├── db/               # db_service.rs, models.rs
└── strategies/       # cardiac.rs, recoveryzone.rs, loadunload.rs
config/cardiac.toml  # Strategy config
migrations/          # SQLite schema
```

## Environment

`.env` requires: `DATABASE_URL`, `USE_TESTNET`, `BINANCE_TEST_*` keys

## Notes

- `db::init()` runs migrations automatically
- `strategies/cardiac.rs` is empty (needs implementation)
- No CI/test suite configured
