//! Trading Bot Fest — Rust port of the original Python trading bot.
//!
//! The exchange-facing behaviour (endpoints, order shapes, rounding and the
//! `ops/{SYMBOL}.json` state files) is kept compatible with the Python
//! implementation so that open positions survive the migration.

pub mod config;
pub mod error;
pub mod exchange;
pub mod logging;
pub mod orders;
pub mod store;
pub mod strategies;
pub mod util;

pub use error::{AppError, Result};
