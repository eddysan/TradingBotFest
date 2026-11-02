use anyhow::Result;
use std::sync::Arc;
use trading_bot_fest::config;
use trading_bot_fest::exchange::ws;
use trading_bot_fest::exchange::BinanceClient;
use trading_bot_fest::logging;

#[tokio::main]
async fn main() -> Result<()> {
    logging::init("logs/positions.log")?;

    let client = Arc::new(BinanceClient::connect(config::load_credentials()?).await?);
    ws::run(client).await?;

    Ok(())
}
