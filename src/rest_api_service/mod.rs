use axum::{routing::post, Router};
use std::net::SocketAddr;
use std::sync::Arc;
use tokio::sync::mpsc;

mod handlers;

use crate::core::commands::{AppState, RestApiCommands};

/// wait for API request from trading_cli who send commands to trading engine
pub async fn run(tx_rest_api_cmd: mpsc::Sender<RestApiCommands>) -> anyhow::Result<()> {
    let state = Arc::new(AppState { tx_rest_api_cmd });

    // listen cardiac data in order to start strategy
    let app = Router::new()
        .route(
            "/cardiac/start_strategy",
            post(handlers::handle_start_strategy),
        )
        .with_state(state);

    let addr = SocketAddr::from(([127, 0, 0, 1], 3000));
    println!("REST API Service listening on {}", addr);

    let listener = tokio::net::TcpListener::bind(addr).await?;
    axum::serve(listener, app).await?;

    Ok(())
}
