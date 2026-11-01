#[tokio::main]
async fn main() {
    println!("Initializing database...");
    
    match trading_bot_fest_rust::db::init().await {
        Ok(_) => println!("Database initialized successfully."),
        Err(e) => eprintln!("Failed to initialize database: {}", e),
    }
}
