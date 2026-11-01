use crate::db::models::{Position, Symbol};
use tokio::sync::oneshot;

pub enum DbCommand {
    PostLog {
        level: String,
        event: String,
        symbol: Option<String>,
        strategy: Option<String>,
        message: Option<String>,
        payload: Option<String>,
    },
    PostSymbol {
        symbol: String,
        status: String,
        base_asset: String,
        quote_asset: String,
        price_precision: i32,
        quantity_precision: i32,
        tick_size: String,
        step_size: String,
        min_quantity: String,
        max_quantity: String,
    },
    GetSymbol {
        symbol: String,
        tx: oneshot::Sender<Option<Symbol>>,
    },
    PostPosition {
        symbol: String,
        position_side: String,
        position_amt: String,
        entry_price: String,
        break_even_price: String,
        mark_price: String,
        unrealized_profit: String,
        liquidation_price: String,
        isolated_margin: String,
        notional: String,
        margin_asset: String,
        isolated_wallet: String,
        initial_margin: String,
        maint_margin: String,
        position_initial_margin: String,
        open_order_initial_margin: String,
        adl: i32,
        bid_notional: i32,
        ask_notional: i64,
        update_time: i64,
        leverage: i32,
        max_notional_value: f64,
        margin_type: String,
        is_auto_add_margin: bool,
        status: String,
    },
    GetPosition {
        symbol: String,
        tx: oneshot::Sender<Vec<Position>>,
    },
    PostOrder {
        symbol: String,
        order_side: String,
        order_type: String,
        price: String,
        quantity: String,
        status: String,
    },
    GetOrder {
        symbol: String,
    },
}

pub enum ExchangeCommands {
    // get symbol information
    GetSymbolInfo {
        symbol: String,
        tx: oneshot::Sender<Vec<Symbol>>,
    },

    // getting exchange information, including wallet info
    GetExchangeInfo {
        tx: oneshot::Sender<Vec<Symbol>>,
    },

    // Place an order
    PlaceOrder {
        symbol: String,
        side: String,
        order_type: String,
        quantity: String,
        price: Option<String>,
    },
}

pub enum RestApiCommands {
    CardiacEntryOrder {
        strategy: String,
        symbol: String,
        side: String,
        price: String,
        quantity: String,
        config: CardiacConfig,
        tx: oneshot::Sender<()>,
    },
}

#[derive(Debug, Clone)]
pub struct PriceUpdate {
    pub symbol: String,
    pub price: f64,
    pub timestamp: i64,
}

#[derive(Debug, Clone, serde::Serialize, serde::Deserialize)]
pub enum StrategyCommand {
    Start {
        symbol: String,
        strategy_name: String,
        config_path: String,
    },
    Stop {
        symbol: String,
    },
}

use serde::{Deserialize, Serialize};
use tokio::sync::mpsc;

use crate::cardiacbot::cardiac_conf::CardiacConfig;

#[derive(Debug, Deserialize, Serialize)]
pub struct CardiacInitStrategy {
    pub strategy: String,
    pub symbol: String,
    pub side: String,
    pub price: String,
    pub quantity: String,
    pub config: CardiacConfig,
}

#[derive(Debug, Serialize)]
pub struct ApiResponse {
    pub status: String,
    pub message: String,
}

pub struct AppState {
    pub tx_rest_api_cmd: mpsc::Sender<RestApiCommands>,
}
