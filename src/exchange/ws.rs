//! Binance user-data WebSocket — Rust port of `wsbin.py`.
//!
//! Creates a listen key, keeps it alive every 30 minutes, dispatches
//! `ORDER_TRADE_UPDATE` events to the strategy that owns the symbol, serialises
//! events per symbol and reconnects with exponential backoff.

use crate::error::Result;
use crate::exchange::models::UserDataEvent;
use crate::exchange::BinanceClient;
use crate::strategies;
use futures_util::{SinkExt, StreamExt};
use std::collections::HashMap;
use std::sync::{Arc, Mutex as StdMutex};
use std::time::Duration;
use tokio::sync::{watch, Mutex, Semaphore};
use tokio::time::{interval, MissedTickBehavior};
use tokio_tungstenite::tungstenite::Message;
use tracing::{debug, error, info, warn};

const MAX_CONCURRENT_MESSAGES: usize = 10;
const KEEPALIVE_SECS: u64 = 30 * 60;
const PING_SECS: u64 = 120;
const INITIAL_RETRY_SECS: u64 = 5;
const MAX_RETRY_SECS: u64 = 120;

/// One async mutex per symbol, so fills for the same symbol are applied in
/// order while different symbols proceed independently.
#[derive(Clone, Default)]
pub struct SymbolLocks {
    inner: Arc<StdMutex<HashMap<String, Arc<Mutex<()>>>>>,
}

impl SymbolLocks {
    pub fn lock_for(&self, symbol: &str) -> Arc<Mutex<()>> {
        let mut map = self
            .inner
            .lock()
            .unwrap_or_else(|poisoned| poisoned.into_inner());
        map.entry(symbol.to_string())
            .or_insert_with(|| Arc::new(Mutex::new(())))
            .clone()
    }
}

/// Run the stream until Ctrl-C, reconnecting on every failure.
pub async fn run(client: Arc<BinanceClient>) -> Result<()> {
    let (stop_tx, stop_rx) = watch::channel(false);

    let ctrl_c = tokio::spawn(async move {
        if tokio::signal::ctrl_c().await.is_ok() {
            info!("Deteniendo bot...");
            let _ = stop_tx.send(true);
        }
    });

    let locks = SymbolLocks::default();
    let semaphore = Arc::new(Semaphore::new(MAX_CONCURRENT_MESSAGES));
    let mut retry_delay = INITIAL_RETRY_SECS;

    loop {
        if *stop_rx.borrow() {
            break;
        }

        match run_once(&client, &locks, &semaphore, stop_rx.clone()).await {
            Ok(()) => {}
            Err(error) => error!("Error en stream: {error}"),
        }

        if *stop_rx.borrow() {
            break;
        }

        warn!("WebSocket desconectado. Reintentando en {retry_delay}s...");

        tokio::select! {
            _ = tokio::time::sleep(Duration::from_secs(retry_delay)) => {}
            _ = wait_for_stop(stop_rx.clone()) => break,
        }

        retry_delay = (retry_delay * 2).min(MAX_RETRY_SECS);
    }

    ctrl_c.abort();
    Ok(())
}

async fn wait_for_stop(mut stop: watch::Receiver<bool>) {
    if *stop.borrow() {
        return;
    }
    let _ = stop.changed().await;
}

