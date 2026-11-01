mod handlers;
mod logic;
mod state;
pub mod cardiac_conf;

use tokio::sync::mpsc;
use crate::core::commands::{DbCommand, ExchangeCommands};

#[derive(Debug)]
pub struct PriceUpdate {
    pub value: f64,
}

#[derive(Debug)]
pub enum CardiacCommand {
    Stop,
    Pause,
    Resume,
    CreateEntryOrder {
        symbol: String,
        side: String,
        price: f64,
        quantity: f64,
    },
}

pub async fn run(
    mut rx_core: mpsc::Receiver<CardiacCommand>,
    mut rx_prices: mpsc::Receiver<PriceUpdate>,
    tx_db: mpsc::Sender<DbCommand>,
    tx_ex: mpsc::Sender<ExchangeCommands>,
) {
    // Inicializamos el estado interno de la estrategia
    let mut estado = state::CardiacState::new();

    loop {
        tokio::select! {
            // Escuchar comandos (Pausar, Detener, Cambiar parámetros)
            Some(cmd) = rx_core.recv() => {
                handlers::handle_core_command(cmd, &mut estado, &tx_db, &tx_ex).await;
            }
            // Escuchar precios en tiempo real de Binance
            Some(price) = rx_prices.recv() => {
                handlers::handle_price_update(price, &mut estado, &tx_db, &tx_ex).await;
            }
        }
    }
}
