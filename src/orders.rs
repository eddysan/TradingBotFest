//! Order placement, cancellation and filtering — the Rust port of
//! `package_common.py`.

use crate::error::{AppError, Result};
use crate::exchange::models::{NewOrder, OrderResponse};
use crate::exchange::BinanceClient;
use crate::util::py_round;
use futures_util::stream::{self, StreamExt};
use serde_json::Value;
use tracing::{debug, error, info, warn};

const GRID_CONCURRENCY: usize = 10;

fn field_str(line: &Value, key: &str) -> Option<String> {
    line.get(key).and_then(Value::as_str).map(str::to_string)
}

fn field_f64(line: &Value, key: &str) -> Option<f64> {
    match line.get(key)? {
        Value::Number(number) => number.as_f64(),
        Value::String(text) => text.parse().ok(),
        _ => None,
    }
}

fn label(line: &Value, default: &str) -> String {
    field_str(line, "label").unwrap_or_else(|| default.to_string())
}

fn position_side(line: &Value) -> String {
    field_str(line, "position_side").unwrap_or_else(|| "NONE".to_string())
}

/// Post a single LIMIT order. Zero-quantity lines are skipped, as in Python.
pub async fn post_limit_order(
    client: &BinanceClient,
    symbol: &str,
    line: &Value,
) -> Result<()> {
    let side = field_str(line, "side").unwrap_or_default();
    let pos_side = position_side(line);
    let price = field_f64(line, "price");
    let quantity = field_f64(line, "quantity");
    let line_label = label(line, "LIMIT");

    let Some(quantity) = quantity.filter(|value| *value != 0.0) else {
        info!("{symbol}_{pos_side} - {line_label} operation skipped due to zero quantity.");
        return Ok(());
    };

    let order = NewOrder {
        symbol: symbol.to_string(),
        side,
        order_type: "LIMIT".into(),
        time_in_force: Some("GTC".into()),
        position_side: Some(pos_side.clone()),
        price,
        quantity: Some(quantity),
        ..Default::default()
    };

    match client.create_order(&order).await {
        Ok(response) => {
            debug!("{symbol}_{pos_side} LIMIT order response: {response:?}");
            info!(
                "{symbol}_{pos_side} - {line_label} | Price: {} | Quantity: {} ...POSTED",
                price.map(crate::util::fmt_num).unwrap_or_default(),
                crate::util::fmt_num(quantity)
            );
            Ok(())
        }
        Err(error) => report_api_error(error, symbol, &pos_side, &line_label, price),
    }
}

pub async fn post_take_profit_order(
    client: &BinanceClient,
    symbol: &str,
    line: &Value,
) -> Result<()> {
    let pos_side = position_side(line);
    let price = field_f64(line, "price");
    let side = field_str(line, "side").unwrap_or_default();
    let line_label = label(line, "TAKE_PROFIT");
    let quantity = field_f64(line, "quantity");

    let order = NewOrder {
        symbol: symbol.to_string(),
        side,
        order_type: "TAKE_PROFIT_MARKET".into(),
        position_side: Some(pos_side.clone()),
        stop_price: price,
        close_position: Some(true),
        ..Default::default()
    };

    match client.create_order(&order).await {
        Ok(response) => {
            debug!("{symbol}_{pos_side} Binance response: {response:?}");
            info!(
                "{symbol}_{pos_side} - {line_label} | Price: {} | Quantity: {} ...POSTED",
                price.map(crate::util::fmt_num).unwrap_or_default(),
                quantity.map(crate::util::fmt_num).unwrap_or_default()
            );
            Ok(())
        }
        Err(error) => report_api_error(error, symbol, &pos_side, &line_label, price),
    }
}

pub async fn post_stop_loss_order(
    client: &BinanceClient,
    symbol: &str,
    line: &Value,
) -> Result<()> {
    let pos_side = position_side(line);
    let price = field_f64(line, "price");
    let side = field_str(line, "side").unwrap_or_default();
    let line_label = label(line, "STOP_LOSS");
    let distance = py_round(field_f64(line, "distance").unwrap_or(0.0), 2);
    let quantity = field_f64(line, "quantity");
    let cost = field_f64(line, "cost");

    let order = NewOrder {
        symbol: symbol.to_string(),
        side,
        order_type: "STOP_MARKET".into(),
        position_side: Some(pos_side.clone()),
        stop_price: price,
        close_position: Some(true),
        ..Default::default()
    };

    match client.create_order(&order).await {
        Ok(response) => {
            debug!("{symbol}_{pos_side} STOP_LOSS response: {response:?}");
            info!(
                "{symbol}_{pos_side} - {line_label} ({distance}%) | Price: {} | Quantity: {} | Cost: {} ...POSTED",
                price.map(crate::util::fmt_num).unwrap_or_default(),
                quantity.map(crate::util::fmt_num).unwrap_or_default(),
                cost.map(crate::util::fmt_num).unwrap_or_default()
            );
            Ok(())
        }
        Err(error) => report_api_error(error, symbol, &pos_side, &line_label, price),
    }
}

