//! THE LOAD UNLOAD GRID strategy — Rust port of `package_theloadunload.py`.

use crate::error::{AppError, Result};
use crate::exchange::models::OrderEvent;
use crate::exchange::BinanceClient;
use crate::orders::{
    clean_open_orders, clean_order, post_grid_order, post_limit_order, post_stop_loss_order,
    post_take_profit_order,
};
use crate::store::{self, Grid};
use crate::util::{
    prompt, prompt_f64_or, py_round, round_to_tick, tick_digits,
};
use serde_json::{json, Value};
use tracing::{debug, info, warn};

/// Safety valve for the grid loop: with a zero `grid_distance` the Python
/// version never terminates. Ten thousand lines is far beyond any real grid.
const MAX_GRID_LINES: usize = 10_000;

pub async fn input_data(client: &BinanceClient) -> Result<String> {
    info!("LCD - THE LOAD UNLOAD...");
    let mut grid = Grid::from_value(
        "config/theloadunload.json",
        store::read_json_required("config/theloadunload.json")?,
    );

    let base = prompt("Symbol (BTC): ")?.to_uppercase();
    let symbol = format!("{base}USDT");
    grid.set_top_level("symbol", Value::from(symbol.clone()))?;

    let side = prompt("Side (LONG|SHORT): ")?.to_uppercase();
    let input_side = if side.is_empty() { "LONG".to_string() } else { side };
    grid.set_top_level("input_side", Value::from(input_side.clone()))?;

    let filters = client.symbol_filters(&symbol).await?;
    grid.set_top_level("step_size", Value::from(filters.step_size))?;
    grid.set_top_level("tick_size", Value::from(filters.tick_size))?;
    grid.set_top_level("price_precision", Value::from(filters.price_precision))?;
    grid.set_top_level(
        "quantity_precision",
        Value::from(filters.quantity_precision),
    )?;

    let positions = client.position_information(&symbol).await?;
    for position in &positions {
        let amount = position.position_amt.parse::<f64>().unwrap_or(0.0);
        if amount != 0.0 && position.position_side == input_side {
            let entry_price = position.entry_price.parse::<f64>().unwrap_or(0.0);
            println!(
                "There is a current position... \n\
                 Position side: {} \n\
                 Price: {} \n\
                 Quantity: {}",
                position.position_side,
                position.entry_price,
                amount.abs()
            );

            let tick_size = grid.f64(&["tick_size"])?;
            let price = round_to_tick(entry_price, tick_size);
            let quantity = amount.abs();
            let cost = py_round(price * quantity, 2);

            grid.set(&[input_side.as_str(), "current_line", "price"], price)?;
            grid.set(&[input_side.as_str(), "current_line", "quantity"], quantity)?;
            grid.set(&[input_side.as_str(), "current_line", "cost"], cost)?;
            grid.set(
                &[input_side.as_str(), "current_line", "status"],
                Value::from("FILLED"),
            )?;

            grid.set(&[input_side.as_str(), "entry_line", "price"], price)?;
            grid.set(&[input_side.as_str(), "entry_line", "quantity"], quantity)?;
            grid.set(&[input_side.as_str(), "entry_line", "cost"], cost)?;
            grid.set(
                &[input_side.as_str(), "entry_line", "status"],
                Value::from("FILLED"),
            )?;
        }
    }

    let wallet_balance = client.wallet_balance_usdt().await?;
    let percentage = grid.f64(&[input_side.as_str(), "risk", "percentage"])?;
    let risk_amount = py_round(wallet_balance * (percentage / 100.0), 2);
    grid.set(
        &[input_side.as_str(), "risk", "wallet_balance_usdt"],
        wallet_balance,
    )?;
    grid.set(&[input_side.as_str(), "risk", "risk_amount"], risk_amount)?;

    let status = grid.string(&[input_side.as_str(), "entry_line", "status"])?;
    if status != "FILLED" {
        let tick_size = grid.f64(&["tick_size"])?;
        let input_price = prompt_f64_or("Entry Price ($): ", 0.0)?;
        let entry_price = py_round(input_price, tick_digits(tick_size));
        grid.set(
            &[input_side.as_str(), "entry_line", "price"],
            entry_price,
        )?;

        if entry_price == 0.0 {
            return Err(AppError::msg("entry price must be greater than zero"));
        }

        let quantity_precision = grid.i32(&["quantity_precision"])?;
        let risk_amount = grid.f64(&[input_side.as_str(), "risk", "risk_amount"])?;
        let entry_usdt = prompt_f64_or(&format!("Entry Quantity ({risk_amount}$): "), risk_amount)?;
        let quantity = py_round(entry_usdt / entry_price, quantity_precision);
        grid.set(
            &[input_side.as_str(), "entry_line", "quantity"],
            quantity,
        )?;
        grid.set(
            &[input_side.as_str(), "entry_line", "status"],
            Value::from("NEW"),
        )?;

        grid.set(
            &[input_side.as_str(), "current_line", "price"],
            entry_price,
        )?;
        grid.set(&[input_side.as_str(), "current_line", "quantity"], quantity)?;
        grid.set(
            &[input_side.as_str(), "current_line", "cost"],
            py_round(entry_price * quantity, 2),
        )?;
    }

    let grid_distance = prompt_f64_or("Grid Distance (2%): ", 2.0)?;
    grid.set(
        &[input_side.as_str(), "risk", "grid_distance"],
        grid_distance,
    )?;

    let quantity_increment = prompt_f64_or("Token Increment (40%): ", 40.0)?;
    grid.set(
        &[input_side.as_str(), "risk", "quantity_increment"],
        quantity_increment,
    )?;

    let risk_amount = grid.f64(&[input_side.as_str(), "risk", "risk_amount"])?;
    let stop_loss_amount = prompt_f64_or(
        &format!("Stop Loss Amount ({risk_amount}$): "),
        risk_amount,
    )?;
    grid.set(
        &[input_side.as_str(), "risk", "stop_loss_amount"],
        stop_loss_amount,
    )?;

    write_operation_file(&symbol, &mut grid, &input_side)?;
    Ok(symbol)
}

