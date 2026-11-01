pub fn check_entry_condition(current_price: f64, rsi: f64) -> bool {
    // Ejemplo de lógica "Cardiac"
    current_price < 60000.0 && rsi < 30.0
}