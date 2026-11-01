pub mod handlers;
pub mod helpers;
pub mod models;
pub mod websocket;

use crate::core::commands::ExchangeCommands;
use crate::exchange_service::helpers::get_binance_client;
use tokio::sync::mpsc;

pub async fn run(mut rx_exchange_cmd: mpsc::Receiver<ExchangeCommands>) {
    let client = get_binance_client().await.unwrap();

    while let Some(cmd) = rx_exchange_cmd.recv().await {
        handlers::handle_exchange_commands(&client, cmd).await;
    }
}
