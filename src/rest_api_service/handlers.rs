use crate::core::commands::{ApiResponse, AppState, CardiacInitStrategy, RestApiCommands};
use axum::{extract::State, Json};
use tokio::sync::oneshot;

pub async fn handle_start_strategy(
    State(state): State<std::sync::Arc<AppState>>,
    Json(payload): Json<CardiacInitStrategy>,
) -> Json<ApiResponse> {
    println!(
        "Received {} Order request for symbol: {}",
        payload.strategy, payload.symbol
    );

    let (tx, rx) = oneshot::channel();
    let cmd = RestApiCommands::CardiacEntryOrder {
        strategy: payload.strategy,
        symbol: payload.symbol,
        side: payload.side,
        price: payload.price,
        quantity: payload.quantity,
        config: payload.config,
        tx,
    };

    if let Err(e) = state.tx_rest_api_cmd.send(cmd).await {
        return Json(ApiResponse {
            status: "error".to_string(),
            message: format!("Failed to send command to core: {}", e),
        });
    }

    match rx.await {
        Ok(_) => Json(ApiResponse {
            status: "success".to_string(),
            message: "Order command processed".to_string(),
        }),
        Err(e) => Json(ApiResponse {
            status: "error".to_string(),
            message: format!("Failed to receive response from core: {}", e),
        }),
    }
}
