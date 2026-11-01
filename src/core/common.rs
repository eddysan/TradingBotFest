use std::io::{self, Write};

use rust_decimal::Decimal;

/// Prompt message to terminal and return symbol input.
/// Appends "USDT" to the input if not ending with "USDT".
pub fn prompt_symbol(label: &str) -> String {
    print!("{label}");
    io::stdout().flush().unwrap();
    let mut buf = String::new();
    io::stdin().read_line(&mut buf).unwrap();
    let mut buf = buf.trim().to_uppercase();
    if !buf.ends_with("USDT") {
        buf.push_str("USDT");
    }
    // TODO: In the future we need to implement the symbol validation using exchange api
    buf
}

/// Prompt message to terminal and return side input.
pub fn prompt_side(label: &str) -> String {
    print!("{label}");
    io::stdout().flush().unwrap();
    let mut buf = String::new();
    io::stdin().read_line(&mut buf).unwrap();
    let buf = buf.trim().to_uppercase();
    if buf != "LONG" && buf != "SHORT" {
        println!("Invalid side, try again.");
        prompt_side(label)
    } else {
        buf
    }
}

/// Prompt message to terminal and return strategy input.
pub fn prompt_strategy(label: &str) -> String {
    print!("{label}");
    io::stdout().flush().unwrap();
    let mut buf = String::new();
    io::stdin().read_line(&mut buf).unwrap();
    match buf.trim() {
        "1" => "CARDIAC".to_string(),
        "2" => "THE_LOAD_UNLOAD".to_string(),
        "3" => "RECOVERY_ZONE".to_string(),
        _ => {
            println!("Invalid strategy, try again.");
            prompt_strategy(label)
        }
    }
}

/// Prompt message to terminal and return price input converted to Decimal.
pub fn prompt_price(label: &str) -> Decimal {
    print!("{label}");
    io::stdout().flush().unwrap();
    let mut buf = String::new();
    io::stdin().read_line(&mut buf).unwrap();
    let price: Decimal = buf.trim().parse().unwrap();
    price
    // TODO: in the future convert using price_filter of the correspondent symbol
}

pub fn prompt_quantity(label: &str) -> Decimal {
    print!("{label}");
    io::stdout().flush().unwrap();
    let mut buf = String::new();
    io::stdin().read_line(&mut buf).unwrap();
    let quantity: Decimal = buf.trim().parse().unwrap();
    quantity
    // TODO: in the future convert using stepSize of the correspondent symbol
}
