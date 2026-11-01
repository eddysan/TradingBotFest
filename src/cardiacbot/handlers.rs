use tokio::sync::mpsc;
use crate::core::commands::{DbCommand, ExchangeCommands};
use super::state::CardiacState;
use super::logic;
use super::{PriceUpdate, CardiacCommand};

pub async fn handle_price_update(
    price: PriceUpdate, 
    state: &mut CardiacState,
    tx_db: &mpsc::Sender<DbCommand>,
    tx_ex: &mpsc::Sender<ExchangeCommands>
) {
    // 1. Ejecutar lógica
    if logic::check_entry_condition(price.value, state.last_rsi) && !state.is_in_position {
        // 2. Enviar orden al exchange
        let _ = tx_ex.send(ExchangeCommands::PlaceOrder { 
            symbol: "BTCUSDT".to_string(),
            side: "LONG".to_string(),
            order_type: "MARKET".to_string(),
            quantity: "0.001".to_string(),
            price: None,
        }).await;

        // 3. Notificar a la DB
        let _ = tx_db.send(DbCommand::PostLog {
            level: "INFO".to_string(),
            event: "Entrada Cardiac".to_string(),
            symbol: Some("BTCUSDT".to_string()),
            strategy: Some("CARDIAC".to_string()),
            message: Some("Condición de entrada cumplida".to_string()),
            payload: None,
        }).await;
        
        state.is_in_position = true;
    }
}

pub async fn handle_core_command(
    cmd: CardiacCommand,
    state: &mut CardiacState,
    tx_db: &mpsc::Sender<DbCommand>,
    tx_ex: &mpsc::Sender<ExchangeCommands>,
) {
    match cmd {
        CardiacCommand::Stop => println!("Stopping strategy"),
        CardiacCommand::Pause => println!("Pausing strategy"),
        CardiacCommand::Resume => println!("Resuming strategy"),
        CardiacCommand::CreateEntryOrder {
            symbol,
            side,
            price,
            quantity,
        } => {
            println!(
                "Creating Entry Order: {} {} {} {}",
                symbol, side, price, quantity
            );

            // 1. Enviar orden al exchange
            let _ = tx_ex
                .send(ExchangeCommands::PlaceOrder {
                    symbol: symbol.clone(),
                    side: side.clone(),
                    order_type: "LIMIT".to_string(),
                    quantity: quantity.to_string(),
                    price: Some(price.to_string()),
                })
                .await;

            // 2. Notificar a la DB
            let _ = tx_db
                .send(DbCommand::PostLog {
                    level: "INFO".to_string(),
                    event: "Manual Entry".to_string(),
                    symbol: Some(symbol),
                    strategy: Some("CARDIAC".to_string()),
                    message: Some("Orden manual generada vía API".to_string()),
                    payload: None,
                })
                .await;

            state.is_in_position = true;
        }
    }
}