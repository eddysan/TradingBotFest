//! Persistent operations state.
//!
//! Every strategy keeps its live state in `ops/{SYMBOL}.json`, exactly like the
//! Python bot, so a running position can be handed over between versions. The
//! documents are dynamic (each strategy has a different shape), so the store
//! keeps `serde_json::Value` and exposes small typed accessors.

use crate::error::{AppError, Result};
use serde_json::Value;
use std::fs;
use std::path::{Path, PathBuf};

pub fn ops_dir() -> PathBuf {
    PathBuf::from("ops")
}

pub fn ops_path(symbol: &str) -> PathBuf {
    ops_dir().join(format!("{symbol}.json"))
}

/// Read a JSON document. Returns `Ok(None)` when the file does not exist,
/// matching `read_config_data` returning `None`.
pub fn read_json(path: impl AsRef<Path>) -> Result<Option<Value>> {
    let path = path.as_ref();
    if !path.exists() {
        return Ok(None);
    }
    let raw = fs::read_to_string(path)?;
    let value = serde_json::from_str(&raw)?;
    Ok(Some(value))
}

/// Read a JSON document that must exist, with a readable error otherwise.
pub fn read_json_required(path: impl AsRef<Path>) -> Result<Value> {
    let path = path.as_ref();
    read_json(path)?.ok_or_else(|| AppError::MissingConfig(path.display().to_string()))
}

/// Write JSON with 4-space indentation, creating the directory when needed.
pub fn write_json(directory: impl AsRef<Path>, file_name: &str, data: &Value) -> Result<()> {
    let directory = directory.as_ref();
    fs::create_dir_all(directory)?;
    let path = directory.join(file_name);
    let mut out = Vec::new();
    let formatter = serde_json::ser::PrettyFormatter::with_indent(b"    ");
    let mut serializer = serde_json::Serializer::with_formatter(&mut out, formatter);
    serde::Serialize::serialize(data, &mut serializer)?;
    out.push(b'\n');
    fs::write(path, out)?;
    Ok(())
}

/// The live state of one symbol, backed by `ops/{symbol}.json`.
#[derive(Debug, Clone)]
pub struct Grid {
    pub symbol: String,
    pub data: Value,
}

impl Grid {
    pub fn load(symbol: &str) -> Result<Self> {
        let path = ops_path(symbol);
        let data = read_json_required(&path)?;
        Ok(Self {
            symbol: symbol.to_string(),
            data,
        })
    }

    pub fn from_value(symbol: &str, data: Value) -> Self {
        Self {
            symbol: symbol.to_string(),
            data,
        }
    }

    pub fn save(&self) -> Result<()> {
        write_json(ops_dir(), &format!("{}.json", self.symbol), &self.data)
    }

    /// Borrow the value at a nested path.
    pub fn at(&self, path: &[&str]) -> Option<&Value> {
        let mut current = &self.data;
        for key in path {
            current = current.get(*key)?;
        }
        Some(current)
    }

    /// Clone the value at a nested path, erroring when it is missing.
    pub fn value(&self, path: &[&str]) -> Result<Value> {
        self.at(path).cloned().ok_or_else(|| AppError::MissingKey {
            path: display_path(path),
            context: self.symbol.clone(),
        })
    }

    fn at_mut(&mut self, path: &[&str]) -> Result<&mut Value> {
        let mut current = &mut self.data;
        for key in path {
            current = current.get_mut(*key).ok_or_else(|| AppError::MissingKey {
                path: display_path(path),
                context: self.symbol.clone(),
            })?;
        }
        Ok(current)
    }

    pub fn f64(&self, path: &[&str]) -> Result<f64> {
        self.f64_opt(path)?.ok_or_else(|| AppError::MissingKey {
            path: display_path(path),
            context: self.symbol.clone(),
        })
    }

    pub fn f64_opt(&self, path: &[&str]) -> Result<Option<f64>> {
        match self.at(path) {
            None | Some(Value::Null) => Ok(None),
            Some(Value::Number(number)) => number
                .as_f64()
                .map(Some)
                .ok_or_else(|| invalid(path, "number is not representable as f64")),
            Some(Value::String(text)) => text
                .parse::<f64>()
                .map(Some)
                .map_err(|_| invalid(path, &format!("not a number: {text:?}"))),
            Some(other) => Err(invalid(path, &format!("expected number, found {other}"))),
        }
    }

