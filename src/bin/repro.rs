use trading_bot_fest_rust::exchange_service::helpers::sync_symbol;
use trading_bot_fest_rust::db;

#[tokio::main]
async fn main() {
    println!("Initializing DB...");
    db::init().await.expect("Failed to initialize database");
    let pool = db::pool();
    println!("DB Initialized.");
    
    let symbol = "BTCUSDT";
    println!("Syncing symbol {} from Binance...", symbol);
    match sync_symbol(pool, symbol).await {
        Ok(_) => println!("Successfully synced {}", symbol),
        Err(e) => println!("Error: {}", e),
    }
}
