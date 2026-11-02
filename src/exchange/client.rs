use crate::config::Credentials;
use crate::error::{AppError, Result};
use crate::exchange::filters::SymbolFilters;
use crate::exchange::models::{
    ApiErrorBody, Balance, ExchangeInfo, ListenKey, NewOrder, OrderResponse, PositionInfo,
    SymbolInfo,
};
use crate::util::{fmt_num, py_round};
use hmac::{Hmac, Mac};
use reqwest::{Client, Method};
use serde::de::DeserializeOwned;
use serde::Deserialize;
use sha2::Sha256;
use std::time::{Duration, SystemTime, UNIX_EPOCH};
use tracing::{debug, info};
use url::form_urlencoded;

pub const PROD_BASE_URL: &str = "https://fapi.binance.com";
pub const TESTNET_BASE_URL: &str = "https://testnet.binancefuture.com";

#[derive(Debug, Deserialize)]
struct ServerTime {
    #[serde(rename = "serverTime")]
    server_time: i64,
}

pub struct BinanceClient {
    http: Client,
    api_key: String,
    api_secret: String,
    base_url: String,
    testnet: bool,
    recv_window: u64,
    time_offset_ms: i64,
}

impl BinanceClient {
    /// Connect, verify the endpoint and synchronise the clock offset.
    pub async fn connect(credentials: Credentials) -> Result<Self> {
        let base_url = if credentials.testnet {
            info!("Connecting to Binance TESTNET...");
            TESTNET_BASE_URL
        } else {
            info!("Connecting to Binance PRODUCTION...");
            PROD_BASE_URL
        };

        let http = Client::builder()
            .timeout(Duration::from_secs(15))
            .build()?;

        let mut client = Self {
            http,
            api_key: credentials.api_key,
            api_secret: credentials.api_secret,
            base_url: base_url.to_string(),
            testnet: credentials.testnet,
            recv_window: 5_000,
            time_offset_ms: 0,
        };

        client.ping().await?;
        let server_time = client.server_time().await?;
        client.time_offset_ms = server_time - now_ms() as i64;
        debug!(
            "Server time offset: {} ms (testnet: {})",
            client.time_offset_ms, client.testnet
        );
        Ok(client)
    }

    pub fn testnet(&self) -> bool {
        self.testnet
    }

    pub fn ws_url(&self, listen_key: &str) -> String {
        if self.testnet {
            format!("wss://fstream.binancefuture.com/ws/{listen_key}")
        } else {
            format!("wss://fstream.binance.com/ws/{listen_key}")
        }
    }

    pub async fn ping(&self) -> Result<()> {
        self.send::<serde_json::Value>(Method::GET, "/fapi/v1/ping", Vec::new(), false)
            .await?;
        Ok(())
    }

    pub async fn server_time(&self) -> Result<i64> {
        Ok(self
            .send::<ServerTime>(Method::GET, "/fapi/v1/time", Vec::new(), false)
            .await?
            .server_time)
    }

    pub async fn exchange_info(&self) -> Result<Vec<SymbolInfo>> {
        Ok(self
            .send::<ExchangeInfo>(Method::GET, "/fapi/v1/exchangeInfo", Vec::new(), false)
            .await?
            .symbols)
    }

    pub async fn symbol_filters(&self, symbol: &str) -> Result<SymbolFilters> {
        let info = self
            .exchange_info()
            .await?
            .into_iter()
            .find(|entry| entry.symbol == symbol)
            .ok_or_else(|| AppError::UnknownSymbol(symbol.to_string()))?;
        SymbolFilters::from_symbol(&info)
    }

    /// Futures USDT wallet balance, rounded to two decimals like the Python bot.
    pub async fn wallet_balance_usdt(&self) -> Result<f64> {
        let balances = self
            .send::<Vec<Balance>>(Method::GET, "/fapi/v2/balance", Vec::new(), true)
            .await?;
        for balance in balances {
            if balance.asset == "USDT" {
                let value = balance.balance.parse::<f64>().unwrap_or(0.0);
                return Ok(py_round(value, 2));
            }
        }
        Ok(0.0)
    }

    pub async fn position_information(&self, symbol: &str) -> Result<Vec<PositionInfo>> {
        let params = vec![("symbol".to_string(), symbol.to_string())];
        self.send::<Vec<PositionInfo>>(Method::GET, "/fapi/v2/positionRisk", params, true)
            .await
    }

    pub async fn create_order(&self, order: &NewOrder) -> Result<OrderResponse> {
        let params = order_params(order);
        self.send::<OrderResponse>(Method::POST, "/fapi/v1/order", params, true)
            .await
    }

    pub async fn open_orders(&self, symbol: &str) -> Result<Vec<OrderResponse>> {
        let params = vec![("symbol".to_string(), symbol.to_string())];
        self.send::<Vec<OrderResponse>>(Method::GET, "/fapi/v1/openOrders", params, true)
            .await
    }

    pub async fn cancel_order(&self, symbol: &str, order_id: i64) -> Result<OrderResponse> {
        let params = vec![
            ("symbol".to_string(), symbol.to_string()),
            ("orderId".to_string(), order_id.to_string()),
        ];
        self.send::<OrderResponse>(Method::DELETE, "/fapi/v1/order", params, true)
            .await
    }

    pub async fn cancel_all_open_orders(&self, symbol: &str) -> Result<()> {
        let params = vec![("symbol".to_string(), symbol.to_string())];
        self.send::<serde_json::Value>(Method::DELETE, "/fapi/v1/allOpenOrders", params, true)
            .await?;
        Ok(())
    }