fn write_operation_file(symbol: &str, grid: &mut Grid, input_side: &str) -> Result<()> {
    let ops_path = store::ops_path(symbol);
    let data = if ops_path.exists() {
        let mut existing = store::read_json_required(&ops_path)?;
        let strategy = existing
            .get("strategy")
            .and_then(Value::as_str)
            .unwrap_or_default()
            .to_string();
        if strategy == "THE_LOAD_UNLOAD_GRID" {
            if let Value::Object(map) = &mut existing {
                map.insert(input_side.to_string(), grid.value(&[input_side])?);
                for key in [
                    "symbol",
                    "input_side",
                    "price_precision",
                    "quantity_precision",
                    "tick_size",
                    "step_size",
                ] {
                    let value = grid.value(&[key])?;
                    map.insert(key.to_string(), value);
                }
            }
            existing
        } else {
            grid.data.clone()
        }
    } else {
        grid.data.clone()
    };

    store::write_json(store::ops_dir(), &format!("{symbol}.json"), &data)
}

pub struct LUGrid {
    pub grid: Grid,
    pub pos_side: String,
}

impl LUGrid {
    pub fn new(symbol: &str) -> Result<Self> {
        Ok(Self {
            grid: Grid::load(symbol)?,
            pos_side: String::new(),
        })
    }

    pub async fn post_order(&mut self, client: &BinanceClient) -> Result<()> {
        self.pos_side = self.grid.string(&["input_side"])?;
        self.generate_grid()?;

        let symbol = self.grid.symbol.clone();
        let status = self
            .grid
            .string(&[self.pos_side.as_str(), "entry_line", "status"])?;
        if status != "FILLED" {
            let entry_line = self
                .grid
                .value(&[self.pos_side.as_str(), "entry_line"])?;
            post_limit_order(client, &symbol, &entry_line).await?;
        }

        let body_line = self.grid.value(&[self.pos_side.as_str(), "body_line"])?;
        post_grid_order(client, &symbol, &body_line).await?;

        let stop_loss_line = self
            .grid
            .value(&[self.pos_side.as_str(), "stop_loss_line"])?;
        post_stop_loss_order(client, &symbol, &stop_loss_line).await?;

        if self
            .grid
            .bool_or(&[self.pos_side.as_str(), "take_profit_line", "enabled"], false)
        {
            self.generate_take_profit()?;
            let take_profit_line = self
                .grid
                .value(&[self.pos_side.as_str(), "take_profit_line"])?;
            post_take_profit_order(client, &symbol, &take_profit_line).await?;
        }

        self.grid.save()
    }

