pub struct CardiacState {
    pub is_in_position: bool,
    pub entry_price: f64,
    pub last_rsi: f64,
    pub volume_24h: f64,
}

impl CardiacState {
    pub fn new() -> Self {
        Self {
            is_in_position: false,
            entry_price: 0.0,
            last_rsi: 0.0,
            volume_24h: 0.0,
        }
    }
}
