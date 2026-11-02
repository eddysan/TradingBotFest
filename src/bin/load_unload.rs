use anyhow::Result;
use trading_bot_fest::config;
use trading_bot_fest::exchange::BinanceClient;
use trading_bot_fest::logging;
use trading_bot_fest::strategies::load_unload;

#[tokio::main]
async fn main() -> Result<()> {
    logging::init("logs/positions.log")?;

    let client = BinanceClient::connect(config::load_credentials()?).await?;

    let symbol = load_unload::input_data(&client).await?;
    let mut grid = load_unload::LUGrid::new(&symbol)?;
    grid.post_order(&client).await?;

    Ok(())
}
