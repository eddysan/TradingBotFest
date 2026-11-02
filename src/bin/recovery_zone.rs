use anyhow::Result;
use trading_bot_fest::config;
use trading_bot_fest::exchange::BinanceClient;
use trading_bot_fest::logging;
use trading_bot_fest::strategies::recovery_zone;

#[tokio::main]
async fn main() -> Result<()> {
    logging::init("logs/positions.log")?;

    let client = BinanceClient::connect(config::load_credentials()?).await?;

    let symbol = recovery_zone::input_data(&client).await?;
    let mut zone = recovery_zone::RecoveryZone::new(&symbol)?;
    zone.post_orders(&client).await?;

    Ok(())
}
