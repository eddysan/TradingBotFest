use crate::error::{AppError, Result};
use crate::exchange::models::SymbolInfo;
use crate::util::{py_round, tick_digits};

/// The exchange filters a symbol imposes on price and quantity.
#[derive(Debug, Clone)]
pub struct SymbolFilters {
    pub price_precision: i32,
    pub quantity_precision: i32,
    pub tick_size: f64,
    pub step_size: f64,
    pub min_qty: f64,
    pub max_qty: f64,
    pub min_notional: f64,
}

impl SymbolFilters {
    pub fn from_symbol(info: &SymbolInfo) -> Result<Self> {
        let mut filters = Self {
            price_precision: info.price_precision,
            quantity_precision: info.quantity_precision,
            tick_size: 0.0,
            step_size: 0.0,
            min_qty: 0.0,
            max_qty: f64::MAX,
            min_notional: 0.0,
        };

        for filter in &info.filters {
            let number = |value: &Option<String>| -> Result<Option<f64>> {
                match value {
                    None => Ok(None),
                    Some(text) => text.parse::<f64>().map(Some).map_err(|_| {
                        AppError::msg(format!(
                            "invalid {} value {:?} for {}",
                            filter.filter_type, text, info.symbol
                        ))
                    }),
                }
            };

            match filter.filter_type.as_str() {
                "PRICE_FILTER" => {
                    if let Some(value) = number(&filter.tick_size)? {
                        filters.tick_size = value;
                    }
                }
                "LOT_SIZE" => {
                    if let Some(value) = number(&filter.step_size)? {
                        filters.step_size = value;
                    }
                    if let Some(value) = number(&filter.min_qty)? {
                        filters.min_qty = value;
                    }
                    if let Some(value) = number(&filter.max_qty)? {
                        filters.max_qty = value;
                    }
                }
                "MIN_NOTIONAL" => {
                    if let Some(value) = number(&filter.notional)? {
                        filters.min_notional = value;
                    } else if let Some(value) = number(&filter.min_notional)? {
                        filters.min_notional = value;
                    }
                }
                _ => {}
            }
        }

        Ok(filters)
    }

    /// Round a price to the symbol's tick size.
    pub fn round_price(&self, price: f64) -> f64 {
        crate::util::round_to_tick(price, self.tick_size)
    }

    /// Round a quantity to the symbol's quantity precision. This is what the
    /// Python bot did; it assumes the step size matches the precision.
    pub fn round_quantity(&self, quantity: f64) -> f64 {
        py_round(quantity, self.quantity_precision)
    }

    /// Round a quantity down to a multiple of `step_size`, for callers that
    /// want a guaranteed-valid exchange quantity.
    pub fn floor_quantity(&self, quantity: f64) -> f64 {
        if self.step_size <= 0.0 {
            return self.round_quantity(quantity);
        }
        let steps = (quantity / self.step_size).floor();
        py_round(steps * self.step_size, self.quantity_precision)
    }

    /// Whether `quantity` at `price` satisfies the exchange minimum notional.
    pub fn meets_min_notional(&self, price: f64, quantity: f64) -> bool {
        self.min_notional <= 0.0 || price * quantity >= self.min_notional
    }

    pub fn tick_digits(&self) -> i32 {
        tick_digits(self.tick_size)
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::exchange::models::SymbolFilter;

    fn info() -> SymbolInfo {
        SymbolInfo {
            symbol: "BTCUSDT".into(),
            price_precision: 1,
            quantity_precision: 3,
            filters: vec![
                SymbolFilter {
                    filter_type: "PRICE_FILTER".into(),
                    tick_size: Some("0.100".into()),
                    ..Default::default()
                },
                SymbolFilter {
                    filter_type: "LOT_SIZE".into(),
                    step_size: Some("0.001".into()),
                    min_qty: Some("0.001".into()),
                    max_qty: Some("1000".into()),
                    ..Default::default()
                },
                SymbolFilter {
                    filter_type: "MIN_NOTIONAL".into(),
                    notional: Some("5".into()),
                    ..Default::default()
                },
            ],
        }
    }

    #[test]
    fn parses_filters() {
        let filters = SymbolFilters::from_symbol(&info()).unwrap();
        assert_eq!(filters.tick_size, 0.1);
        assert_eq!(filters.step_size, 0.001);
        assert_eq!(filters.min_qty, 0.001);
        assert_eq!(filters.min_notional, 5.0);
    }

    #[test]
    fn rounds_to_tick_and_step() {
        let filters = SymbolFilters::from_symbol(&info()).unwrap();
        assert_eq!(filters.round_price(99.2537), 99.3);
        assert_eq!(filters.floor_quantity(1.23456), 1.234);
        assert!(filters.meets_min_notional(100.0, 0.05));
        assert!(!filters.meets_min_notional(100.0, 0.01));
    }
}