pub async fn post_hedge_order(
    client: &BinanceClient,
    symbol: &str,
    line: &Value,
) -> Result<()> {
    let pos_side = position_side(line);
    let price = field_f64(line, "price");
    let side = field_str(line, "side").unwrap_or_default();
    let quantity = field_f64(line, "quantity");
    let line_label = label(line, "HEDGE");

    let order = NewOrder {
        symbol: symbol.to_string(),
        side,
        order_type: "STOP_MARKET".into(),
        time_in_force: Some("GTC".into()),
        position_side: Some(pos_side.clone()),
        stop_price: price,
        quantity,
        close_position: Some(false),
        ..Default::default()
    };

    match client.create_order(&order).await {
        Ok(response) => {
            debug!("{symbol}_{pos_side} Post hedge order response: {response:?}");
            info!(
                "{symbol}_{pos_side} - {line_label} | Price: {} | Quantity: {} ...POSTED",
                price.map(crate::util::fmt_num).unwrap_or_default(),
                quantity.map(crate::util::fmt_num).unwrap_or_default()
            );
            Ok(())
        }
        Err(error) => report_api_error(error, symbol, &pos_side, &line_label, price),
    }
}

pub async fn post_trailing_stop_order(
    client: &BinanceClient,
    symbol: &str,
    line: &Value,
) -> Result<()> {
    let pos_side = position_side(line);
    let activation_price = field_f64(line, "activation_price");
    let callback_rate = field_f64(line, "callback_rate");
    let side = field_str(line, "side").unwrap_or_default();
    let quantity = field_f64(line, "quantity");
    let line_label = label(line, "TRAILING_STOP_MARKET");

    let order = NewOrder {
        symbol: symbol.to_string(),
        side,
        order_type: "TRAILING_STOP_MARKET".into(),
        time_in_force: Some("GTC".into()),
        position_side: Some(pos_side.clone()),
        activation_price,
        callback_rate,
        quantity,
        close_position: Some(false),
        ..Default::default()
    };

    match client.create_order(&order).await {
        Ok(response) => {
            debug!("{symbol}_{pos_side} Post trailing stop response: {response:?}");
            info!(
                "{symbol}_{pos_side} - {line_label} | Activation Price: {} | Quantity: {} ...POSTED",
                activation_price.map(crate::util::fmt_num).unwrap_or_default(),
                quantity.map(crate::util::fmt_num).unwrap_or_default()
            );
            Ok(())
        }
        Err(error) => report_api_error(error, symbol, &pos_side, &line_label, activation_price),
    }
}

/// Post every line whose `status` is `NEW`, up to ten at a time.
pub async fn post_grid_order(
    client: &BinanceClient,
    symbol: &str,
    lines: &Value,
) -> Result<()> {
    let Some(lines) = lines.as_array() else {
        return Err(AppError::msg(format!(
            "{symbol} grid orders: expected an array"
        )));
    };

    debug!("{symbol} POSTING GRID ORDERS...");

    let pending: Vec<Value> = lines
        .iter()
        .filter(|line| field_str(line, "status").as_deref() == Some("NEW"))
        .cloned()
        .collect();

    let results: Vec<Result<()>> = stream::iter(pending)
        .map(|line| async move { post_grid_one(client, symbol, &line).await })
        .buffer_unordered(GRID_CONCURRENCY)
        .collect()
        .await;

    for result in results {
        if let Err(error) = result {
            error!("{symbol} Error in posting a grid order: {error}");
        }
    }

    Ok(())
}

async fn post_grid_one(client: &BinanceClient, symbol: &str, line: &Value) -> Result<()> {
    let pos_side = position_side(line);
    let price = field_f64(line, "price");
    let quantity = field_f64(line, "quantity");
    let line_label = label(line, "GRID");

    let order = NewOrder {
        symbol: symbol.to_string(),
        side: field_str(line, "side").unwrap_or_default(),
        order_type: "LIMIT".into(),
        time_in_force: Some("GTC".into()),
        position_side: Some(pos_side.clone()),
        price,
        quantity,
        ..Default::default()
    };

    match client.create_order(&order).await {
        Ok(response) => {
            debug!("{symbol} Binance response: {response:?}");
            info!(
                "{symbol} - {line_label} | Price: {} | Quantity: {} | Cost: {} ...POSTED",
                price.map(crate::util::fmt_num).unwrap_or_default(),
                quantity.map(crate::util::fmt_num).unwrap_or_default(),
                field_f64(line, "cost")
                    .map(crate::util::fmt_num)
                    .unwrap_or_default()
            );
            Ok(())
        }
        Err(error) => report_api_error(error, symbol, &pos_side, &line_label, price),
    }
}

