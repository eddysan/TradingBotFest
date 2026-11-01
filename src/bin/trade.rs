use trading_bot_fest_rust::core::common::{
    prompt_price, prompt_quantity, prompt_side, prompt_symbol,
};

#[tokio::main]
async fn main() -> anyhow::Result<()> {
    println!("Starting TRADING_CLI...");

    // by now, we only use CARDIAC strategy
    // let strategy_name = prompt_strategy("Strategy (1. CARDIAC, 2. THE_LOAD_UNLOAD, 3. RECOVERY_ZONE): ");
    // getting symbol, side, price and quantity by terminal
    let symbol = prompt_symbol("Symbol (BTC): ");
    let side = prompt_side("Side (LONG|SHORT): ");
    let price = prompt_price("Price: ");
    let quantity = prompt_quantity("Quantity: ");

    // getting config file for cardiac strategy
    let config = trading_bot_fest_rust::cardiacbot::cardiac_conf::CardiacConfig::from_file(
        "config/cardiac.toml",
    )?;

    // Build the URL for the API endpoint
    let url = format!(
        "{}/cardiac/start_strategy",
        std::env::var("REST_API_URL").unwrap_or_else(|_| "http://localhost:3000".to_string()),
    );

    let client = reqwest::Client::new();
    let payload = trading_bot_fest_rust::core::commands::CardiacInitStrategy {
        strategy: "CARDIAC".to_string(),
        symbol: symbol.to_string(),
        side: side.to_string(),
        price: price.to_string(),
        quantity: quantity.to_string(),
        config,
    };

    println!("Sending request to API...");
    let res = client.post(&url).json(&payload).send().await?;

    if res.status().is_success() {
        println!("  ✓ Order sent successfully!");
        let body = res.text().await?;
        println!("  Response: {}", body);
    } else {
        println!("  ✗ Failed to send order: {}", res.status());
        let body = res.text().await?;
        println!("  Error: {}", body);
    }

    Ok(())
}
