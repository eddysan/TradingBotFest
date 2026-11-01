pub mod cardiac;
pub mod load_unload;
pub mod recovery_zone;

use crate::core::commands::{PriceUpdate, ExchangeCommands, DbCommand};
use tokio::sync::{broadcast, mpsc};

/// A trait for strategies that can be run as a service task.
pub trait TradingStrategy {
    fn run(
        &mut self,
        rx_prices: broadcast::Receiver<PriceUpdate>,
        tx_ex: mpsc::Sender<ExchangeCommands>,
        tx_db: mpsc::Sender<DbCommand>,
    ) -> tokio::task::JoinHandle<()>;
}
