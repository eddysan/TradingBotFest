use anyhow::Result;
use trading_bot_fest::config;
use trading_bot_fest::exchange::BinanceClient;
use trading_bot_fest::logging;
use trading_bot_fest::strategies::cardiac;

#[tokio::main]
async fn main() -> Result<()> {
    logging::init("logs/positions.log")?;

    let client = BinanceClient::connect(config::load_credentials()?).await?;

    if let Some(symbol) = cardiac::input_data(&client).await? {
        let mut grid = cardiac::CardiacGrid::new(&symbol)?;
        grid.post_order(&client).await?;
    }

    Ok(())
}
