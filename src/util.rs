use crate::error::{AppError, Result};
use std::io::Write;

/// Python's `round()` uses banker's rounding (ties to even). Rust's
/// `f64::round()` rounds half away from zero, so use `round_ties_even` to stay
/// close to the original implementation.
pub fn py_round(value: f64, digits: i32) -> f64 {
    if !value.is_finite() {
        return value;
    }
    if digits == 0 {
        return value.round_ties_even();
    }
    let factor = 10f64.powi(digits);
    (value * factor).round_ties_even() / factor
}

/// `int(abs(math.log10(tick_size)))` from the Python code: the number of
/// decimals accepted for a symbol whose price moves in `tick_size` steps.
pub fn tick_digits(tick_size: f64) -> i32 {
    if !tick_size.is_finite() || tick_size <= 0.0 {
        return 0;
    }
    tick_size.abs().log10().abs() as i32
}

/// Round a price to the symbol's tick size. Mirrors `round_to_tick`.
pub fn round_to_tick(price: f64, tick_size: f64) -> f64 {
    py_round(price, tick_digits(tick_size))
}

/// Percentage distance between two prices. Mirrors `get_distance`.
pub fn get_distance(first_point: f64, second_point: f64) -> f64 {
    if first_point < second_point {
        py_round(
            ((second_point - first_point) / first_point) * 100.0,
            2,
        )
    } else {
        py_round(
            ((first_point - second_point) / first_point) * 100.0,
            2,
        )
    }
}

/// Format a number the way Binance expects it: no trailing `.0`, no exponent
/// for the ranges used by futures prices and quantities.
pub fn fmt_num(value: f64) -> String {
    format!("{value}")
}

/// Strip the quote asset from a symbol, e.g. `BTCUSDT` -> `BTC`.
pub fn base_asset(symbol: &str) -> &str {
    symbol.strip_suffix("USDT").unwrap_or(symbol)
}

fn read_line(label: &str) -> Result<String> {
    print!("{label}");
    std::io::stdout().flush()?;
    let mut line = String::new();
    std::io::stdin().read_line(&mut line)?;
    Ok(line.trim().to_string())
}

/// Prompt for a required string value.
pub fn prompt(label: &str) -> Result<String> {
    read_line(label)
}

/// Prompt for a string with a default when the answer is blank.
pub fn prompt_or(label: &str, default: &str) -> Result<String> {
    let answer = read_line(label)?;
    if answer.is_empty() {
        Ok(default.to_string())
    } else {
        Ok(answer)
    }
}

fn parse_f64(label: &str, raw: &str) -> Result<f64> {
    raw.parse::<f64>()
        .map_err(|_| AppError::msg(format!("{label} is not a number: {raw:?}")))
}

/// Prompt for a required number.
pub fn prompt_f64(label: &str) -> Result<f64> {
    let raw = read_line(label)?;
    parse_f64(label, &raw)
}

/// Prompt for a number with a default when the answer is blank.
pub fn prompt_f64_or(label: &str, default: f64) -> Result<f64> {
    let raw = read_line(label)?;
    if raw.is_empty() {
        Ok(default)
    } else {
        parse_f64(label, &raw)
    }
}

/// Prompt for an integer with a default when the answer is blank.
pub fn prompt_i32_or(label: &str, default: i32) -> Result<i32> {
    let raw = read_line(label)?;
    if raw.is_empty() {
        Ok(default)
    } else {
        raw.parse::<i32>()
            .map_err(|_| AppError::msg(format!("{label} is not an integer: {raw:?}")))
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn distances_match_the_python_direction_rules() {
        assert_eq!(get_distance(100.0, 101.0), 1.0);
        assert_eq!(get_distance(101.0, 100.0), 0.99);
        assert_eq!(get_distance(100.0, 100.0), 0.0);
    }

    #[test]
    fn tick_rounding_uses_tick_decimals() {
        assert_eq!(tick_digits(0.1), 1);
        assert_eq!(tick_digits(0.001), 3);
        assert_eq!(tick_digits(1.0), 0);
        assert_eq!(round_to_tick(99.2537, 0.1), 99.3);
    }

    #[test]
    fn py_round_ties_to_even() {
        assert_eq!(py_round(2.5, 0), 2.0);
        assert_eq!(py_round(3.5, 0), 4.0);
        assert_eq!(py_round(-2.5, 0), -2.0);
    }

    #[test]
    fn base_asset_strips_usdt() {
        assert_eq!(base_asset("BTCUSDT"), "BTC");
        assert_eq!(base_asset("ETHUSDT"), "ETH");
    }
}