fn report_api_error(
    error: AppError,
    symbol: &str,
    pos_side: &str,
    line_label: &str,
    price: Option<f64>,
) -> Result<()> {
    if error.api_code() == Some(-2021) {
        error!(
            "{symbol}_{pos_side} - {line_label} | Price: {} ...TRIGGERED",
            price.map(crate::util::fmt_num).unwrap_or_default()
        );
    } else {
        error!("{symbol}_{pos_side} - Binance API error: {error}");
    }
    Ok(())
}

/// Cancel every open order for a symbol.
pub async fn clean_all_open_orders(client: &BinanceClient, symbol: &str) -> Result<()> {
    debug!("{symbol} - CLEAN ALL OPEN ORDERS...");
    match client.cancel_all_open_orders(symbol).await {
        Ok(()) => {
            info!("{symbol} - All open orders cancelled");
            Ok(())
        }
        Err(error) => {
            if is_nothing_to_cancel(&error) {
                info!("{symbol} - No open orders to cancel.");
                Ok(())
            } else {
                error!("{symbol} - Error cancelling orders: {error}");
                Err(error)
            }
        }
    }
}

/// Cancel every open order on one position side.
pub async fn clean_open_orders(
    client: &BinanceClient,
    symbol: &str,
    pos_side: &str,
) -> Result<()> {
    debug!("{symbol}_{pos_side} - CLEAN ALL OPEN ORDERS...");

    let open_orders = client.open_orders(symbol).await?;
    let filtered: Vec<OrderResponse> = open_orders
        .into_iter()
        .filter(|order| order.position_side.as_deref() == Some(pos_side))
        .collect();

    if filtered.is_empty() {
        info!("{symbol}_{pos_side} - There are no orders to cancel.");
        return Ok(());
    }

    let results: Vec<Result<()>> = stream::iter(filtered)
        .map(|order| async move { cancel_one(client, symbol, pos_side, &order).await })
        .buffer_unordered(GRID_CONCURRENCY)
        .collect()
        .await;

    for result in results {
        if let Err(error) = result {
            error!("{symbol}_{pos_side} - unexpected cancellation error: {error}");
        }
    }

    Ok(())
}

/// Cancel the open orders belonging to one kind of operation for a position.
pub async fn clean_order(
    client: &BinanceClient,
    symbol: &str,
    pos_side: &str,
    kind_operation: &str,
) -> Result<()> {
    debug!("{symbol}_{pos_side} CLEANING {kind_operation} ORDERS...");

    let open_orders = match client.open_orders(symbol).await {
        Ok(orders) => orders,
        Err(error) => {
            error!("{symbol}_{pos_side} There is an exception retrieving orders {error}");
            return Err(error);
        }
    };

    let filtered = filter_operation(open_orders, pos_side, kind_operation)?;

    if filtered.is_empty() {
        info!("{symbol}_{pos_side} There is no orders to cancel.");
        return Ok(());
    }

    let results: Vec<Result<()>> = stream::iter(filtered)
        .map(|order| async move {
            cancel_one_for_kind(client, symbol, pos_side, kind_operation, &order).await
        })
        .buffer_unordered(GRID_CONCURRENCY)
        .collect()
        .await;

    for result in results {
        if let Err(error) = result {
            error!("{symbol}_{pos_side} - unexpected cancellation error: {error}");
        }
    }

    Ok(())
}

async fn cancel_one(
    client: &BinanceClient,
    symbol: &str,
    pos_side: &str,
    order: &OrderResponse,
) -> Result<()> {
    match client.cancel_order(symbol, order.order_id).await {
        Ok(response) => {
            info!(
                "{symbol}_{pos_side} - {} | Price: {} | Quantity: {} ...CANCELLED",
                response.order_type,
                response.price.clone().unwrap_or_default(),
                response.orig_qty.clone().unwrap_or_default()
            );
            Ok(())
        }
        Err(error) => report_cancel_error(error, symbol, pos_side, order.order_id),
    }
}

async fn cancel_one_for_kind(
    client: &BinanceClient,
    symbol: &str,
    pos_side: &str,
    kind_operation: &str,
    order: &OrderResponse,
) -> Result<()> {
    match client.cancel_order(symbol, order.order_id).await {
        Ok(response) => {
            info!(
                "{symbol}_{pos_side} - {kind_operation} | Price: {} | Quantity: {} ...CANCELLED",
                response.price.clone().unwrap_or_default(),
                response.orig_qty.clone().unwrap_or_default()
            );
            Ok(())
        }
        Err(error) => report_cancel_error(error, symbol, pos_side, order.order_id),
    }
}

