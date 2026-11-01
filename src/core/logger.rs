use serde_json::Value as JsonValue;
use std::collections::HashMap;
use tracing::{debug, error, info, warn};

use crate::db::{insert_log, DbPool};

#[derive(Debug, Clone, PartialEq, Eq, Hash)]
pub enum Event {
    Boot,
    Shutdown,
    ConfigLoaded,
    InputStarted,
    InputSaved,
    PositionFound,
    PositionCreated,
    PositionUpdated,
    PositionClosed,
    OrderPlaced,
    OrderFilled,
    OrderCanceled,
    OrderFailed,
    StopLossTriggered,
    TakeProfitHit,
    UnloadTriggered,
    ApiError,
    ApiRateLimit,
    ConnectionError,
    ConnectionSuccess,
}

impl Event {
    pub fn as_str(&self) -> &'static str {
        match self {
            Event::Boot => "BOOT",
            Event::Shutdown => "SHUTDOWN",
            Event::ConfigLoaded => "CONFIG_LOADED",
            Event::InputStarted => "INPUT_STARTED",
            Event::InputSaved => "INPUT_SAVED",
            Event::PositionFound => "POSITION_FOUND",
            Event::PositionCreated => "POSITION_CREATED",
            Event::PositionUpdated => "POSITION_UPDATED",
            Event::PositionClosed => "POSITION_CLOSED",
            Event::OrderPlaced => "ORDER_PLACED",
            Event::OrderFilled => "ORDER_FILLED",
            Event::OrderCanceled => "ORDER_CANCELED",
            Event::OrderFailed => "ORDER_FAILED",
            Event::StopLossTriggered => "STOP_LOSS_TRIGGERED",
            Event::TakeProfitHit => "TAKE_PROFIT_HIT",
            Event::UnloadTriggered => "UNLOAD_TRIGGERED",
            Event::ApiError => "API_ERROR",
            Event::ApiRateLimit => "API_RATE_LIMIT",
            Event::ConnectionError => "CONNECTION_ERROR",
            Event::ConnectionSuccess => "CONNECTION_SUCCESS",
        }
    }
}

impl std::fmt::Display for Event {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(f, "{}", self.as_str())
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Level {
    Debug,
    Info,
    Warning,
    Error,
}

impl Level {
    pub fn as_str(&self) -> &'static str {
        match self {
            Level::Debug => "DEBUG",
            Level::Info => "INFO",
            Level::Warning => "WARNING",
            Level::Error => "ERROR",
        }
    }
}

impl std::fmt::Display for Level {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(f, "{}", self.as_str())
    }
}

pub struct LogEntry<'a> {
    pub event: &'a Event,
    pub level: Level,
    pub symbol: Option<&'a str>,
    pub strategy: Option<&'a str>,
    pub message: Option<&'a str>,
    pub payload: Option<HashMap<String, JsonValue>>,
}

impl<'a> LogEntry<'a> {
    pub fn new(event: &'a Event) -> Self {
        Self {
            event,
            level: Level::Info,
            symbol: None,
            strategy: None,
            message: None,
            payload: None,
        }
    }

    pub fn level(mut self, level: Level) -> Self {
        self.level = level;
        self
    }
    pub fn symbol(mut self, s: &'a str) -> Self {
        self.symbol = Some(s);
        self
    }
    pub fn strategy(mut self, s: &'a str) -> Self {
        self.strategy = Some(s);
        self
    }
    pub fn message(mut self, m: &'a str) -> Self {
        self.message = Some(m);
        self
    }
    pub fn payload(mut self, p: HashMap<String, JsonValue>) -> Self {
        self.payload = Some(p);
        self
    }
}

pub async fn log(entry: LogEntry<'_>, pool: &DbPool) {
    let msg = entry.message.unwrap_or("");
    let tag = entry.event.as_str();

    match entry.level {
        Level::Debug => debug!("[{tag}] {msg}"),
        Level::Info => info!("[{tag}] {msg}"),
        Level::Warning => warn!("[{tag}] {msg}"),
        Level::Error => error!("[{tag}] {msg}"),
    }

    let payload_json: Option<String> = entry
        .payload
        .as_ref()
        .and_then(|p| serde_json::to_string(p).ok());

    if let Err(e) = insert_log(
        pool,
        entry.level.as_str(),
        entry.event.as_str(),
        entry.symbol,
        entry.strategy,
        entry.message,
        payload_json.as_deref(),
    )
    .await
    {
        error!("Failed to write log to DB: {e}");
    }
}
