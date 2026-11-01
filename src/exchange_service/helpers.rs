use anyhow::{Context, Result};
use binance_sdk::config::ConfigurationRestApi;
use binance_sdk::derivatives_trading_usds_futures::rest_api::RestApi;
use binance_sdk::derivatives_trading_usds_futures::DerivativesTradingUsdsFuturesRestApi;
use dotenvy::dotenv;
use std::sync::OnceLock;

use crate::db::{DbPool, upsert_symbol};
use crate::exchange_service::models::{ExchangeInfo, ExtractedFilters};

static BINANCE_CLIENT: OnceLock<RestApi> = OnceLock::new();

/// Connect to binance testnet or production and get the client
pub async fn get_binance_client() -> Result<&'static RestApi> {
    if let Some(client) = BINANCE_CLIENT.get() {
        return Ok(client);
    }

    dotenv().ok();
    let binance_net = std::env::var("BINANCE_NETWORK")
        .unwrap_or_else(|_| "TESTNET".to_string())
        .to_uppercase();

    let client = if binance_net == "TESTNET" {
        let config = ConfigurationRestApi::builder()
            .api_key(
                std::env::var("BINANCE_TEST_API_KEY")
                    .with_context(|| "BINANCE_TEST_API_KEY must be set in .env")?,
            )
            .api_secret(
                std::env::var("BINANCE_TEST_API_SECRET")
                    .with_context(|| "BINANCE_TEST_API_SECRET must be set in .env")?,
            )
            .build()?;
        DerivativesTradingUsdsFuturesRestApi::testnet(config)
    } else {
        let config = ConfigurationRestApi::builder()
            .api_key(
                std::env::var("BINANCE_PROD_API_KEY")
                    .with_context(|| "BINANCE_PROD_API_KEY must be set in .env")?,
            )
            .api_secret(
                std::env::var("BINANCE_PROD_API_SECRET")
                    .with_context(|| "BINANCE_PROD_API_SECRET must be set in .env")?,
            )
            .build()?;
        DerivativesTradingUsdsFuturesRestApi::production(config)
    };

    let _ = BINANCE_CLIENT.set(client);
    Ok(BINANCE_CLIENT.get().unwrap())
}

pub async fn sync_symbol(pool: &DbPool, symbol: &str) -> Result<()> {
    let client = get_binance_client()
        .await
        .context("Failed to get Binance client")?;

    let response = client
        .exchange_information()
        .await
        .context("Failed to fetch exchange information")?;

    let data = response
        .data()
        .await
        .context("Failed to parse exchange information data")?;

    let json_str = serde_json::to_string(&data)?;

    let exchange_info: ExchangeInfo =
        serde_json::from_str(&json_str).context("Failed to parse exchange info")?;

    if let Some(sym) = exchange_info
        .symbols
        .into_iter()
        .find(|s| s.symbol == symbol)
    {
        if let Some(filters) = extract_filters(&sym.filters) {
            upsert_symbol(
                pool,
                &sym.symbol,
                &sym.status,
                &sym.base_asset,
                &sym.quote_asset,
                sym.price_precision,
                sym.quantity_precision,
                &filters.tick_size,
                &filters.step_size,
                &filters.min_qty,
                &filters.max_qty,
            )
            .await?;
            println!("Synced symbol: {}", symbol);
        } else {
            anyhow::bail!("Symbol {symbol} missing required filters");
        }
    } else {
        anyhow::bail!("Symbol {symbol} not found in exchange info");
    }

    Ok(())
}

fn extract_filters(filters: &[serde_json::Value]) -> Option<ExtractedFilters> {
    let mut tick_size = None;
    let mut min_qty = None;
    let mut max_qty = None;
    let mut step_size = None;

    for f in filters {
        if let Some(filter_type) = f.get("filterType").and_then(|v| v.as_str()) {
            match filter_type {
                "PRICE_FILTER" => {
                    if let Some(ts) = f.get("tickSize").and_then(|v| v.as_str()) {
                        tick_size = Some(ts.to_string());
                    }
                }
                "LOT_SIZE" => {
                    if let Some(mq) = f.get("minQty").and_then(|v| v.as_str()) {
                        min_qty = Some(mq.to_string());
                    }
                    if let Some(xq) = f.get("maxQty").and_then(|v| v.as_str()) {
                        max_qty = Some(xq.to_string());
                    }
                    if let Some(ss) = f.get("stepSize").and_then(|v| v.as_str()) {
                        step_size = Some(ss.to_string());
                    }
                }
                _ => {}
            }
        }
    }

    match (tick_size, step_size, min_qty, max_qty) {
        (Some(ts), Some(ss), Some(mq), Some(xq)) => Some(ExtractedFilters {
            tick_size: ts,
            step_size: ss,
            min_qty: mq,
            max_qty: xq,
        }),
        _ => None,
    }
}
