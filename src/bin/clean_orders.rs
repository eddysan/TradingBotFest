use anyhow::Result;
use trading_bot_fest::config;
use trading_bot_fest::exchange::BinanceClient;
use trading_bot_fest::logging;
use trading_bot_fest::orders::{clean_all_open_orders, clean_open_orders};
use trading_bot_fest::util::prompt;

#[tokio::main]
async fn main() -> Result<()> {
    logging::init("logs/positions.log")?;

    let client = BinanceClient::connect(config::load_credentials()?).await?;

    let base = prompt("Symbol (BTC): ")?.to_uppercase();
    let symbol = format!("{base}USDT");

    let side = prompt("Side to clean (LONG|SHORT|ALL): ")?.to_uppercase();
    let side = if side.is_empty() {
        "ALL".to_string()
    } else {
        side
    };

    if side == "ALL" {
        clean_all_open_orders(&client, &symbol).await?;
    } else {
        clean_open_orders(&client, &symbol, &side).await?;
    }

    Ok(())
}
