use tokio::sync::mpsc;
use trading_bot_fest_rust::cardiacbot;
use trading_bot_fest_rust::cardiacbot::CardiacCommand;
use trading_bot_fest_rust::core::commands::{
    DbCommand, ExchangeCommands, PriceUpdate, RestApiCommands, StrategyCommand,
};
use trading_bot_fest_rust::core::dispatcher::Dispatcher;
use trading_bot_fest_rust::db;
use trading_bot_fest_rust::exchange_service;
use trading_bot_fest_rust::rest_api_service;

#[tokio::main]
async fn main() -> anyhow::Result<()> {
    println!("Starting Trading Bot Fest Core Engine...");

    // init database channel
    let (tx_db_cmd, rx_db_cmd) = mpsc::channel::<DbCommand>(100);
    // init rest api channel
    let (tx_rest_api_cmd, rx_rest_api_cmd) = mpsc::channel::<RestApiCommands>(100);
    // init cardiacbot command channel
    let (tx_cardiac_cmd, rx_cardiac_cmd) = mpsc::channel::<CardiacCommand>(100);
    // init prices channel
    let (tx_prices, rx_prices) = mpsc::channel::<PriceUpdate>(100);
    // init strategy commands channel
    let (tx_strat_cmds, rx_strat_cmds) = mpsc::channel::<StrategyCommand>(100);
    // cardiacbot price channel
    let (tx_cardiac_prices, rx_cardiac_prices) = mpsc::channel::<cardiacbot::PriceUpdate>(100);

    // init database service
    println!("Launching DB Service...");
    let db_handle = tokio::spawn(async move {
        if let Err(e) = db::run(rx_db_cmd).await {
            eprintln!("DB Service error: {}", e);
        }
    });

    // Launch REST API service
    println!("Launching REST API Services...");
    let tx_rest_api_cmd_for_service = tx_rest_api_cmd.clone();
    let rest_api_handle = tokio::spawn(async move {
        if let Err(e) = rest_api_service::run(tx_rest_api_cmd_for_service).await {
            eprintln!("REST API Service error: {}", e);
        }
    });

    // Launch CardiacBot Service
    println!("Launching CardiacBot Service...");
    let tx_db_for_cardiac = tx_db_cmd.clone();
    // For now we don't have a real exchange sender for orders, we should probably create one
    let (tx_ex_cmd, _rx_ex_cmd) = mpsc::channel::<ExchangeCommands>(100);
    let cardiac_handle = tokio::spawn(async move {
        cardiacbot::run(
            rx_cardiac_cmd,
            rx_cardiac_prices,
            tx_db_for_cardiac,
            tx_ex_cmd,
        )
        .await;
    });

    // Route REST API commands to strategies
    let tx_cardiac_cmd_for_router = tx_cardiac_cmd.clone();
    let api_router_handle = tokio::spawn(async move {
        let mut rx = rx_rest_api_cmd;
        while let Some(cmd) = rx.recv().await {
            match cmd {
                RestApiCommands::CardiacEntryOrder {
                    strategy,
                    symbol,
                    side,
                    price,
                    quantity,
                    config,
                    tx,
                } => {
                    if strategy == "CARDIAC" {
                        println!("API Router: cardiac: Received Cardiac Symbol: {}", symbol);
                        println!("API Router: cardiac: Received Cardiac Side: {}", side);
                        println!("API Router: cardiac: Received Cardiac Price: {}", price);
                        println!(
                            "API Router: cardiac: Received Cardiac Quantity: {}",
                            quantity
                        );
                        println!(
                            "API Router: cardiac: Received Cardiac Config: {:#?}",
                            config
                        );
                        let cardiac_cmd = CardiacCommand::CreateEntryOrder {
                            symbol,
                            side,
                            price: price.parse().unwrap_or(0.0),
                            quantity: quantity.parse().unwrap_or(0.0),
                        };
                        let _ = tx_cardiac_cmd_for_router.send(cardiac_cmd).await;
                        let _ = tx.send(());
                    }
                }
            }
        }
    });

    // 4. Start Market Data (Websocket) Service
    println!("Launching Market Data Websocket...");
    let ws_handle = tokio::spawn(async move {
        exchange_service::websocket::run(tx_prices).await;
    });

    // 5. Start Dispatcher (Routes prices to strategies)
    println!("Launching Dispatcher...");
    let dispatcher = Dispatcher::new(rx_prices, rx_strat_cmds);
    let dispatcher_handle = tokio::spawn(async move {
        dispatcher.run().await;
    });

    // 6. Monitor services
    tokio::select! {
        _ = db_handle => println!("DB Service exited"),
        _ = rest_api_handle => println!("REST API Service exited"),
        _ = cardiac_handle => println!("CardiacBot Service exited"),
        _ = api_router_handle => println!("API Router exited"),
        _ = ws_handle => println!("Websocket Service exited"),
        _ = dispatcher_handle => println!("Dispatcher exited"),
    }

    Ok(())
}
