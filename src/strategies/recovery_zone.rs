//! RECOVERY ZONE strategy — Rust port of `package_recoveryzone.py`.

use crate::error::{AppError, Result};
use crate::exchange::models::OrderEvent;
use crate::exchange::BinanceClient;
use crate::orders::{
    clean_all_open_orders, clean_order, post_grid_order, post_hedge_order, post_stop_loss_order,
    post_take_profit_order, post_trailing_stop_order,
};
use crate::store::{self, Grid};
use crate::util::{
    get_distance, prompt, prompt_f64, prompt_f64_or, prompt_i32_or, py_round, round_to_tick,
};
use serde_json::{json, Value};
use tracing::{debug, info};

fn opposite(side: &str) -> &'static str {
    if side == "LONG" {
        "SHORT"
    } else {
        "LONG"
    }
}

pub async fn input_data(client: &BinanceClient) -> Result<String> {
    debug!("INPUT DATA");

    let mut grid = Grid::from_value(
        "config/recoveryzone.json",
        store::read_json_required("config/recoveryzone.json")?,
    );

    let base = prompt("Symbol (BTC): ")?.to_uppercase();
    let symbol = format!("{base}USDT");
    grid.set_top_level("symbol", Value::from(symbol.clone()))?;

    let side = prompt("Side (LONG|SHORT): ")?.to_uppercase();
    let pos_side = if side.is_empty() { "LONG".to_string() } else { side };
    let opos_side = opposite(&pos_side).to_string();
    grid.set_top_level("input_side", Value::from(pos_side.clone()))?;

    let filters = client.symbol_filters(&symbol).await?;
    grid.set_top_level("tick_size", Value::from(filters.tick_size))?;
    grid.set_top_level("price_precision", Value::from(filters.price_precision))?;
    grid.set_top_level(
        "quantity_precision",
        Value::from(filters.quantity_precision),
    )?;

    let nentries = prompt_i32_or("Number of entries (1|2): ", 1)?;
    let tick_size = grid.f64(&["tick_size"])?;
    let quantity_precision = grid.i32(&["quantity_precision"])?;

    let positions = client.position_information(&symbol).await?;
    for position in &positions {
        let amount = position.position_amt.parse::<f64>().unwrap_or(0.0);
        if amount != 0.0 && position.position_side == pos_side {
            let entry_price = position.entry_price.parse::<f64>().unwrap_or(0.0);
            println!(
                " There is a current position as entry values... \n\
                 Position side: {} \n\
                 Entry Price: {} \n\
                 Entry Quantity: {}",
                position.position_side,
                position.entry_price,
                amount.abs()
            );

            let second_price = prompt_f64("Entry second price ($): ")?;
            let side = if pos_side == "LONG" { "BUY" } else { "SELL" };
            let entry_line = json!([
                {
                    "label": "first entry",
                    "price": round_to_tick(entry_price, tick_size),
                    "quantity": amount.abs(),
                    "side": side,
                    "position_side": pos_side,
                    "cost": py_round(entry_price * amount.abs(), 2),
                    "status": "FILLED"
                },
                {
                    "label": "second entry",
                    "price": round_to_tick(second_price, tick_size),
                    "quantity": if nentries == 2 { amount.abs() } else { 0.0 },
                    "side": side,
                    "position_side": pos_side,
                    "cost": py_round(second_price * amount.abs(), 2),
                    "status": if nentries == 2 { "NEW" } else { "CANCELLED" }
                }
            ]);
            grid.set(&[pos_side.as_str(), "entry_line"], entry_line)?;

            let take_profit = prompt_f64("Take profit price: ")?;
            grid.set(
                &[pos_side.as_str(), "take_profit_line", "price"],
                round_to_tick(take_profit, tick_size),
            )?;
        }
    }

    let target_factor = grid.f64(&["risk", "target_factor"])?;
    if target_factor == 0.0 {
        return Err(AppError::msg("risk.target_factor must not be zero"));
    }
    grid.set(
        &["risk", "product_factor"],
        py_round((target_factor + 1.0) / target_factor, 2),
    )?;

    let wallet_balance = client.wallet_balance_usdt().await?;
    grid.set(&["risk", "wallet_balance_usdt"], wallet_balance)?;

    if grid.array_len(&[pos_side.as_str(), "entry_line"]) == 0 {
        let first_price = prompt_f64("First entry price ($): ")?;
        let second_price = prompt_f64("Second entry price ($): ")?;
        let take_profit = prompt_f64("Take profit price: ")?;
        grid.set(
            &[pos_side.as_str(), "take_profit_line", "price"],
            round_to_tick(take_profit, tick_size),
        )?;

        let distance = get_distance(first_price, second_price);
        if distance == 0.0 {
            return Err(AppError::msg(
                "entry prices must differ so a recovery distance can be computed",
            ));
        }
        if first_price == 0.0 || second_price == 0.0 {
            return Err(AppError::msg("entry prices must be greater than zero"));
        }

        let min_risk = grid.f64(&["risk", "min_risk"])?;
        let suggested_quantity = py_round((wallet_balance * min_risk) / distance, 2);
        let usdt_quantity = prompt_f64_or(
            &format!("Entry quantity ({suggested_quantity}$): "),
            suggested_quantity,
        )?;

        let (first_quantity, second_quantity) = match nentries {
            1 => (
                py_round(usdt_quantity / first_price, quantity_precision),
                0.0,
            ),
            2 => (
                py_round((usdt_quantity / 2.0) / first_price, quantity_precision),
                py_round((usdt_quantity / 2.0) / second_price, quantity_precision),
            ),
            _ => (0.0, 0.0),
        };

        let side = if pos_side == "LONG" { "BUY" } else { "SELL" };
        let entry_line = json!([
            {
                "label": "first entry",
                "price": round_to_tick(first_price, tick_size),
                "quantity": first_quantity,
                "side": side,
                "position_side": pos_side,
                "cost": py_round(first_price * first_quantity, 2),
                "status": "NEW"
            },
            {
                "label": "second entry",
                "price": round_to_tick(second_price, tick_size),
                "quantity": second_quantity,
                "side": side,
                "position_side": pos_side,
                "cost": py_round(second_price * second_quantity, 2),
                "status": if second_quantity != 0.0 { "NEW" } else { "CANCELLED" }
            }
        ]);
        grid.set(&[pos_side.as_str(), "entry_line"], entry_line)?;
    }

    // Hedge line on the opposite side, anchored to the second entry.
    let entry_line = grid.value(&[pos_side.as_str(), "entry_line"])?;
    let entries = entry_line
        .as_array()
        .ok_or_else(|| AppError::msg("entry_line must be an array"))?;
    let second_entry_price = entries
        .get(1)
        .and_then(|entry| entry.get("price"))
        .and_then(Value::as_f64)
        .ok_or_else(|| AppError::msg("second entry price is missing"))?;
    let total_quantity: f64 = entries
        .iter()
        .take(2)
        .filter_map(|entry| entry.get("quantity").and_then(Value::as_f64))
        .sum();

    let hedge_distance = grid.f64(&["risk", "hedge_distance"])?;
    let hedge_price = if opos_side == "LONG" {
        round_to_tick(
            second_entry_price * (1.0 + (hedge_distance / 100.0)),
            tick_size,
        )
    } else {
        round_to_tick(
            second_entry_price * (1.0 - (hedge_distance / 100.0)),
            tick_size,
        )
    };
    grid.set(&[opos_side.as_str(), "hedge_line", "price"], hedge_price)?;

    let product_factor = grid.f64(&["risk", "product_factor"])?;
    grid.set(
        &[opos_side.as_str(), "hedge_line", "quantity"],
        py_round(product_factor * total_quantity, quantity_precision),
    )?;

    store::write_json(
        store::ops_dir(),
        &format!("{symbol}.json"),
        &grid.data,
    )?;

    Ok(symbol)
}