    pub fn f64_or(&self, path: &[&str], default: f64) -> Result<f64> {
        Ok(self.f64_opt(path)?.unwrap_or(default))
    }

    pub fn i32(&self, path: &[&str]) -> Result<i32> {
        let value = self.f64(path)?;
        Ok(value as i32)
    }

    pub fn string(&self, path: &[&str]) -> Result<String> {
        match self.at(path) {
            Some(Value::String(text)) => Ok(text.clone()),
            Some(other) => Err(invalid(path, &format!("expected string, found {other}"))),
            None => Err(AppError::MissingKey {
                path: display_path(path),
                context: self.symbol.clone(),
            }),
        }
    }

    pub fn string_opt(&self, path: &[&str]) -> Option<String> {
        self.at(path).and_then(Value::as_str).map(str::to_string)
    }

    pub fn bool(&self, path: &[&str]) -> Result<bool> {
        self.at(path)
            .and_then(Value::as_bool)
            .ok_or_else(|| invalid(path, "expected boolean"))
    }

    pub fn bool_or(&self, path: &[&str], default: bool) -> bool {
        self.at(path).and_then(Value::as_bool).unwrap_or(default)
    }

    pub fn array_len(&self, path: &[&str]) -> usize {
        self.at(path)
            .and_then(Value::as_array)
            .map_or(0, Vec::len)
    }

    pub fn set(&mut self, path: &[&str], value: impl Into<Value>) -> Result<()> {
        let target = self.at_mut(path)?;
        *target = value.into();
        Ok(())
    }

    pub fn set_json(&mut self, path: &[&str], value: Value) -> Result<()> {
        self.set(path, value)
    }

    pub fn push(&mut self, path: &[&str], value: Value) -> Result<()> {
        match self.at_mut(path)? {
            Value::Array(items) => {
                items.push(value);
                Ok(())
            }
            other => Err(invalid(path, &format!("expected array, found {other}"))),
        }
    }

    pub fn clear_array(&mut self, path: &[&str]) -> Result<()> {
        match self.at_mut(path)? {
            Value::Array(items) => {
                items.clear();
                Ok(())
            }
            other => Err(invalid(path, &format!("expected array, found {other}"))),
        }
    }

    /// Merge top-level keys from `source` into this document.
    pub fn set_top_level(&mut self, key: &str, value: Value) -> Result<()> {
        match &mut self.data {
            Value::Object(map) => {
                map.insert(key.to_string(), value);
                Ok(())
            }
            _ => Err(AppError::msg("state document is not a JSON object")),
        }
    }
}

fn display_path(path: &[&str]) -> String {
    path.join(".")
}

fn invalid(path: &[&str], message: &str) -> AppError {
    AppError::InvalidValue {
        path: display_path(path),
        message: message.to_string(),
    }
}

/// Strategy name stored in `ops/{symbol}.json`, mirroring `get_strategy`.
pub fn get_strategy(symbol: &str) -> Option<String> {
    read_json(ops_path(symbol))
        .ok()
        .flatten()
        .and_then(|value| value.get("strategy").and_then(Value::as_str).map(str::to_string))
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    fn sample() -> Grid {
        Grid::from_value("BTCUSDT", json!({ "LONG": { "price": 100.0, "enabled": true, "lines": [] } }))
    }

    #[test]
    fn reads_nested_values() {
        let grid = sample();
        assert_eq!(grid.f64(&["LONG", "price"]).unwrap(), 100.0);
        assert!(grid.bool(&["LONG", "enabled"]).unwrap());
    }

    #[test]
    fn writes_nested_values() {
        let mut grid = sample();
        grid.set(&["LONG", "price"], 101.5).unwrap();
        grid.push(&["LONG", "lines"], json!({ "price": 1.0 })).unwrap();
        assert_eq!(grid.f64(&["LONG", "price"]).unwrap(), 101.5);
        assert_eq!(grid.array_len(&["LONG", "lines"]), 1);
    }

    #[test]
    fn missing_keys_are_errors() {
        let grid = sample();
        assert!(grid.f64(&["LONG", "nope"]).is_err());
        assert!(grid.f64_opt(&["LONG", "nope"]).unwrap().is_none());
    }
}
