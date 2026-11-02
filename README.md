# trading_bot_fest

Trading Bot Festival, many trading bots helping us to trade.

This is a Rust implementation of the original Python bot. It talks to Binance
USDT-M futures through signed REST calls and a user-data WebSocket, and keeps
its live state in `ops/{SYMBOL}.json`.

## Requirements

- Rust 1.80+ (`cargo`)
- Binance futures API credentials (testnet or production)

## Setup

```bash
cp config/.credentials.env.example config/.credentials.env   # if present
cargo build --release
```

`config/.credentials.env` (or `.env`) needs:

```
TESTNET=True
BINANCE_TEST_API_KEY=...
BINANCE_TEST_API_SECRET=...
BINANCE_PROD_API_KEY=...
BINANCE_PROD_API_SECRET=...
```

## Usage

```bash
# start the WebSocket listener (systemd runs this)
cargo run --release --bin bot

# place a new position with one of the strategies
cargo run --release --bin cardiac
cargo run --release --bin load_unload
cargo run --release --bin recovery_zone

# cancel open orders for a symbol
cargo run --release --bin clean_orders
```

Each strategy prompts for the symbol, side and its own prices/quantities.

## Deployment

`update.sh` pulls `main`, runs `cargo build --release`, installs
`config/tradingbot.service` as a user service and restarts it.
`.github/workflows/deploy.yml` invokes that script over SSH on every push to
`main`.

## Layout

| Path | Purpose |
| --- | --- |
| `src/exchange/` | Binance REST client, symbol filters, user-data stream |
| `src/strategies/` | CARDIAC, THE_LOAD_UNLOAD_GRID, RECOVERY_ZONE |
| `src/orders.rs` | Order posting, cancellation and filtering |
| `src/store/` | `ops/{SYMBOL}.json` access |
| `config/` | Strategy defaults and the systemd unit |
| `assets/old_python/` | Archived Python implementation |

See `MIGRATION.md` for the differences from the Python version.
