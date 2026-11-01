use crate::core::commands::{PriceUpdate, ExchangeCommands, DbCommand};
use tokio::sync::{broadcast, mpsc};

pub async fn run(
    mut rx_prices: broadcast::Receiver<PriceUpdate>,
    _tx_ex: mpsc::Sender<ExchangeCommands>,
    _tx_db: mpsc::Sender<DbCommand>,
) {
    println!("Load/Unload strategy task started...");
    while let Ok(_price_update) = rx_prices.recv().await {
        // Implementation of Load/Unload logic
    }
}
