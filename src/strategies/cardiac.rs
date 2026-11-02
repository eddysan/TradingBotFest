//! CARDIAC strategy — Rust port of `package_cardiac.py`.

use crate::error::{AppError, Result};
use crate::exchange::models::OrderEvent;
use crate::exchange::BinanceClient;
use crate::orders::{
    clean_open_orders, post_limit_order, post_stop_loss_order, post_take_profit_order,
};
use crate::store::{self, Grid};
use crate::util::{
    base_asset, prompt, prompt_f64, prompt_f64_or, py_round, round_to_tick,
};
use serde_json::Value;
use tracing::{debug, info};

/// Prompt for a trade, persist the state file and return the symbol.
///
/// Returns `None` when an existing position was found and its protection
/// orders were regenerated, matching the original control flow.
pub async fn input_data(client: &BinanceClient) -> Result<Option<String>> {
    debug!("INPUT DATA...");
    let mut grid = Grid::from_value(
        "config/cardiac.json",
        store::read_json_required("config/cardiac.json")?,
    );

    let base = prompt("Symbol (BTC): ")?.to_uppercase();
    let symbol = format!("{base}USDT");
    grid.set_top_level("symbol", Value::from(symbol.clone()))?;

    let side = prompt("Side (LONG|SHORT): ")?.to_uppercase();
    let pos_side = if side.is_empty() { "LONG".to_string() } else { side };
    grid.set_top_level("input_side", Value::from(pos_side.clone()))?;

    let positions = client.position_information(&symbol).await?;
    for position in &positions {
        let amount = position.position_amt.parse::<f64>().unwrap_or(0.0);
        if amount != 0.0 && position.position_side == pos_side {
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
            grid.set(
                &[pos_side.as_str(), "entry_line", "price"],
                entry_price,
            )?;
            grid.set(
                &[pos_side.as_str(), "entry_line", "quantity"],
                amount.abs(),
            )?;
            grid.set(
                &[pos_side.as_str(), "entry_line", "status"],
                Value::from("FILLED"),
            )?;
        }
    }

    let wallet_balance = client.wallet_balance_usdt().await?;
    let percentage = grid.f64(&[pos_side.as_str(), "risk", "percentage"])?;
    let risk_amount = py_round(wallet_balance * (percentage / 100.0), 2);
    grid.set(
        &[pos_side.as_str(), "risk", "wallet_balance_usdt"],
        wallet_balance,
    )?;
    grid.set(&[pos_side.as_str(), "risk", "amount"], risk_amount)?;

    let filters = client.symbol_filters(&symbol).await?;
    grid.set_top_level("step_size", Value::from(filters.step_size))?;
    grid.set_top_level("tick_size", Value::from(filters.tick_size))?;
    grid.set_top_level(
        "price_precision",
        Value::from(filters.price_precision),
    )?;
    grid.set_top_level(
        "quantity_precision",
        Value::from(filters.quantity_precision),
    )?;

    let status = grid.string(&[pos_side.as_str(), "entry_line", "status"])?;
    if status != "FILLED" {
        let tick_size = grid.f64(&["tick_size"])?;
        let entry_price = prompt_f64("Entry Price ($): ")?;
        let entry_price = round_to_tick(entry_price, tick_size);
        grid.set(
            &[pos_side.as_str(), "entry_line", "price"],
            entry_price,
        )?;

        let quantity_precision = grid.i32(&["quantity_precision"])?;
        let entry_token = py_round(risk_amount / entry_price, quantity_precision);
        let quantity = prompt_f64_or(
            &format!(
                "Entry Quantity ({entry_token} {}): ",
                base_asset(&symbol)
            ),
            entry_token,
        )?;
        grid.set(
            &[pos_side.as_str(), "entry_line", "quantity"],
            quantity,
        )?;
        grid.set(
            &[pos_side.as_str(), "entry_line", "status"],
            Value::from("NEW"),
        )?;
    }

    let risk_amount = grid.f64(&[pos_side.as_str(), "risk", "amount"])?;
    let stop_loss_amount = prompt_f64_or(
        &format!("Stop Loss Amount ({risk_amount}$): "),
        risk_amount,
    )?;
    grid.set(
        &[pos_side.as_str(), "risk", "stop_loss_amount"],
        stop_loss_amount,
    )?;

    write_operation_file(&symbol, &mut grid, &pos_side)?;

    if grid.string(&[pos_side.as_str(), "entry_line", "status"])? == "FILLED" {
        let mut cardiac = CardiacGrid::new(&symbol)?;
        cardiac.attend_filled(client, &pos_side).await?;
        return Ok(None);
    }

    Ok(Some(symbol))
}