    pub async fn attend_message(
        &mut self,
        client: &BinanceClient,
        event: &OrderEvent,
    ) -> Result<()> {
        if event.status != "FILLED" {
            return Ok(());
        }

        self.pos_side = event.position_side.clone();
        let symbol = self.grid.symbol.clone();

        match self.get_transaction_type(event) {
            Some("GRID") => {
                debug!(
                    "{symbol}_{} - LCD - ATTENDING GRID OPERATION... price: {}, quantity: {}",
                    self.pos_side, event.price, event.orig_qty
                );
                self.update_current_position(client).await?;

                if self
                    .grid
                    .bool_or(&[self.pos_side.as_str(), "unload_line", "enabled"], false)
                {
                    let entry_side = self
                        .grid
                        .string(&[self.pos_side.as_str(), "entry_line", "position_side"])?;
                    clean_order(client, &symbol, &entry_side, "UNLOAD").await?;
                    self.generate_unload_order()?;
                    let unload_line = self
                        .grid
                        .value(&[self.pos_side.as_str(), "unload_line"])?;
                    post_limit_order(client, &symbol, &unload_line).await?;
                }

                if self
                    .grid
                    .bool_or(&[self.pos_side.as_str(), "take_profit_line", "enabled"], false)
                {
                    let entry_side = self
                        .grid
                        .string(&[self.pos_side.as_str(), "entry_line", "position_side"])?;
                    clean_order(client, &symbol, &entry_side, "TAKE_PROFIT").await?;
                    self.generate_take_profit()?;
                    let take_profit_line = self
                        .grid
                        .value(&[self.pos_side.as_str(), "take_profit_line"])?;
                    post_take_profit_order(client, &symbol, &take_profit_line).await?;
                }

                self.grid.save()
            }
            Some("UNLOAD") => {
                debug!(
                    "{symbol}_{} - LCD - ATTENDING UNLOAD ORDER... price: {}, quantity: {}",
                    self.pos_side, event.price, event.orig_qty
                );
                let entry_side = self
                    .grid
                    .string(&[self.pos_side.as_str(), "entry_line", "position_side"])?;
                clean_open_orders(client, &symbol, &entry_side).await?;
                self.update_current_position(client).await?;
                self.generate_grid()?;

                let stop_loss_line = self
                    .grid
                    .value(&[self.pos_side.as_str(), "stop_loss_line"])?;
                post_stop_loss_order(client, &symbol, &stop_loss_line).await?;

                let body_line = self.grid.value(&[self.pos_side.as_str(), "body_line"])?;
                post_grid_order(client, &symbol, &body_line).await?;

                if self
                    .grid
                    .bool_or(&[self.pos_side.as_str(), "take_profit_line", "enabled"], false)
                {
                    self.generate_take_profit()?;
                    let take_profit_line = self
                        .grid
                        .value(&[self.pos_side.as_str(), "take_profit_line"])?;
                    post_take_profit_order(client, &symbol, &take_profit_line).await?;
                }

                self.grid.save()
            }
            Some("STOP_LOSS") => {
                debug!(
                    "{symbol}_{} - LCD - ATTENDING STOP LOSS ORDER... price: {}, quantity: {}",
                    self.pos_side, event.price, event.orig_qty
                );
                let entry_side = self
                    .grid
                    .string(&[self.pos_side.as_str(), "entry_line", "position_side"])?;
                clean_open_orders(client, &symbol, &entry_side).await
            }
            Some("TAKE_PROFIT") => {
                debug!(
                    "{symbol}_{} - LCD - ATTENDING TAKE PROFIT ORDER... price: {}, quantity: {}",
                    self.pos_side, event.price, event.orig_qty
                );
                let entry_side = self
                    .grid
                    .string(&[self.pos_side.as_str(), "entry_line", "position_side"])?;
                clean_open_orders(client, &symbol, &entry_side).await
            }
            _ => {
                warn!(
                    "{symbol}_{} No matching operation to attend for {symbol}",
                    self.pos_side
                );
                Ok(())
            }
        }
    }

