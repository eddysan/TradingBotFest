use axum::{
    extract::State,
    routing::post,
    Json, Router,
};
use std::net::SocketAddr;
use tokio::sync::mpsc;
use crate::core::commands::StrategyCommand;

#[derive(Clone)]
pub struct ApiState {
    pub tx_strat_cmds: mpsc::Sender<StrategyCommand>,
}

pub async fn run(tx_strat_cmds: mpsc::Sender<StrategyCommand>) -> anyhow::Result<()> {
    let state = ApiState { tx_strat_cmds };

    let app = Router::new()
        .route("/strategy", post(handle_strategy_command))
        .with_state(state);

    let addr = SocketAddr::from(([127, 0, 0, 1], 3000));
    println!("API Service listening on http://{}", addr);
    
    let listener = tokio::net::TcpListener::bind(addr).await?;
    axum::serve(listener, app).await?;

    Ok(())
}

async fn handle_strategy_command(
    State(state): State<ApiState>,
    Json(cmd): Json<StrategyCommand>,
) -> Json<serde_json::Value> {
    println!("API: Received strategy command: {:?}", cmd);
    
    match state.tx_strat_cmds.send(cmd).await {
        Ok(_) => {
            Json(serde_json::json!({ "status": "success", "message": "Command routed to Dispatcher" }))
        }
        Err(e) => {
            Json(serde_json::json!({ "status": "error", "message": format!("Internal channel error: {}", e) }))
        }
    }
}
