use serde::{Deserialize, Serialize};

#[derive(Debug, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct BinanceSymbol {
    pub symbol: String,
    pub status: String,
    pub base_asset: String,
    pub quote_asset: String,
    pub price_precision: i32,
    pub quantity_precision: i32,
    pub filters: Vec<serde_json::Value>,
}

#[derive(Debug, Serialize, Deserialize)]
pub struct ExtractedFilters {
    pub tick_size: String,
    pub step_size: String,
    pub min_qty: String,
    pub max_qty: String,
}

#[derive(Debug, Serialize, Deserialize)]
pub struct ExchangeInfo {
    pub symbols: Vec<BinanceSymbol>,
}