pub struct RecoveryZone {
    pub grid: Grid,
    pub pos_side: String,
    pub opos_side: String,
}

impl RecoveryZone {
    pub fn new(symbol: &str) -> Result<Self> {
        Ok(Self {
            grid: Grid::load(symbol)?,
            pos_side: "NONE".into(),
            opos_side: "NONE".into(),
        })
    }

    pub async fn post_orders(&mut self, client: &BinanceClient) -> Result<()> {
        self.pos_side = self.grid.string(&["input_side"])?;
        self.opos_side = opposite(&self.pos_side).to_string();
        let symbol = self.grid.symbol.clone();

        let entry_line = self
            .grid
            .value(&[self.pos_side.as_str(), "entry_line"])?;
        post_grid_order(client, &symbol, &entry_line).await?;

        let hedge_line = self
            .grid
            .value(&[self.opos_side.as_str(), "hedge_line"])?;
        post_hedge_order(client, &symbol, &hedge_line).await?;

        if self
            .grid
            .bool_or(&[self.pos_side.as_str(), "take_profit_line", "enabled"], false)
        {
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
        self.opos_side = opposite(&self.pos_side).to_string();
        let symbol = self.grid.symbol.clone();
        let orig_type = if event.orig_type.is_empty() {
            event.order_type.as_str()
        } else {
            event.orig_type.as_str()
        };

        match (orig_type, event.close_position) {
            ("LIMIT", _) => {
                info!(
                    "{symbol}_{} - RECOVERY_ZONE - hedge_line - Price: {} | Quantity: {} ...FILLED",
                    self.pos_side, event.price, event.orig_qty
                );
                self.update_current_position(client).await?;

                if self.grid.bool_or(
                    &[self.pos_side.as_str(), "trailing_stop_line", "enabled"],
                    false,
                ) {
                    let side = self.pos_side.clone();
                    clean_order(client, &symbol, &side, "TRAILING_STOP_MARKET").await?;
                    self.generate_trailing_stop()?;
                    let trailing = self
                        .grid
                        .value(&[self.pos_side.as_str(), "trailing_stop_line"])?;
                    post_trailing_stop_order(client, &symbol, &trailing).await?;
                }

                self.grid.save()
            }

            ("STOP_MARKET", false) => {
                info!(
                    "{symbol}_{} - RECOVERY_ZONE - HEDGE - Price: {} | Quantity: {} ...FILLED",
                    self.pos_side, event.price, event.orig_qty
                );
                self.update_current_position(client).await?;
                clean_all_open_orders(client, &symbol).await?;

                let long_quantity = self.grid.f64(&["LONG", "hedge_line", "quantity"])?;
                let short_quantity = self.grid.f64(&["SHORT", "hedge_line", "quantity"])?;

                if long_quantity != short_quantity {
                    let min_risk = self.grid.f64(&["risk", "min_risk"])?;
                    let product_factor = self.grid.f64(&["risk", "product_factor"])?;
                    let new_risk = py_round(min_risk * product_factor, 2);
                    self.grid.set(&["risk", "min_risk"], new_risk)?;

                    let max_risk = self.grid.f64(&["risk", "max_risk"])?;
                    let quantity_precision = self.grid.i32(&["quantity_precision"])?;
                    let pos_quantity = self
                        .grid
                        .f64(&[self.pos_side.as_str(), "hedge_line", "quantity"])?;
                    let opos_quantity = self
                        .grid
                        .f64(&[self.opos_side.as_str(), "hedge_line", "quantity"])?;

                    let new_quantity = if new_risk < max_risk {
                        (product_factor * pos_quantity) - opos_quantity
                    } else {
                        pos_quantity - opos_quantity
                    };

                    self.grid.set(
                        &[self.opos_side.as_str(), "hedge_line", "quantity"],
                        py_round(new_quantity, quantity_precision),
                    )?;
                    self.generate_recovery_line()?;

                    let recovery_line = self
                        .grid
                        .value(&[self.opos_side.as_str(), "recovery_line"])?;
                    post_hedge_order(client, &symbol, &recovery_line).await?;

                    self.generate_distances()?;
                    self.generate_break_even_points()?;
                    self.generate_take_profit_points()?;
                    self.generate_stop_loss_points()?;

                    for side in ["LONG", "SHORT"] {
                        let take_profit = self.grid.value(&[side, "take_profit_line"])?;
                        post_take_profit_order(client, &symbol, &take_profit).await?;
                        let stop_loss = self.grid.value(&[side, "stop_loss_line"])?;
                        post_stop_loss_order(client, &symbol, &stop_loss).await?;
                    }
                }

                self.grid.save()
            }

            ("TAKE_PROFIT_MARKET", true) => {
                info!(
                    "{symbol}_{} - RECOVERY_ZONE - TAKE_PROFIT - Price: {} | Quantity: {} ...FILLED",
                    self.pos_side, event.price, event.orig_qty
                );
                let pos_side = self.pos_side.clone();
                let opos_side = self.opos_side.clone();
                clean_order(client, &symbol, &pos_side, "GRID").await?;
                clean_order(client, &symbol, &opos_side, "HEDGE").await
            }

            ("STOP_MARKET", true) => {
                info!(
                    "{symbol}_{} - RECOVERY_ZONE - STOP_LOSS - Price: {} | Quantity: {} ...FILLED",
                    self.pos_side, event.price, event.orig_qty
                );
                let pos_side = self.pos_side.clone();
                let opos_side = self.opos_side.clone();
                clean_order(client, &symbol, &pos_side, "GRID").await?;
                clean_order(client, &symbol, &opos_side, "HEDGE").await
            }

            ("TRAILING_STOP_MARKET", _) => {
                info!(
                    "{symbol}_{} - TRAILING_STOP_MARKET - Price: {} | Quantity: {} ...FILLED",
                    self.pos_side, event.price, event.orig_qty
                );
                let pos_side = self.pos_side.clone();
                let opos_side = self.opos_side.clone();
                clean_order(client, &symbol, &pos_side, "GRID").await?;
                clean_order(client, &symbol, &opos_side, "HEDGE").await
            }

            _ => Ok(()),
        }
    }

    pub async fn update_current_position(&mut self, client: &BinanceClient) -> Result<()> {
        let symbol = self.grid.symbol.clone();
        debug!("{symbol} UPDATING CURRENT POSITION...");

        let positions = client.position_information(&symbol).await?;
        for position in &positions {
            if position.position_side == "LONG" || position.position_side == "SHORT" {
                let entry_price = position.entry_price.parse::<f64>().unwrap_or(0.0);
                let amount = position.position_amt.parse::<f64>().unwrap_or(0.0).abs();
                let tick_size = self.grid.f64(&["tick_size"])?;
                let side = position.position_side.as_str();

                self.grid.set(
                    &[side, "hedge_line", "position_side"],
                    Value::from(position.position_side.clone()),
                )?;
                self.grid.set(
                    &[side, "hedge_line", "price"],
                    round_to_tick(entry_price, tick_size),
                )?;
                self.grid.set(&[side, "hedge_line", "quantity"], amount)?;
            }
        }

        debug!(
            "{symbol} Positions updated: {} - {}",
            self.grid.value(&["LONG", "hedge_line"])?,
            self.grid.value(&["SHORT", "hedge_line"])?
        );
        Ok(())
    }

    pub fn generate_distances(&mut self) -> Result<()> {
        debug!("{} GENERATING DISTANCES...", self.grid.symbol);

        let long_price = self.grid.f64(&["LONG", "hedge_line", "price"])?;
        let short_price = self.grid.f64(&["SHORT", "hedge_line", "price"])?;
        let target_factor = self.grid.f64(&["risk", "target_factor"])?;

        let long_distance = get_distance(long_price, short_price);
        let short_distance = get_distance(short_price, long_price);

        self.grid
            .set(&["LONG", "hedge_line", "distance"], long_distance)?;
        self.grid
            .set(&["SHORT", "hedge_line", "distance"], short_distance)?;

        self.grid.set(
            &["LONG", "break_even_line", "win_distance"],
            py_round(long_distance * target_factor, 2),
        )?;
        self.grid.set(
            &["LONG", "break_even_line", "lost_distance"],
            py_round(short_distance * (target_factor + 1.0), 2),
        )?;

        self.grid.set(
            &["SHORT", "break_even_line", "win_distance"],
            py_round(short_distance * target_factor, 2),
        )?;
        // The Python source omitted the parentheses here
        // (`distance * target_factor + 1`); this uses the same formula as the
        // LONG branch so both sides are symmetric.
        self.grid.set(
            &["SHORT", "break_even_line", "lost_distance"],
            py_round(long_distance * (target_factor + 1.0), 2),
        )?;

        Ok(())
    }

    pub fn generate_break_even_points(&mut self) -> Result<()> {
        debug!("{} GENERATING BREAK EVEN POINTS...", self.grid.symbol);
        let tick_size = self.grid.f64(&["tick_size"])?;

        let long_price = self.grid.f64(&["LONG", "hedge_line", "price"])?;
        let long_win_distance = self.grid.f64(&["LONG", "break_even_line", "win_distance"])?;
        let long_quantity = self.grid.f64(&["LONG", "hedge_line", "quantity"])?;
        let short_quantity = self.grid.f64(&["SHORT", "hedge_line", "quantity"])?;
        let long_break_even = round_to_tick(
            (long_price * (1.0 + (long_win_distance / 100.0))).abs(),
            tick_size,
        );
        self.grid
            .set(&["LONG", "break_even_line", "price"], long_break_even)?;
        self.grid
            .set(&["LONG", "break_even_line", "win_quantity"], long_quantity)?;
        self.grid
            .set(&["LONG", "break_even_line", "lost_quantity"], short_quantity)?;
        self.grid.set(
            &["LONG", "break_even_line", "win_cost"],
            py_round(long_quantity * long_break_even, 2),
        )?;
        self.grid.set(
            &["LONG", "break_even_line", "lost_cost"],
            py_round(short_quantity * long_break_even, 2),
        )?;

        let short_price = self.grid.f64(&["SHORT", "hedge_line", "price"])?;
        let short_win_distance = self
            .grid
            .f64(&["SHORT", "break_even_line", "win_distance"])?;
        let short_break_even = round_to_tick(
            (short_price * (1.0 - (short_win_distance / 100.0))).abs(),
            tick_size,
        );
        self.grid
            .set(&["SHORT", "break_even_line", "price"], short_break_even)?;
        self.grid
            .set(&["SHORT", "break_even_line", "win_quantity"], short_quantity)?;
        self.grid
            .set(&["SHORT", "break_even_line", "lost_quantity"], long_quantity)?;
        self.grid.set(
            &["SHORT", "break_even_line", "win_cost"],
            py_round(short_quantity * short_break_even, 2),
        )?;
        self.grid.set(
            &["SHORT", "break_even_line", "lost_cost"],
            py_round(long_quantity * short_break_even, 2),
        )?;

        Ok(())
    }

    pub fn generate_take_profit_points(&mut self) -> Result<()> {
        debug!("{} GENERATING TAKE PROFIT POINTS...", self.grid.symbol);
        let tick_size = self.grid.f64(&["tick_size"])?;

        let long_break_even = self.grid.f64(&["LONG", "break_even_line", "price"])?;
        let long_distance = self
            .grid
            .f64(&["LONG", "take_profit_line", "distance"])?;
        self.grid.set(
            &["LONG", "take_profit_line", "price"],
            round_to_tick(long_break_even * (1.0 + (long_distance / 100.0)), tick_size),
        )?;

        let short_break_even = self.grid.f64(&["SHORT", "break_even_line", "price"])?;
        let short_distance = self
            .grid
            .f64(&["SHORT", "take_profit_line", "distance"])?;
        self.grid.set(
            &["SHORT", "take_profit_line", "price"],
            round_to_tick(short_break_even * (1.0 - (short_distance / 100.0)), tick_size),
        )?;

        Ok(())
    }

    pub fn generate_stop_loss_points(&mut self) -> Result<()> {
        debug!("{} GENERATING STOP LOSS POINTS...", self.grid.symbol);
        let long_take_profit = self.grid.f64(&["LONG", "take_profit_line", "price"])?;
        let short_take_profit = self.grid.f64(&["SHORT", "take_profit_line", "price"])?;

        self.grid
            .set(&["LONG", "stop_loss_line", "price"], short_take_profit)?;
        self.grid
            .set(&["SHORT", "stop_loss_line", "price"], long_take_profit)?;
        Ok(())
    }

    pub fn generate_recovery_line(&mut self) -> Result<()> {
        let opos_price = self
            .grid
            .f64(&[self.opos_side.as_str(), "hedge_line", "price"])?;
        let pos_price = self
            .grid
            .f64(&[self.pos_side.as_str(), "hedge_line", "price"])?;
        let opos_quantity = self
            .grid
            .f64(&[self.opos_side.as_str(), "hedge_line", "quantity"])?;
        let reduce_hedge = self.grid.f64(&["risk", "reduce_hedge"])?;
        let tick_size = self.grid.f64(&["tick_size"])?;

        let inside_distance = get_distance(opos_price, pos_price);
        let target_distance = (inside_distance / 100.0) * reduce_hedge;
        let target_price = if self.pos_side == "LONG" {
            opos_price * (1.0 + target_distance / 100.0)
        } else {
            opos_price * (1.0 - target_distance / 100.0)
        };

        self.grid.set(
            &[self.opos_side.as_str(), "recovery_line", "price"],
            round_to_tick(target_price, tick_size),
        )?;
        self.grid.set(
            &[self.opos_side.as_str(), "recovery_line", "quantity"],
            opos_quantity,
        )?;
        Ok(())
    }

    pub fn generate_trailing_stop(&mut self) -> Result<()> {
        let tick_size = self.grid.f64(&["tick_size"])?;
        let hedge_price = self
            .grid
            .f64(&[self.pos_side.as_str(), "hedge_line", "price"])?;
        let take_profit_price = self
            .grid
            .f64(&[self.pos_side.as_str(), "take_profit_line", "price"])?;
        let quantity = self
            .grid
            .f64(&[self.pos_side.as_str(), "hedge_line", "quantity"])?;

        let activation_price = round_to_tick((hedge_price + take_profit_price) / 2.0, tick_size);
        let callback_rate = get_distance(activation_price, hedge_price);
        let callback_rate = if callback_rate <= 10.0 {
            callback_rate
        } else {
            10.0
        };

        self.grid.set(
            &[self.pos_side.as_str(), "trailing_stop_line", "activation_price"],
            activation_price,
        )?;
        self.grid.set(
            &[self.pos_side.as_str(), "trailing_stop_line", "callback_rate"],
            callback_rate,
        )?;
        self.grid.set(
            &[self.pos_side.as_str(), "trailing_stop_line", "quantity"],
            quantity,
        )?;
        self.grid.set(
            &[self.pos_side.as_str(), "trailing_stop_line", "cost"],
            py_round(activation_price * quantity, 2),
        )?;
        Ok(())
    }

    pub fn generate_stop_loss_protection(&mut self) -> Result<()> {
        debug!(
            "{} GENERATING STOP LOSS PROTECTION POINT...",
            self.grid.symbol
        );
        let tick_size = self.grid.f64(&["tick_size"])?;
        let hedge_price = self
            .grid
            .f64(&[self.pos_side.as_str(), "hedge_line", "price"])?;
        let protection_distance = self
            .grid
            .f64(&[self.pos_side.as_str(), "stop_loss_line", "protection_distance"])?;

        let target_price = if self.pos_side == "LONG" {
            hedge_price * (1.0 + protection_distance / 100.0)
        } else {
            hedge_price * (1.0 - protection_distance / 100.0)
        };

        self.grid.set(
            &[self.pos_side.as_str(), "stop_loss_line", "price"],
            round_to_tick(target_price, tick_size),
        )?;
        Ok(())
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn zone() -> RecoveryZone {
        let data = json!({
            "strategy": "RECOVERY_ZONE",
            "symbol": "BTCUSDT",
            "input_side": "LONG",
            "price_precision": 1,
            "quantity_precision": 3,
            "tick_size": 0.1,
            "step_size": 0.001,
            "risk": {
                "wallet_balance_usdt": 1000.0,
                "min_risk": 1.0,
                "max_risk": 6.0,
                "target_factor": 2.0,
                "product_factor": 1.5,
                "reduce_hedge": 0.5,
                "hedge_distance": 0.1
            },
            "LONG": {
                "hedge_line": { "enabled": true, "side": "BUY", "type": "STOP_MARKET", "position_side": "LONG", "distance": 0.0, "price": 100.0, "quantity": 2.0, "cost": 0.0, "close_position": false },
                "recovery_line": { "enabled": true, "side": "BUY", "type": "STOP_MARKET", "position_side": "LONG", "price": 0.0, "quantity": 0.0 },
                "take_profit_line": { "enabled": true, "side": "SELL", "position_side": "LONG", "distance": 0.5, "price": 0.0 },
                "stop_loss_line": { "enabled": true, "side": "SELL", "position_side": "LONG", "distance": 0.5, "price": 0.0 },
                "break_even_line": { "win_distance": 0.0, "lost_distance": 0.0, "price": 0.0, "win_quantity": 0.0, "lost_quantity": 0.0, "win_cost": 0.0, "lost_cost": 0.0 },
                "trailing_stop_line": { "enabled": true, "side": "SELL", "position_side": "LONG", "activation_price": 0.0, "quantity": 0.0, "callback_rate": 0.0, "cost": 0.0 }
            },
            "SHORT": {
                "hedge_line": { "enabled": true, "side": "SELL", "type": "STOP_MARKET", "position_side": "SHORT", "distance": 0.0, "price": 101.0, "quantity": 2.0, "cost": 0.0, "close_position": false },
                "recovery_line": { "enabled": true, "side": "SELL", "type": "STOP_MARKET", "position_side": "SHORT", "price": 0.0, "quantity": 0.0 },
                "take_profit_line": { "enabled": true, "side": "BUY", "position_side": "SHORT", "distance": 0.5, "price": 0.0 },
                "stop_loss_line": { "enabled": true, "side": "BUY", "position_side": "SHORT", "distance": 0.5, "price": 0.0 },
                "break_even_line": { "win_distance": 0.0, "lost_distance": 0.0, "price": 0.0, "win_quantity": 0.0, "lost_quantity": 0.0, "win_cost": 0.0, "lost_cost": 0.0 },
                "trailing_stop_line": { "enabled": true, "side": "BUY", "position_side": "SHORT", "activation_price": 0.0, "quantity": 0.0, "callback_rate": 0.0, "cost": 0.0 }
            }
        });
        RecoveryZone {
            grid: Grid::from_value("BTCUSDT", data),
            pos_side: "LONG".into(),
            opos_side: "SHORT".into(),
        }
    }

    fn close(a: f64, b: f64) -> bool {
        (a - b).abs() < 1e-9
    }

    #[test]
    fn distances_are_symmetric_on_both_sides() {
        let mut zone = zone();
        zone.generate_distances().unwrap();
        assert!(close(
            zone.grid.f64(&["LONG", "break_even_line", "win_distance"]).unwrap(),
            2.0
        ));
        assert!(close(
            zone.grid.f64(&["LONG", "break_even_line", "lost_distance"]).unwrap(),
            2.97
        ));
        assert!(close(
            zone.grid.f64(&["SHORT", "break_even_line", "win_distance"]).unwrap(),
            1.98
        ));
        assert!(close(
            zone.grid.f64(&["SHORT", "break_even_line", "lost_distance"]).unwrap(),
            3.0
        ));
    }

    #[test]
    fn break_even_and_take_profit_points_follow_the_side() {
        let mut zone = zone();
        zone.generate_distances().unwrap();
        zone.generate_break_even_points().unwrap();
        zone.generate_take_profit_points().unwrap();
        zone.generate_stop_loss_points().unwrap();

        assert!(close(
            zone.grid.f64(&["LONG", "break_even_line", "price"]).unwrap(),
            102.0
        ));
        assert!(close(
            zone.grid.f64(&["SHORT", "break_even_line", "price"]).unwrap(),
            99.0
        ));
        assert_eq!(
            zone.grid.f64(&["LONG", "stop_loss_line", "price"]).unwrap(),
            zone.grid.f64(&["SHORT", "take_profit_line", "price"]).unwrap()
        );
        assert_eq!(
            zone.grid.f64(&["SHORT", "stop_loss_line", "price"]).unwrap(),
            zone.grid.f64(&["LONG", "take_profit_line", "price"]).unwrap()
        );
    }

    #[test]
    fn recovery_line_uses_reduce_hedge() {
        let mut zone = zone();
        zone.generate_recovery_line().unwrap();
        let price = zone
            .grid
            .f64(&["SHORT", "recovery_line", "price"])
            .unwrap();
        assert!((101.0..=102.0).contains(&price));
        assert_eq!(
            zone.grid
                .f64(&["SHORT", "recovery_line", "quantity"])
                .unwrap(),
            2.0
        );
    }

    #[test]
    fn trailing_stop_callback_is_capped_at_ten_percent() {
        let mut zone = zone();
        zone.generate_trailing_stop().unwrap();
        let callback = zone
            .grid
            .f64(&["LONG", "trailing_stop_line", "callback_rate"])
            .unwrap();
        assert!(callback <= 10.0);
        assert!(callback > 0.0);
    }
}