async fn run_once(
    client: &Arc<BinanceClient>,
    locks: &SymbolLocks,
    semaphore: &Arc<Semaphore>,
    stop: watch::Receiver<bool>,
) -> Result<()> {
    let listen_key = client.listen_key().await?;
    let url = client.ws_url(&listen_key);

    if client.testnet() {
        info!("TESTNET websocket CONNECTED!");
    } else {
        info!("PRODUCTION websocket CONNECTED!");
    }

    let (socket, _) = tokio_tungstenite::connect_async(url).await?;
    let (mut write, mut read) = socket.split();

    let keepalive = {
        let client = client.clone();
        let key = listen_key.clone();
        let mut stop = stop.clone();
        tokio::spawn(async move {
            let mut ticker = interval(Duration::from_secs(KEEPALIVE_SECS));
            ticker.set_missed_tick_behavior(MissedTickBehavior::Delay);
            ticker.tick().await; // consume the immediate tick
            loop {
                tokio::select! {
                    _ = ticker.tick() => {
                        match client.keepalive_listen_key(&key).await {
                            Ok(()) => info!("Listen key renovado correctamente"),
                            Err(error) => error!("Error renovando listen key: {error}"),
                        }
                    }
                    _ = stop.changed() => break,
                }
            }
        })
    };

    let mut ping = interval(Duration::from_secs(PING_SECS));
    ping.set_missed_tick_behavior(MissedTickBehavior::Delay);
    ping.tick().await; // consume the immediate tick

    let mut stopped = false;

    loop {
        tokio::select! {
            _ = wait_for_stop(stop.clone()) => {
                stopped = true;
                break;
            }
            _ = ping.tick() => {
                if let Err(error) = write.send(Message::Ping(Vec::new().into())).await {
                    warn!("WebSocket ping failed: {error}");
                    break;
                }
            }
            message = read.next() => {
                match message {
                    Some(Ok(Message::Text(text))) => {
                        if !handle_text(client, locks, semaphore, &text) {
                            break;
                        }
                    }
                    Some(Ok(Message::Ping(payload))) => {
                        let _ = write.send(Message::Pong(payload)).await;
                    }
                    Some(Ok(Message::Pong(_))) => {}
                    Some(Ok(Message::Close(frame))) => {
                        warn!("WebSocket cerrado: {frame:?}. Reconectando...");
                        break;
                    }
                    Some(Ok(_)) => {}
                    Some(Err(error)) => {
                        warn!("WebSocket error: {error}");
                        break;
                    }
                    None => break,
                }
            }
        }
    }

    keepalive.abort();

    if let Err(error) = client.close_listen_key(&listen_key).await {
        debug!("Could not close listen key: {error}");
    } else if stopped {
        info!("Listen key cerrado correctamente");
    }

    if stopped {
        Ok(())
    } else {
        Err(crate::error::AppError::msg("websocket closed"))
    }
}

/// Returns `false` when the listen key expired and the stream must reconnect.
fn handle_text(
    client: &Arc<BinanceClient>,
    locks: &SymbolLocks,
    semaphore: &Arc<Semaphore>,
    text: &str,
) -> bool {
    debug!("MESSAGE RECEIVED -->: {text}");

    let event = match serde_json::from_str::<UserDataEvent>(text) {
        Ok(event) => event,
        Err(error) => {
            error!("Error parsing stream message: {error}");
            return true;
        }
    };

    if event.event_type == "listenKeyExpired" {
        warn!("Listen key expired; reconnecting");
        return false;
    }

    if event.event_type != "ORDER_TRADE_UPDATE" {
        return true;
    }

    let Some(order) = event.order else {
        error!("ORDER_TRADE_UPDATE without an order payload: {text}");
        return true;
    };

    let symbol = order.symbol.clone();
    let lock = locks.lock_for(&symbol);
    let client = client.clone();
    let semaphore = semaphore.clone();

    tokio::spawn(async move {
        let _permit = match semaphore.acquire_owned().await {
            Ok(permit) => permit,
            Err(_) => return,
        };
        let _guard = lock.lock().await;

        if let Err(error) = strategies::dispatch(&client, &order).await {
            error!("Error processing message: {error}");
        }
    });

    true
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn symbol_locks_are_shared_per_symbol() {
        let locks = SymbolLocks::default();
        let first = locks.lock_for("BTCUSDT");
        let second = locks.lock_for("BTCUSDT");
        let other = locks.lock_for("ETHUSDT");
        assert!(Arc::ptr_eq(&first, &second));
        assert!(!Arc::ptr_eq(&first, &other));
    }
}