fn write_operation_file(symbol: &str, grid: &mut Grid, pos_side: &str) -> Result<()> {
    let ops_path = store::ops_path(symbol);
    let data = if ops_path.exists() {
        let mut existing = store::read_json_required(&ops_path)?;
        let strategy = existing
            .get("strategy")
            .and_then(Value::as_str)
            .unwrap_or_default()
            .to_string();
        if strategy == "CARDIAC" {
            if let Value::Object(map) = &mut existing {
                map.insert(
                    pos_side.to_string(),
                    grid.value(&[pos_side])?,
                );
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

pub struct CardiacGrid {
    pub grid: Grid,
}

impl CardiacGrid {
    pub fn new(symbol: &str) -> Result<Self> {
        Ok(Self {
            grid: Grid::load(symbol)?,
        })
    }

    /// Post the configured entry order.
    pub async fn post_order(&mut self, client: &BinanceClient) -> Result<()> {
        let side = self.grid.string(&["input_side"])?;
        let line = self.grid.value(&[side.as_str(), "entry_line"])?;
        let symbol = self.grid.symbol.clone();
        post_limit_order(client, &symbol, &line).await?;
        self.grid.save()
    }

    /// Handle a user-data order event.
    pub async fn attend_message(
        &mut self,
        client: &BinanceClient,
        event: &OrderEvent,
    ) -> Result<()> {
        if event.status != "FILLED" {
            return Ok(());
        }
        self.attend_filled(client, &event.position_side).await
    }

    /// Rebuild stop-loss, unload and take-profit lines for a filled position.
    pub async fn attend_filled(
        &mut self,
        client: &BinanceClient,
        pos_side: &str,
    ) -> Result<()> {
        let symbol = self.grid.symbol.clone();

        clean_open_orders(client, &symbol, pos_side).await?;
        self.update_current_position(client, pos_side).await?;

        let current_quantity = self
            .grid
            .f64(&[pos_side, "current_line", "quantity"])?;

        if current_quantity != 0.0 {
            if self.grid.bool_or(&[pos_side, "stop_loss_line", "enabled"], false) {
                self.generate_stop_loss(pos_side)?;
                let line = self.grid.value(&[pos_side, "stop_loss_line"])?;
                post_stop_loss_order(client, &symbol, &line).await?;
            }

            if self.grid.bool_or(&[pos_side, "unload_line", "enabled"], false) {
                self.generate_unload(pos_side)?;
                let line = self.grid.value(&[pos_side, "unload_line"])?;
                post_limit_order(client, &symbol, &line).await?;
            }

            if self
                .grid
                .bool_or(&[pos_side, "take_profit_line", "enabled"], false)
            {
                self.generate_take_profit(pos_side)?;
                let line = self.grid.value(&[pos_side, "take_profit_line"])?;
                post_take_profit_order(client, &symbol, &line).await?;
            }
        }

        self.grid.save()
    }

    pub fn round_to_tick_size(&self, price: f64) -> Result<f64> {
        let tick_size = self.grid.f64(&["tick_size"])?;
        Ok(round_to_tick(price, tick_size))
    }

    pub async fn update_current_position(
        &mut self,
        client: &BinanceClient,
        pos_side: &str,
    ) -> Result<()> {
        let symbol = self.grid.symbol.clone();
        info!("{symbol} - UPDATING CURRENT POSITION...");

        let positions = client.position_information(&symbol).await?;
        let Some(position) = positions
            .iter()
            .find(|position| position.position_side == pos_side)
        else {
            info!("{symbol} - No relevant position found for side: {pos_side}");
            return Ok(());
        };

        let entry_price = position.entry_price.parse::<f64>().unwrap_or(0.0);
        let position_amount = position.position_amt.parse::<f64>().unwrap_or(0.0).abs();
        let quantity_precision = self.grid.i32(&["quantity_precision"])?;

        self.grid.set(
            &[pos_side, "current_line", "price"],
            self.round_to_tick_size(entry_price)?,
        )?;
        self.grid.set(
            &[pos_side, "current_line", "quantity"],
            py_round(position_amount, quantity_precision),
        )?;

        debug!("{symbol} Current position from Binance: {position:?}");
        Ok(())
    }

    pub fn generate_stop_loss(&mut self, pos_side: &str) -> Result<()> {
        let symbol = self.grid.symbol.clone();
        info!("{symbol} - GENERATING STOP_LOSS DATA...");

        let stop_loss_amount =
            self.grid.f64(&[pos_side, "risk", "stop_loss_amount"])?;
        let price = self.grid.f64(&[pos_side, "current_line", "price"])?;
        let quantity = self.grid.f64(&[pos_side, "current_line", "quantity"])?;

        if price == 0.0 || quantity == 0.0 {
            return Err(AppError::msg(format!(
                "{symbol} cannot compute stop loss with price {price} and quantity {quantity}"
            )));
        }

        let distance = (stop_loss_amount * 100.0) / (price * quantity);
        self.grid.set(&[pos_side, "current_line", "distance"], distance)?;

        let stop_side = self
            .grid
            .string(&[pos_side, "stop_loss_line", "position_side"])?;

        match stop_side.as_str() {
            "LONG" => {
                let stop_price =
                    round_to_tick(price - (price * distance / 100.0), self.tick()?).abs();
                self.grid
                    .set(&[pos_side, "stop_loss_line", "price"], stop_price)?;
                self.grid.set(
                    &[pos_side, "stop_loss_line", "distance"],
                    py_round((price - stop_price) / price, 4),
                )?;
            }
            "SHORT" => {
                let stop_price =
                    round_to_tick(price + (price * distance / 100.0), self.tick()?).abs();
                self.grid
                    .set(&[pos_side, "stop_loss_line", "price"], stop_price)?;
                self.grid.set(
                    &[pos_side, "stop_loss_line", "distance"],
                    py_round((stop_price - price) / price, 4),
                )?;
            }
            other => {
                return Err(AppError::msg(format!(
                    "{symbol} unexpected stop-loss position side: {other}"
                )))
            }
        }

        self.grid
            .set(&[pos_side, "stop_loss_line", "quantity"], quantity)?;
        debug!(
            "{symbol}_{stop_side} stop_loss_line generated: {}",
            self.grid.value(&[pos_side, "stop_loss_line"])?
        );
        Ok(())
    }

    pub fn generate_take_profit(&mut self, pos_side: &str) -> Result<()> {
        let stop_side = self
            .grid
            .string(&[pos_side, "take_profit_line", "position_side"])?;
        let distance = self
            .grid
            .f64(&[pos_side, "take_profit_line", "distance"])?;
        let current_price = self.grid.f64(&[pos_side, "current_line", "price"])?;

        let factor = if stop_side == "LONG" {
            1.0 + distance / 100.0
        } else {
            1.0 - distance / 100.0
        };
        let price = round_to_tick(current_price * factor, self.tick()?);

        self.grid
            .set(&[pos_side, "take_profit_line", "price"], price)?;
        debug!(
            "{} take_profit_line generated: {}",
            self.grid.symbol,
            self.grid.value(&[pos_side, "take_profit_line"])?
        );
        Ok(())
    }

    pub fn generate_unload(&mut self, pos_side: &str) -> Result<()> {
        let unload_side = self
            .grid
            .string(&[pos_side, "unload_line", "position_side"])?;
        let distance = self.grid.f64(&[pos_side, "unload_line", "distance"])?;
        let current_price = self.grid.f64(&[pos_side, "current_line", "price"])?;
        let current_quantity = self
            .grid
            .f64(&[pos_side, "current_line", "quantity"])?;
        let entry_quantity = self.grid.f64(&[pos_side, "entry_line", "quantity"])?;
        let quantity_precision = self.grid.i32(&["quantity_precision"])?;

        let factor = if unload_side == "LONG" {
            1.0 + distance / 100.0
        } else {
            1.0 - distance / 100.0
        };
        let price = round_to_tick(current_price * factor, self.tick()?);
        let quantity = py_round(current_quantity - entry_quantity, quantity_precision);

        self.grid.set(&[pos_side, "unload_line", "price"], price)?;
        self.grid
            .set(&[pos_side, "unload_line", "quantity"], quantity)?;
        debug!(
            "{} unload_line to post: {}",
            self.grid.symbol,
            self.grid.value(&[pos_side, "unload_line"])?
        );
        Ok(())
    }

    fn tick(&self) -> Result<f64> {
        self.grid.f64(&["tick_size"])
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    fn grid() -> CardiacGrid {
        let data = json!({
            "strategy": "CARDIAC",
            "symbol": "BTCUSDT",
            "input_side": "LONG",
            "price_precision": 1,
            "quantity_precision": 3,
            "tick_size": 0.1,
            "step_size": 0.001,
            "LONG": {
                "risk": { "percentage": 10, "amount": 100.0, "wallet_balance_usdt": 1000.0, "stop_loss_amount": 10.0 },
                "entry_line": { "label": "ENTRY", "side": "BUY", "position_side": "LONG", "price": 100.0, "quantity": 1.0, "status": "FILLED" },
                "take_profit_line": { "enabled": true, "label": "TAKE_PROFIT", "side": "SELL", "position_side": "LONG", "distance": 1.0, "price": 0.0, "quantity": 0.0 },
                "unload_line": { "enabled": true, "label": "UNLOAD", "side": "SELL", "position_side": "LONG", "distance": 0.25, "price": 0.0, "quantity": 0.0 },
                "stop_loss_line": { "enabled": true, "label": "STOP_LOSS", "side": "SELL", "position_side": "LONG", "distance": 0.0, "price": 0.0, "quantity": 0.0 },
                "current_line": { "price": 100.0, "distance": 0.0, "quantity": 1.0, "position_side": "LONG" }
            },
            "SHORT": {
                "risk": { "percentage": 10, "amount": 100.0, "wallet_balance_usdt": 1000.0, "stop_loss_amount": 10.0 },
                "entry_line": { "label": "ENTRY", "side": "SELL", "position_side": "SHORT", "price": 100.0, "quantity": 1.0, "status": "FILLED" },
                "take_profit_line": { "enabled": true, "label": "TAKE_PROFIT", "side": "BUY", "position_side": "SHORT", "distance": 1.0, "price": 0.0, "quantity": 0.0 },
                "unload_line": { "enabled": true, "label": "UNLOAD", "side": "BUY", "position_side": "SHORT", "distance": 0.25, "price": 0.0, "quantity": 0.0 },
                "stop_loss_line": { "enabled": true, "label": "STOP_LOSS", "side": "BUY", "position_side": "SHORT", "distance": 0.0, "price": 0.0, "quantity": 0.0 },
                "current_line": { "price": 100.0, "distance": 0.0, "quantity": 1.0, "position_side": "SHORT" }
            }
        });
        CardiacGrid {
            grid: Grid::from_value("BTCUSDT", data),
        }
    }

    #[test]
    fn long_stop_loss_is_below_entry() {
        let mut cardiac = grid();
        cardiac.generate_stop_loss("LONG").unwrap();
        let price = cardiac
            .grid
            .f64(&["LONG", "stop_loss_line", "price"])
            .unwrap();
        assert_eq!(price, 90.0);
        let distance = cardiac
            .grid
            .f64(&["LONG", "stop_loss_line", "distance"])
            .unwrap();
        assert_eq!(distance, 0.1);
    }

    #[test]
    fn short_stop_loss_is_above_entry() {
        let mut cardiac = grid();
        cardiac.generate_stop_loss("SHORT").unwrap();
        let price = cardiac
            .grid
            .f64(&["SHORT", "stop_loss_line", "price"])
            .unwrap();
        assert_eq!(price, 110.0);
    }

    #[test]
    fn take_profit_and_unload_use_side_direction() {
        let mut cardiac = grid();
        cardiac.generate_take_profit("LONG").unwrap();
        cardiac.generate_unload("LONG").unwrap();
        assert_eq!(
            cardiac
                .grid
                .f64(&["LONG", "take_profit_line", "price"])
                .unwrap(),
            101.0
        );
        assert_eq!(
            cardiac
                .grid
                .f64(&["LONG", "unload_line", "quantity"])
                .unwrap(),
            0.0
        );

        cardiac.generate_take_profit("SHORT").unwrap();
        assert_eq!(
            cardiac
                .grid
                .f64(&["SHORT", "take_profit_line", "price"])
                .unwrap(),
            99.0
        );
    }
}