    pub async fn listen_key(&self) -> Result<String> {
        Ok(self
            .send::<ListenKey>(Method::POST, "/fapi/v1/listenKey", Vec::new(), true)
            .await?
            .listen_key)
    }

    pub async fn keepalive_listen_key(&self, listen_key: &str) -> Result<()> {
        let params = vec![("listenKey".to_string(), listen_key.to_string())];
        self.send::<serde_json::Value>(Method::PUT, "/fapi/v1/listenKey", params, true)
            .await?;
        Ok(())
    }

    pub async fn close_listen_key(&self, listen_key: &str) -> Result<()> {
        let params = vec![("listenKey".to_string(), listen_key.to_string())];
        self.send::<serde_json::Value>(Method::DELETE, "/fapi/v1/listenKey", params, true)
            .await?;
        Ok(())
    }

    async fn send<T: DeserializeOwned>(
        &self,
        method: Method,
        path: &str,
        mut params: Vec<(String, String)>,
        signed: bool,
    ) -> Result<T> {
        if signed {
            params.push(("recvWindow".to_string(), self.recv_window.to_string()));
            params.push((
                "timestamp".to_string(),
                (now_ms() as i64 + self.time_offset_ms).to_string(),
            ));
        }

        let mut query = encode(&params);
        if signed {
            let signature = self.sign(&query)?;
            query.push_str("&signature=");
            query.push_str(&signature);
        }

        let url = if query.is_empty() {
            format!("{}{}", self.base_url, path)
        } else {
            format!("{}{}?{}", self.base_url, path, query)
        };

        debug!("{} {} (signed: {})", method, path, signed);

        let mut request = self.http.request(method, url);
        if signed {
            request = request.header("X-MBX-APIKEY", &self.api_key);
        }

        let response = request.send().await?;
        let status = response.status();
        let body = response.text().await?;

        if !status.is_success() {
            if let Ok(api) = serde_json::from_str::<ApiErrorBody>(&body) {
                if api.code != 0 || !api.msg.is_empty() {
                    return Err(AppError::Api {
                        code: api.code,
                        msg: api.msg,
                    });
                }
            }
            return Err(AppError::msg(format!(
                "HTTP {status} from {path}: {body}"
            )));
        }

        serde_json::from_str::<T>(&body).map_err(|error| {
            AppError::msg(format!(
                "invalid response from {path}: {error} (body: {body})"
            ))
        })
    }

    fn sign(&self, payload: &str) -> Result<String> {
        let mut mac = Hmac::<Sha256>::new_from_slice(self.api_secret.as_bytes())
            .map_err(|_| AppError::msg("invalid Binance API secret"))?;
        mac.update(payload.as_bytes());
        Ok(hex::encode(mac.finalize().into_bytes()))
    }
}

fn encode(params: &[(String, String)]) -> String {
    let mut serializer = form_urlencoded::Serializer::new(String::new());
    for (key, value) in params {
        serializer.append_pair(key, value);
    }
    serializer.finish()
}

pub(crate) fn order_params(order: &NewOrder) -> Vec<(String, String)> {
    let mut params = vec![
        ("symbol".to_string(), order.symbol.clone()),
        ("side".to_string(), order.side.clone()),
        ("type".to_string(), order.order_type.clone()),
    ];

    let mut push = |key: &str, value: String| params.push((key.to_string(), value));

    if let Some(value) = &order.time_in_force {
        push("timeInForce", value.clone());
    }
    if let Some(value) = &order.position_side {
        push("positionSide", value.clone());
    }
    if let Some(value) = order.price {
        push("price", fmt_num(value));
    }
    if let Some(value) = order.quantity {
        push("quantity", fmt_num(value));
    }
    if let Some(value) = order.stop_price {
        push("stopPrice", fmt_num(value));
    }
    if let Some(value) = order.close_position {
        push("closePosition", value.to_string());
    }
    if let Some(value) = order.activation_price {
        push("activationPrice", fmt_num(value));
    }
    if let Some(value) = order.callback_rate {
        push("callbackRate", fmt_num(value));
    }

    params
}

fn now_ms() -> u128 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .expect("system clock before Unix epoch")
        .as_millis()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn order_params_include_only_present_fields() {
        let order = NewOrder {
            symbol: "BTCUSDT".into(),
            side: "BUY".into(),
            order_type: "LIMIT".into(),
            time_in_force: Some("GTC".into()),
            position_side: Some("LONG".into()),
            price: Some(100.0),
            quantity: Some(0.5),
            ..Default::default()
        };

        let params = order_params(&order);
        assert!(params.contains(&("symbol".into(), "BTCUSDT".into())));
        assert!(params.contains(&("type".into(), "LIMIT".into())));
        assert!(params.contains(&("price".into(), "100".into())));
        assert!(params.contains(&("quantity".into(), "0.5".into())));
        assert!(!params.iter().any(|(key, _)| key == "stopPrice"));
        assert!(!params.iter().any(|(key, _)| key == "closePosition"));
    }

    #[test]
    fn stop_order_has_no_quantity() {
        let order = NewOrder {
            symbol: "BTCUSDT".into(),
            side: "SELL".into(),
            order_type: "STOP_MARKET".into(),
            position_side: Some("LONG".into()),
            stop_price: Some(99.0),
            close_position: Some(true),
            ..Default::default()
        };

        let params = order_params(&order);
        assert!(params.contains(&("stopPrice".into(), "99".into())));
        assert!(params.contains(&("closePosition".into(), "true".into())));
        assert!(!params.iter().any(|(key, _)| key == "quantity"));
    }
}