    /// Classify a fill. The Python version keyed take-profit and stop-loss on
    /// a `(type, None, None)` tuple that never matched real events; classifying
    /// by order type fixes that while keeping the LIMIT mapping identical.
    pub fn get_transaction_type(&self, event: &OrderEvent) -> Option<&'static str> {
        match event.order_type.as_str() {
            "TAKE_PROFIT_MARKET" => Some("TAKE_PROFIT"),
            "STOP_MARKET" => Some("STOP_LOSS"),
            "LIMIT" => match (event.position_side.as_str(), event.side.as_str()) {
                ("LONG", "BUY") | ("SHORT", "SELL") => Some("GRID"),
                ("LONG", "SELL") | ("SHORT", "BUY") => Some("UNLOAD"),
                _ => None,
            },
            _ => None,
        }
    }

    pub fn round_to_tick_size(&self, price: f64) -> Result<f64> {
        let tick_size = self.grid.f64(&["tick_size"])?;
        Ok(round_to_tick(price, tick_size))
    }

    pub fn generate_grid(&mut self) -> Result<()> {
        let symbol = self.grid.symbol.clone();
        debug!("{symbol} GENERATING DATA_GRID LINES...");

        let ps = self.pos_side.clone();
        self.grid.clear_array(&[ps.as_str(), "body_line"])?;

        let mut current_price = self.grid.f64(&[ps.as_str(), "current_line", "price"])?;
        let mut current_quantity = self.grid.f64(&[ps.as_str(), "current_line", "quantity"])?;

        if current_price <= 0.0 || current_quantity <= 0.0 {
            return Err(AppError::msg(format!(
                "{symbol} cannot generate a grid with price {current_price} and quantity {current_quantity}"
            )));
        }

        self.grid
            .set(&[ps.as_str(), "average_line", "price"], current_price)?;
        self.grid
            .set(&[ps.as_str(), "average_line", "quantity"], current_quantity)?;

        let stop_loss_amount = self.grid.f64(&[ps.as_str(), "risk", "stop_loss_amount"])?;
        let mut sl_distance =
            (stop_loss_amount * 100.0) / (current_price * current_quantity);
        self.grid.set(
            &[ps.as_str(), "average_line", "sl_distance"],
            sl_distance,
        )?;

        let tick_size = self.grid.f64(&["tick_size"])?;
        let quantity_precision = self.grid.i32(&["quantity_precision"])?;
        let grid_distance = self.grid.f64(&[ps.as_str(), "risk", "grid_distance"])?;
        let quantity_increment = self
            .grid
            .f64(&[ps.as_str(), "risk", "quantity_increment"])?;

        if grid_distance <= 0.0 {
            return Err(AppError::msg(format!(
                "{symbol} grid_distance must be greater than zero (got {grid_distance})"
            )));
        }

        if ps == "LONG" {
            let stop_price = round_to_tick(
                current_price - (current_price * sl_distance / 100.0),
                tick_size,
            );
            self.grid
                .set(&[ps.as_str(), "stop_loss_line", "price"], stop_price)?;
            self.grid.set(
                &[ps.as_str(), "stop_loss_line", "distance"],
                py_round((current_price - stop_price) / current_price, 4),
            )?;
        }
        if ps == "SHORT" {
            let stop_price = round_to_tick(
                current_price + (current_price * sl_distance / 100.0),
                tick_size,
            );
            self.grid
                .set(&[ps.as_str(), "stop_loss_line", "price"], stop_price)?;
            self.grid.set(
                &[ps.as_str(), "stop_loss_line", "distance"],
                py_round((stop_price - current_price) / current_price, 4),
            )?;
        }

        self.grid
            .set(&[ps.as_str(), "stop_loss_line", "quantity"], current_quantity)?;
        let current_cost = self.grid.f64(&[ps.as_str(), "current_line", "cost"])?;
        self.grid
            .set(&[ps.as_str(), "stop_loss_line", "cost"], current_cost)?;

        let mut iterations = 0usize;
        loop {
            iterations += 1;
            if iterations > MAX_GRID_LINES {
                warn!(
                    "{symbol} grid generation stopped after {MAX_GRID_LINES} lines; check grid_distance"
                );
                break;
            }

            let new_price = if ps == "LONG" {
                current_price * (1.0 - (grid_distance / 100.0))
            } else {
                current_price * (1.0 + (grid_distance / 100.0))
            };
            let new_quantity = current_quantity * (1.0 + (quantity_increment / 100.0));

            if !new_price.is_finite() || !new_quantity.is_finite() {
                warn!("{symbol} grid generation stopped: non-finite price or quantity");
                break;
            }

            let stop_price = self.grid.f64(&[ps.as_str(), "stop_loss_line", "price"])?;
            if ps == "LONG" && stop_price > new_price {
                break;
            }
            if ps == "SHORT" && new_price > stop_price {
                break;
            }

            let label = self.grid.array_len(&[ps.as_str(), "body_line"]) + 1;
            self.grid.push(
                &[ps.as_str(), "body_line"],
                json!({
                    "label": label,
                    "side": if ps == "LONG" { "BUY" } else { "SELL" },
                    "position_side": ps,
                    "price": round_to_tick(new_price, tick_size),
                    "quantity": py_round(new_quantity, quantity_precision),
                    "type": "LIMIT",
                    "cost": py_round(new_price * new_quantity, 2),
                    "status": "NEW"
                }),
            )?;

            let average_price = self.grid.f64(&[ps.as_str(), "average_line", "price"])?;
            let average_quantity = self.grid.f64(&[ps.as_str(), "average_line", "quantity"])?;
            let new_average_price = round_to_tick(
                ((average_price * average_quantity) + (new_price * new_quantity))
                    / (average_quantity + new_quantity),
                tick_size,
            );
            let new_average_quantity =
                py_round(average_quantity + new_quantity, quantity_precision);
            self.grid
                .set(&[ps.as_str(), "average_line", "price"], new_average_price)?;
            self.grid.set(
                &[ps.as_str(), "average_line", "quantity"],
                new_average_quantity,
            )?;

            sl_distance = (stop_loss_amount * 100.0) / (new_average_price * new_average_quantity);
            self.grid.set(
                &[ps.as_str(), "average_line", "sl_distance"],
                sl_distance,
            )?;

            if ps == "LONG" {
                let price = round_to_tick(
                    new_average_price - (new_average_price * sl_distance / 100.0),
                    tick_size,
                );
                self.grid
                    .set(&[ps.as_str(), "stop_loss_line", "price"], price)?;
                self.grid.set(
                    &[ps.as_str(), "stop_loss_line", "distance"],
                    py_round((current_price - price) / current_price, 4),
                )?;
            }
            if ps == "SHORT" {
                let price = round_to_tick(
                    new_average_price + (new_average_price * sl_distance / 100.0),
                    tick_size,
                );
                self.grid
                    .set(&[ps.as_str(), "stop_loss_line", "price"], price)?;
                self.grid.set(
                    &[ps.as_str(), "stop_loss_line", "distance"],
                    py_round((price - current_price) / current_price, 4),
                )?;
            }

            let stop_quantity = self.grid.f64(&[ps.as_str(), "stop_loss_line", "quantity"])?;
            let stop_cost = self.grid.f64(&[ps.as_str(), "stop_loss_line", "cost"])?;
            self.grid.set(
                &[ps.as_str(), "stop_loss_line", "quantity"],
                py_round(stop_quantity + new_quantity, quantity_precision),
            )?;
            self.grid.set(
                &[ps.as_str(), "stop_loss_line", "cost"],
                py_round(stop_cost + (new_price * new_quantity), 2),
            )?;

            current_price = new_price;
            current_quantity = new_quantity;
        }

        debug!(
            "{symbol} body_line generated: {}",
            self.grid.value(&[ps.as_str(), "body_line"])?
        );
        debug!(
            "{symbol} stop_loss_line generated: {}",
            self.grid.value(&[ps.as_str(), "stop_loss_line"])?
        );
        Ok(())
    }

    pub fn generate_take_profit(&mut self) -> Result<()> {
        let ps = self.pos_side.clone();
        let entry_side = self
            .grid
            .string(&[ps.as_str(), "entry_line", "position_side"])?;
        let distance = self
            .grid
            .f64(&[ps.as_str(), "take_profit_line", "distance"])?;
        let current_price = self.grid.f64(&[ps.as_str(), "current_line", "price"])?;

        let factor = if entry_side == "LONG" {
            1.0 + distance / 100.0
        } else {
            1.0 - distance / 100.0
        };
        let price = self.round_to_tick_size(current_price * factor)?;

        self.grid
            .set(&[ps.as_str(), "take_profit_line", "price"], price)?;
        debug!(
            "{} take_profit_line generated: {}",
            self.grid.symbol,
            self.grid.value(&[ps.as_str(), "take_profit_line"])?
        );
        Ok(())
    }

    pub fn generate_unload_order(&mut self) -> Result<()> {
        let ps = self.pos_side.clone();
        let current_side = self
            .grid
            .string(&[ps.as_str(), "current_line", "position_side"])?;
        let distance = self.grid.f64(&[ps.as_str(), "unload_line", "distance"])?;
        let current_price = self.grid.f64(&[ps.as_str(), "current_line", "price"])?;
        let current_quantity = self.grid.f64(&[ps.as_str(), "current_line", "quantity"])?;
        let entry_quantity = self.grid.f64(&[ps.as_str(), "entry_line", "quantity"])?;
        let quantity_precision = self.grid.i32(&["quantity_precision"])?;

        let factor = if current_side == "LONG" {
            1.0 + distance / 100.0
        } else {
            1.0 - distance / 100.0
        };
        let price = self.round_to_tick_size(current_price * factor)?;
        let price = {
            let tick_size = self.grid.f64(&["tick_size"])?;
            round_to_tick(price, tick_size)
        };
        let quantity = py_round(current_quantity - entry_quantity, quantity_precision);

        self.grid.set(&[ps.as_str(), "unload_line", "price"], price)?;
        self.grid
            .set(&[ps.as_str(), "unload_line", "quantity"], quantity)?;
        debug!(
            "{} UNLOAD generated: {}",
            self.grid.symbol,
            self.grid.value(&[ps.as_str(), "unload_line"])?
        );
        Ok(())
    }

    pub async fn update_current_position(&mut self, client: &BinanceClient) -> Result<()> {
        let symbol = self.grid.symbol.clone();
        debug!("{symbol} UPDATING CURRENT POSITION...");

        let positions = client.position_information(&symbol).await?;
        for position in &positions {
            if position.position_side == self.pos_side {
                let entry_price = position.entry_price.parse::<f64>().unwrap_or(0.0);
                let quantity = position.position_amt.parse::<f64>().unwrap_or(0.0).abs();
                let tick_size = self.grid.f64(&["tick_size"])?;
                let price = round_to_tick(entry_price, tick_size);
                let ps = self.pos_side.as_str();

                self.grid.set(&[ps, "current_line", "price"], price)?;
                self.grid.set(&[ps, "current_line", "quantity"], quantity)?;
                self.grid
                    .set(&[ps, "current_line", "cost"], py_round(price * quantity, 2))?;
                self.grid.set(
                    &[ps, "current_line", "position_side"],
                    Value::from(position.position_side.clone()),
                )?;
                debug!("{symbol} Current position from Binance: {position:?}");
                break;
            }
        }
        Ok(())
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    fn grid() -> LUGrid {
        let data = json!({
            "strategy": "THE_LOAD_UNLOAD_GRID",
            "symbol": "BTCUSDT",
            "input_side": "LONG",
            "price_precision": 1,
            "quantity_precision": 3,
            "tick_size": 0.1,
            "step_size": 0.001,
            "LONG": {
                "risk": {
                    "wallet_balance_usdt": 1000.0,
                    "percentage": 10,
                    "risk_amount": 100.0,
                    "grid_distance": 2.0,
                    "quantity_increment": 40.0,
                    "stop_loss_amount": 10.0
                },
                "entry_line": { "side": "BUY", "position_side": "LONG", "price": 100.0, "quantity": 1.0, "cost": 100.0, "status": "FILLED" },
                "take_profit_line": { "enabled": true, "position_side": "LONG", "distance": 5.0, "price": 0.0 },
                "unload_line": { "enabled": true, "position_side": "LONG", "distance": 0.5, "price": 0.0, "quantity": 0.0 },
                "stop_loss_line": { "enabled": true, "position_side": "LONG", "price": 0.0, "quantity": 0.0, "cost": 100.0, "distance": 0.0 },
                "average_line": { "price": 0.0, "quantity": 0.0, "sl_distance": 0.0 },
                "current_line": { "position_side": "LONG", "price": 100.0, "quantity": 1.0, "cost": 100.0 },
                "body_line": []
            },
            "SHORT": {
                "risk": {
                    "wallet_balance_usdt": 1000.0,
                    "percentage": 10,
                    "risk_amount": 100.0,
                    "grid_distance": 2.0,
                    "quantity_increment": 40.0,
                    "stop_loss_amount": 10.0
                },
                "entry_line": { "side": "SELL", "position_side": "SHORT", "price": 100.0, "quantity": 1.0, "cost": 100.0, "status": "FILLED" },
                "take_profit_line": { "enabled": true, "position_side": "SHORT", "distance": 5.0, "price": 0.0 },
                "unload_line": { "enabled": true, "position_side": "SHORT", "distance": 0.5, "price": 0.0, "quantity": 0.0 },
                "stop_loss_line": { "enabled": true, "position_side": "SHORT", "price": 0.0, "quantity": 0.0, "cost": 100.0, "distance": 0.0 },
                "average_line": { "price": 0.0, "quantity": 0.0, "sl_distance": 0.0 },
                "current_line": { "position_side": "SHORT", "price": 100.0, "quantity": 1.0, "cost": 100.0 },
                "body_line": []
            }
        });
        LUGrid {
            grid: Grid::from_value("BTCUSDT", data),
            pos_side: "LONG".into(),
        }
    }

    #[test]
    fn long_grid_generates_lines_below_entry() {
        let mut lu = grid();
        lu.generate_grid().unwrap();
        let body = lu.grid.at(&["LONG", "body_line"]).unwrap();
        let lines = body.as_array().unwrap();
        assert!(!lines.is_empty());
        assert_eq!(lines[0]["price"], 98.0);
        assert!(lines.iter().all(|line| line["price"].as_f64().unwrap() < 100.0));

        let stop = lu
            .grid
            .f64(&["LONG", "stop_loss_line", "price"])
            .unwrap();
        assert!(stop < 100.0);
    }

    #[test]
    fn short_grid_generates_lines_above_entry() {
        let mut lu = grid();
        lu.pos_side = "SHORT".into();
        lu.generate_grid().unwrap();
        let body = lu.grid.at(&["SHORT", "body_line"]).unwrap();
        let lines = body.as_array().unwrap();
        assert!(!lines.is_empty());
        assert_eq!(lines[0]["price"], 102.0);
        assert!(lines.iter().all(|line| line["price"].as_f64().unwrap() > 100.0));
    }

    #[test]
    fn zero_grid_distance_is_rejected() {
        let mut lu = grid();
        lu.grid
            .set(&["LONG", "risk", "grid_distance"], 0.0)
            .unwrap();
        assert!(lu.generate_grid().is_err());
        assert_eq!(lu.grid.array_len(&["LONG", "body_line"]), 0);
    }

    #[test]
    fn transaction_types_match_limit_fills() {
        let lu = grid();
        let mut event = OrderEvent {
            order_type: "LIMIT".into(),
            position_side: "LONG".into(),
            side: "BUY".into(),
            ..Default::default()
        };
        assert_eq!(lu.get_transaction_type(&event), Some("GRID"));
        event.side = "SELL".into();
        assert_eq!(lu.get_transaction_type(&event), Some("UNLOAD"));
        event.order_type = "STOP_MARKET".into();
        assert_eq!(lu.get_transaction_type(&event), Some("STOP_LOSS"));
        event.order_type = "TAKE_PROFIT_MARKET".into();
        assert_eq!(lu.get_transaction_type(&event), Some("TAKE_PROFIT"));
    }
}