fn report_cancel_error(
    error: AppError,
    symbol: &str,
    pos_side: &str,
    order_id: i64,
) -> Result<()> {
    if error.api_code() == Some(-2011) {
        warn!(
            "{symbol}_{pos_side} - Order {order_id} does not exist or is already cancelled."
        );
    } else {
        error!("{symbol}_{pos_side} - API error cancelling order {order_id}: {error}");
    }
    Ok(())
}

fn is_nothing_to_cancel(error: &AppError) -> bool {
    matches!(
        error.api_code(),
        Some(-2011) | Some(-4046)
    ) || error.to_string().to_lowercase().contains("no orders to cancel")
}

/// Keep the orders that belong to `kind_operation` on `position_side`.
///
/// This is the Rust equivalent of the Python `operation_map`:
/// `(order type, order side, closePosition)`.
pub fn filter_operation(
    open_orders: Vec<OrderResponse>,
    pos_side: &str,
    kind_operation: &str,
) -> Result<Vec<OrderResponse>> {
    let (order_type, side, close_position) = match kind_operation {
        "GRID" => (
            "LIMIT",
            if pos_side == "LONG" { "BUY" } else { "SELL" },
            false,
        ),
        "UNLOAD" => (
            "LIMIT",
            if pos_side == "LONG" { "SELL" } else { "BUY" },
            false,
        ),
        "TAKE_PROFIT" => (
            "TAKE_PROFIT_MARKET",
            if pos_side == "LONG" { "SELL" } else { "BUY" },
            true,
        ),
        "STOP_LOSS" => (
            "STOP_MARKET",
            if pos_side == "LONG" { "SELL" } else { "BUY" },
            true,
        ),
        "HEDGE" => (
            "STOP_MARKET",
            if pos_side == "LONG" { "BUY" } else { "SELL" },
            false,
        ),
        "TRAILING_STOP_MARKET" => (
            "TRAILING_STOP_MARKET",
            if pos_side == "LONG" { "SELL" } else { "BUY" },
            false,
        ),
        other => {
            return Err(AppError::msg(format!(
                "unknown operation to clean: {other}"
            )))
        }
    };

    Ok(open_orders
        .into_iter()
        .filter(|order| {
            order.position_side.as_deref() == Some(pos_side)
                && order.order_type == order_type
                && order.side == side
                && order.close_position.unwrap_or(false) == close_position
        })
        .collect())
}

#[cfg(test)]
mod tests {
    use super::*;

    fn order(order_type: &str, side: &str, pos_side: &str, close: bool) -> OrderResponse {
        OrderResponse {
            order_id: 1,
            order_type: order_type.into(),
            side: side.into(),
            position_side: Some(pos_side.into()),
            close_position: Some(close),
            price: Some("100.0".into()),
            orig_qty: Some("1".into()),
            ..Default::default()
        }
    }

    #[test]
    fn grid_filter_matches_limit_orders_on_the_same_side() {
        let orders = vec![
            order("LIMIT", "BUY", "LONG", false),
            order("LIMIT", "SELL", "LONG", false),
            order("LIMIT", "BUY", "SHORT", false),
        ];
        let filtered = filter_operation(orders, "LONG", "GRID").unwrap();
        assert_eq!(filtered.len(), 1);
        assert_eq!(filtered[0].side, "BUY");
        assert_eq!(filtered[0].position_side.as_deref(), Some("LONG"));
    }

    #[test]
    fn stop_loss_filter_requires_close_position() {
        let orders = vec![
            order("STOP_MARKET", "SELL", "LONG", true),
            order("STOP_MARKET", "SELL", "LONG", false),
        ];
        let filtered = filter_operation(orders, "LONG", "STOP_LOSS").unwrap();
        assert_eq!(filtered.len(), 1);
        assert!(filtered[0].close_position.unwrap());
    }

    #[test]
    fn hedge_filter_uses_position_direction() {
        let orders = vec![
            order("STOP_MARKET", "BUY", "LONG", false),
            order("STOP_MARKET", "SELL", "LONG", false),
        ];
        let filtered = filter_operation(orders, "LONG", "HEDGE").unwrap();
        assert_eq!(filtered.len(), 1);
        assert_eq!(filtered[0].side, "BUY");
    }

    #[test]
    fn unknown_operation_is_an_error() {
        assert!(filter_operation(Vec::new(), "LONG", "NOPE").is_err());
    }
}
