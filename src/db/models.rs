// /src/db/models.rs
//! This model acts as a bridge between the database and the application.
//! It is used to store and retrieve data from the database.

use rust_decimal::Decimal;
use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Log {
    pub id: i64,
    pub created_at: String,
    pub level: String,
    pub event: String,
    pub symbol: Option<String>,
    pub strategy: Option<String>,
    pub message: Option<String>,
    pub payload: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Symbol {
    pub id: i64,
    pub symbol: String,
    pub status: String,
    pub base_asset: String,
    pub quote_asset: String,
    pub price_precision: i32,
    pub quantity_precision: i32,
    pub tick_size: Decimal,
    pub step_size: Decimal,
    pub min_quantity: Decimal,
    pub max_quantity: Decimal,
    pub created_at: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Strategy {
    pub id: i64,
    pub name: String,
    pub symbol: String,
    pub timeframe: String,
    pub is_active: bool,
    pub parameters: Option<String>,
    pub created_at: String,
    pub updated_at: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Position {
    pub id: i64,
    pub symbol: String,
    pub position_side: String,
    pub position_amt: Decimal,
    pub entry_price: Decimal,
    pub break_even_price: Decimal,
    pub mark_price: Decimal,
    pub unrealized_profit: Decimal,
    pub liquidation_price: Decimal,
    pub isolated_margin: Decimal,
    pub notional: Decimal,
    pub margin_asset: String,
    pub isolated_wallet: Decimal,
    pub initial_margin: Decimal,
    pub maint_margin: Decimal,
    pub position_initial_margin: Decimal,
    pub open_order_initial_margin: Decimal,
    pub adl: i32,
    pub bid_notional: i32,
    pub ask_notional: i64,
    pub update_time: i64,
    pub leverage: i32,
    pub max_notional_value: f64,
    pub margin_type: String,
    pub is_auto_add_margin: bool,
    pub status: String,
    pub created_at: String,
    pub updated_at: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Order {
    pub id: i64,
    pub symbol: Option<String>,
    pub strategy: Option<String>,
    pub label: Option<String>,
    pub position_side: Option<String>,
    pub order_id: Option<i64>,
    pub client_order_id: Option<String>,
    pub label_order: i32,
    pub order_type: Option<String>,
    pub side: Option<String>,
    pub price: Decimal,
    pub avg_price: Decimal,
    pub orig_qty: Decimal,
    pub executed_qty: Decimal,
    pub status: Option<String>,
    pub time_in_force: String,
    pub reduce_only: bool,
    pub update_time: i64,
    pub created_at: String,
    pub updated_at: String,
}
