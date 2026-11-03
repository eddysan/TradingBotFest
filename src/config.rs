use crate::error::{AppError, Result};
use std::env;
use std::path::Path;

/// Binance credentials selected from the environment.
#[derive(Debug, Clone)]
pub struct Credentials {
    pub testnet: bool,
    pub api_key: String,
    pub api_secret: String,
}

fn env_flag(name: &str) -> Option<bool> {
    env::var(name).ok().map(|value| {
        matches!(
            value.trim().to_ascii_lowercase().as_str(),
            "true" | "1" | "yes"
        )
    })
}

fn required(name: &str) -> Result<String> {
    env::var(name)
        .ok()
        .filter(|value| !value.trim().is_empty())
        .ok_or_else(|| AppError::MissingEnv(name.to_string()))
}

/// Load `config/.credentials.env` (falling back to `.env`) and pick the
/// testnet or production key pair. `TESTNET` is the variable the Python bot
/// used; `USE_TESTNET` is accepted as an alias.
pub fn load_credentials() -> Result<Credentials> {
    for path in [".credentials.env", ".env"] {
        if Path::new(path).exists() {
            let _ = dotenvy::from_path(path);
        }
    }

    let testnet = env_flag("TESTNET")
        .or_else(|| env_flag("USE_TESTNET"))
        .unwrap_or(false);

    let (key_name, secret_name) = if testnet {
        ("BINANCE_TEST_API_KEY", "BINANCE_TEST_API_SECRET")
    } else {
        ("BINANCE_PROD_API_KEY", "BINANCE_PROD_API_SECRET")
    };

    Ok(Credentials {
        testnet,
        api_key: required(key_name)?,
        api_secret: required(secret_name)?,
    })
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::sync::Mutex;

    // Environment variables are process-global; serialise tests that touch them.
    static ENV_LOCK: Mutex<()> = Mutex::new(());

    #[test]
    fn env_flag_accepts_common_true_spellings() {
        let _guard = ENV_LOCK.lock().unwrap();
        env::set_var("TBF_TEST_FLAG", "true");
        assert_eq!(env_flag("TBF_TEST_FLAG"), Some(true));
        env::set_var("TBF_TEST_FLAG", "1");
        assert_eq!(env_flag("TBF_TEST_FLAG"), Some(true));
        env::set_var("TBF_TEST_FLAG", "false");
        assert_eq!(env_flag("TBF_TEST_FLAG"), Some(false));
        env::remove_var("TBF_TEST_FLAG");
    }
}
