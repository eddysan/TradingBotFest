use serde::{Deserialize, Serialize};

#[derive(Debug, Deserialize, Serialize)]
pub struct CardiacConfig {
    pub take_profit: TakeProfit,
    pub stop_loss: StopLoss,
    pub unload: Unload,
    pub buy_back: BuyBack,
}

#[derive(Debug, Deserialize, Serialize)]
pub struct TakeProfit {
    pub enabled: bool,
    pub distance: f64,
}

#[derive(Debug, Deserialize, Serialize)]
pub struct StopLoss {
    pub enabled: bool,
    pub risk: f64,
}

#[derive(Debug, Deserialize, Serialize)]
pub struct Unload {
    pub enabled: bool,
    pub distance: f64,
    pub lost_active: f64,
}

#[derive(Debug, Deserialize, Serialize)]
pub struct BuyBack {
    pub enabled: bool,
    pub distance: f64,
}

impl CardiacConfig {
    pub fn from_file(path: &str) -> anyhow::Result<Self> {
        let content = std::fs::read_to_string(path)?;
        let config: Self = toml::from_str(&content)?;
        Ok(config)
    }
}
