use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Deserialize)]
pub struct ExchangeInfo {
    #[serde(default)]
    pub symbols: Vec<SymbolInfo>,
}

#[derive(Debug, Clone, Deserialize)]
pub struct SymbolInfo {
    #[serde(default)]
    pub symbol: String,
    #[serde(rename = "pricePrecision", default)]
    pub price_precision: i32,
    #[serde(rename = "quantityPrecision", default)]
    pub quantity_precision: i32,
    #[serde(default)]
    pub filters: Vec<SymbolFilter>,
}

#[derive(Debug, Clone, Deserialize, Default)]
pub struct SymbolFilter {
    #[serde(rename = "filterType", default)]
    pub filter_type: String,
    #[serde(rename = "tickSize", default)]
    pub tick_size: Option<String>,
    #[serde(rename = "stepSize", default)]
    pub step_size: Option<String>,
    #[serde(rename = "minQty", default)]
    pub min_qty: Option<String>,
    #[serde(rename = "maxQty", default)]
    pub max_qty: Option<String>,
    #[serde(default)]
    pub notional: Option<String>,
    #[serde(rename = "minNotional", default)]
    pub min_notional: Option<String>,
}

#[derive(Debug, Clone, Deserialize)]
pub struct Balance {
    #[serde(default)]
    pub asset: String,
    #[serde(default)]
    pub balance: String,
}

#[derive(Debug, Clone, Deserialize)]
pub struct PositionInfo {
    #[serde(default)]
    pub symbol: String,
    #[serde(rename = "positionSide", default)]
    pub position_side: String,
    #[serde(rename = "positionAmt", default)]
    pub position_amt: String,
    #[serde(rename = "entryPrice", default)]
    pub entry_price: String,
}

/// Response of `POST /fapi/v1/order`, `DELETE /fapi/v1/order` and items of
/// `GET /fapi/v1/openOrders`. Only the fields the bot reads are modelled.
#[derive(Debug, Clone, Deserialize, Serialize, Default)]
pub struct OrderResponse {
    #[serde(rename = "orderId", default)]
    pub order_id: i64,
    #[serde(default)]
    pub symbol: String,
    #[serde(rename = "clientOrderId", default)]
    pub client_order_id: Option<String>,
    #[serde(default)]
    pub status: String,
    #[serde(default)]
    pub side: String,
    #[serde(rename = "type", default)]
    pub order_type: String,
    #[serde(rename = "positionSide", default)]
    pub position_side: Option<String>,
    #[serde(default)]
    pub price: Option<String>,
    #[serde(rename = "stopPrice", default)]
    pub stop_price: Option<String>,
    #[serde(rename = "origQty", default)]
    pub orig_qty: Option<String>,
    #[serde(rename = "executedQty", default)]
    pub executed_qty: Option<String>,
    #[serde(rename = "avgPrice", default)]
    pub avg_price: Option<String>,
    #[serde(rename = "closePosition", default)]
    pub close_position: Option<bool>,
    #[serde(rename = "timeInForce", default)]
    pub time_in_force: Option<String>,
    #[serde(rename = "updateTime", default)]
    pub update_time: Option<i64>,
}

impl OrderResponse {
    pub fn orig_qty_f64(&self) -> f64 {
        self.orig_qty
            .as_deref()
            .and_then(|value| value.parse().ok())
            .unwrap_or(0.0)
    }

    pub fn price_f64(&self) -> f64 {
        self.price
            .as_deref()
            .and_then(|value| value.parse().ok())
            .unwrap_or(0.0)
    }
}

#[derive(Debug, Clone, Deserialize)]
pub struct ListenKey {
    #[serde(rename = "listenKey", default)]
    pub listen_key: String,
}

#[derive(Debug, Clone, Deserialize, Default)]
pub struct ApiErrorBody {
    #[serde(default)]
    pub code: i64,
    #[serde(default)]
    pub msg: String,
}

/// The `o` object of an `ORDER_TRADE_UPDATE` event.
///
/// Field names are the single-letter keys Binance uses (`s`, `S`, `o`, `X`,
/// `ps`, `cp`, `ot`, ...), renamed to readable Rust names.
#[derive(Debug, Clone, Deserialize, Default)]
pub struct OrderEvent {
    #[serde(rename = "s", default)]
    pub symbol: String,
    #[serde(rename = "c", default)]
    pub client_order_id: String,
    #[serde(rename = "S", default)]
    pub side: String,
    #[serde(rename = "o", default)]
    pub order_type: String,
    #[serde(rename = "ot", default)]
    pub orig_type: String,
    #[serde(rename = "q", default)]
    pub orig_qty: String,
    #[serde(rename = "p", default)]
    pub price: String,
    #[serde(rename = "ap", default)]
    pub avg_price: String,
    #[serde(rename = "X", default)]
    pub status: String,
    #[serde(rename = "i", default)]
    pub order_id: i64,
    #[serde(rename = "ps", default)]
    pub position_side: String,
    #[serde(rename = "cp", default)]
    pub close_position: bool,
}

#[derive(Debug, Clone, Deserialize, Default)]
pub struct UserDataEvent {
    #[serde(rename = "e", default)]
    pub event_type: String,
    #[serde(rename = "o", default)]
    pub order: Option<OrderEvent>,
}

/// Parameters for `POST /fapi/v1/order`.
#[derive(Debug, Clone, Default)]
pub struct NewOrder {
    pub symbol: String,
    pub side: String,
    pub order_type: String,
    pub time_in_force: Option<String>,
    pub position_side: Option<String>,
    pub price: Option<f64>,
    pub quantity: Option<f64>,
    pub stop_price: Option<f64>,
    pub close_position: Option<bool>,
    pub activation_price: Option<f64>,
    pub callback_rate: Option<f64>,
}
