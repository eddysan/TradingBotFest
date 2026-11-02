use thiserror::Error;

#[derive(Debug, Error)]
pub enum AppError {
    #[error("missing environment variable {0}")]
    MissingEnv(String),

    #[error("missing configuration file {0}")]
    MissingConfig(String),

    #[error("missing key {path} in {context}")]
    MissingKey { path: String, context: String },

    #[error("invalid value at {path}: {message}")]
    InvalidValue { path: String, message: String },

    #[error("symbol {0} not found in exchange info")]
    UnknownSymbol(String),

    #[error("exchange error {code}: {msg}")]
    Api { code: i64, msg: String },

    #[error("websocket error: {0}")]
    Websocket(#[from] tokio_tungstenite::tungstenite::Error),

    #[error("http error: {0}")]
    Http(#[from] reqwest::Error),

    #[error("io error: {0}")]
    Io(#[from] std::io::Error),

    #[error("json error: {0}")]
    Json(#[from] serde_json::Error),

    #[error("{0}")]
    Msg(String),
}

impl AppError {
    pub fn msg(message: impl Into<String>) -> Self {
        Self::Msg(message.into())
    }

    /// Binance "order would immediately trigger" / "unknown order" style errors
    /// are expected during normal operation and handled by the caller.
    pub fn api_code(&self) -> Option<i64> {
        match self {
            Self::Api { code, .. } => Some(*code),
            _ => None,
        }
    }
}

pub type Result<T> = std::result::Result<T, AppError>;
