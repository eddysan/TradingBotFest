use crate::core::commands::{PriceUpdate, ExchangeCommands, DbCommand};
use tokio::sync::{broadcast, mpsc};

pub async fn run(
    mut rx_prices: broadcast::Receiver<PriceUpdate>,
    tx_ex: mpsc::Sender<ExchangeCommands>,
    tx_db: mpsc::Sender<DbCommand>,
) {
    println!("Cardiac strategy task started...");
    while let Ok(price_update) = rx_prices.recv().await {
        // Implementation of Cardiac logic
        if price_update.price < 60000.0 {
            let _ = tx_db.send(DbCommand::PostLog {
                level: "INFO".to_string(),
                event: "Cardiac Entry".to_string(),
                symbol: Some(price_update.symbol.clone()),
                strategy: Some("CARDIAC".to_string()),
                message: Some(format!("Price {} triggered entry", price_update.price)),
                payload: None,
            }).await;
        }
    }
}
