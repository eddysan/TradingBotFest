//! Binance USDS-M futures integration.
//!
//! The REST surface mirrors what the Python bot used through `python-binance`:
//! exchange info, futures balance, position risk, order create/cancel/query and
//! the user-data listen key. Signing is HMAC-SHA256 over the query string.

pub mod client;
pub mod filters;
pub mod models;
pub mod ws;

pub use client::BinanceClient;
pub use filters::SymbolFilters;
pub use models::{
    ApiErrorBody, Balance, ExchangeInfo, ListenKey, OrderEvent, OrderResponse, PositionInfo,
    SymbolFilter, SymbolInfo, UserDataEvent,
};
