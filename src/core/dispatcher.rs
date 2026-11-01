use crate::core::commands::{PriceUpdate, StrategyCommand};
use std::collections::HashMap;
use tokio::sync::mpsc;
use tokio::sync::broadcast;

pub struct Dispatcher {
    // Channel to receive price updates from Market Data Service
    rx_prices: mpsc::Receiver<PriceUpdate>,
    // Channel to receive management commands (Start/Stop) from CLI/Core
    rx_commands: mpsc::Receiver<StrategyCommand>,
    // Map of active strategy broadcast channels, keyed by symbol
    strategy_txs: HashMap<String, broadcast::Sender<PriceUpdate>>,
}

impl Dispatcher {
    pub fn new(
        rx_prices: mpsc::Receiver<PriceUpdate>,
        rx_commands: mpsc::Receiver<StrategyCommand>,
    ) -> Self {
        Self {
            rx_prices,
            rx_commands,
            strategy_txs: HashMap::new(),
        }
    }

    pub async fn run(mut self) {
        println!("Dispatcher started...");
        loop {
            tokio::select! {
                // Handle new price updates
                Some(price_update) = self.rx_prices.recv() => {
                    if let Some(tx) = self.strategy_txs.get(&price_update.symbol) {
                        // Broadcast price to all listening services for this symbol
                        let _ = tx.send(price_update);
                    }
                }
                // Handle strategy management commands
                Some(cmd) = self.rx_commands.recv() => {
                    match cmd {
                        StrategyCommand::Start { symbol, strategy_name, config_path } => {
                            println!("Starting strategy {} for {} with config {}", strategy_name, symbol, config_path);
                            // Ensure a broadcast channel exists for this symbol
                            self.strategy_txs.entry(symbol).or_insert_with(|| {
                                let (tx, _) = broadcast::channel(100);
                                tx
                            });
                        }
                        StrategyCommand::Stop { symbol } => {
                            println!("Stopping strategies for {}", symbol);
                            self.strategy_txs.remove(&symbol);
                        }
                    }
                }
            }
        }
    }

    pub fn subscribe(&mut self, symbol: &str) -> broadcast::Receiver<PriceUpdate> {
        let tx = self.strategy_txs.entry(symbol.to_string()).or_insert_with(|| {
            let (tx, _) = broadcast::channel(100);
            tx
        });
        tx.subscribe()
    }
}
