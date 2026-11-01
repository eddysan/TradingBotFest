use super::models::{Log, Order, Position, Strategy, Symbol};
use crate::db::DbPool;
use anyhow::Result;
use sqlx::FromRow;

// ── LOGS ──────────────────────────────────────────────────────────────────────

pub async fn insert_log(
    pool: &DbPool,
    level: &str,
    event: &str,
    symbol: Option<&str>,
    strategy: Option<&str>,
    message: Option<&str>,
    payload: Option<&str>,
) -> Result<i64> {
    let result = sqlx::query(
        "INSERT INTO logs (level, event, symbol, strategy, message, payload) VALUES (?, ?, ?, ?, ?, ?)",
    )
    .bind(level)
    .bind(event)
    .bind(symbol)
    .bind(strategy)
    .bind(message)
    .bind(payload)
    .execute(pool)
    .await?;

    Ok(result.last_insert_rowid())
}

// ── SYMBOLS ───────────────────────────────────────────────────────────────────

pub async fn upsert_symbol(
    pool: &DbPool,
    symbol: &str,
    status: &str,
    base_asset: &str,
    quote_asset: &str,
    price_precision: i32,
    quantity_precision: i32,
    tick_size: &str,
    step_size: &str,
    min_quantity: &str,
    max_quantity: &str,
) -> Result<()> {
    sqlx::query(
        r#"
        INSERT INTO symbols (symbol, status, base_asset, quote_asset, price_precision, 
                           quantity_precision, tick_size, step_size, min_quantity, max_quantity)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(symbol) DO UPDATE SET
            status = excluded.status,
            base_asset = excluded.base_asset,
            quote_asset = excluded.quote_asset,
            price_precision = excluded.price_precision,
            quantity_precision = excluded.quantity_precision,
            tick_size = excluded.tick_size,
            step_size = excluded.step_size,
            min_quantity = excluded.min_quantity,
            max_quantity = excluded.max_quantity
        "#,
    )
    .bind(symbol)
    .bind(status)
    .bind(base_asset)
    .bind(quote_asset)
    .bind(price_precision)
    .bind(quantity_precision)
    .bind(tick_size)
    .bind(step_size)
    .bind(min_quantity)
    .bind(max_quantity)
    .execute(pool)
    .await?;

    Ok(())
}

pub async fn get_symbol(pool: &DbPool, symbol: &str) -> Result<Option<Symbol>> {
    let row = sqlx::query_as::<_, SymbolRow>(
        "SELECT id, symbol, status, base_asset, quote_asset, price_precision, quantity_precision, tick_size, step_size, min_quantity, max_quantity, created_at FROM symbols WHERE symbol = ?",
    )
    .bind(symbol)
    .fetch_optional(pool)
    .await?;

    Ok(row.map(|r| r.into()))
}

// ── POSITIONS ─────────────────────────────────────────────────────────────────

pub async fn upsert_position(
    pool: &DbPool,
    symbol: &str,
    position_side: &str,
    position_amt: &str,
    entry_price: &str,
    break_even_price: &str,
    mark_price: &str,
    unrealized_profit: &str,
    liquidation_price: &str,
    isolated_margin: &str,
    notional: &str,
    margin_asset: &str,
    isolated_wallet: &str,
    initial_margin: &str,
    maint_margin: &str,
    position_initial_margin: &str,
    open_order_initial_margin: &str,
    adl: i32,
    bid_notional: i32,
    ask_notional: i64,
    update_time: i64,
    leverage: i32,
    max_notional_value: f64,
    margin_type: &str,
    is_auto_add_margin: bool,
    status: &str,
) -> Result<()> {
    sqlx::query(
        r#"
        INSERT INTO positions (symbol, position_side, position_amt, entry_price, break_even_price,
                             mark_price, unrealized_profit, liquidation_price, isolated_margin,
                             notional, margin_asset, isolated_wallet, initial_margin, maint_margin,
                             position_initial_margin, open_order_initial_margin, adl, bid_notional,
                             ask_notional, update_time, leverage, max_notional_value, margin_type,
                             is_auto_add_margin, status)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
            symbol = excluded.symbol,
            position_side = excluded.position_side,
            position_amt = excluded.position_amt,
            entry_price = excluded.entry_price,
            break_even_price = excluded.break_even_price,
            mark_price = excluded.mark_price,
            unrealized_profit = excluded.unrealized_profit,
            liquidation_price = excluded.liquidation_price,
            isolated_margin = excluded.isolated_margin,
            notional = excluded.notional,
            margin_asset = excluded.margin_asset,
            isolated_wallet = excluded.isolated_wallet,
            initial_margin = excluded.initial_margin,
            maint_margin = excluded.maint_margin,
            position_initial_margin = excluded.position_initial_margin,
            open_order_initial_margin = excluded.open_order_initial_margin,
            adl = excluded.adl,
            bid_notional = excluded.bid_notional,
            ask_notional = excluded.ask_notional,
            update_time = excluded.update_time,
            leverage = excluded.leverage,
            max_notional_value = excluded.max_notional_value,
            margin_type = excluded.margin_type,
            is_auto_add_margin = excluded.is_auto_add_margin,
            status = excluded.status,
            updated_at = datetime('now')
        "#,
    )
    .bind(symbol)
    .bind(position_side)
    .bind(position_amt)
    .bind(entry_price)
    .bind(break_even_price)
    .bind(mark_price)
    .bind(unrealized_profit)
    .bind(liquidation_price)
    .bind(isolated_margin)
    .bind(notional)
    .bind(margin_asset)
    .bind(isolated_wallet)
    .bind(initial_margin)
    .bind(maint_margin)
    .bind(position_initial_margin)
    .bind(open_order_initial_margin)
    .bind(adl)
    .bind(bid_notional)
    .bind(ask_notional)
    .bind(update_time)
    .bind(leverage)
    .bind(max_notional_value)
    .bind(margin_type)
    .bind(is_auto_add_margin)
    .bind(status)
    .execute(pool)
    .await?;

    Ok(())
}

pub async fn get_positions(pool: &DbPool, symbol: &str) -> Result<Vec<Position>> {
    let rows = sqlx::query_as::<_, PositionRow>(
        "SELECT id, symbol, position_side, position_amt, entry_price, break_even_price, mark_price, unrealized_profit, liquidation_price, isolated_margin, notional, margin_asset, isolated_wallet, initial_margin, maint_margin, position_initial_margin, open_order_initial_margin, adl, bid_notional, ask_notional, update_time, leverage, max_notional_value, margin_type, is_auto_add_margin, status, created_at, updated_at FROM positions WHERE symbol = ?",
    )
    .bind(symbol)
    .fetch_all(pool)
    .await?;

    Ok(rows.into_iter().map(|r| r.into()).collect())
}

pub async fn get_open_positions(pool: &DbPool) -> Result<Vec<Position>> {
    let rows = sqlx::query_as::<_, PositionRow>(
        "SELECT id, symbol, position_side, position_amt, entry_price, break_even_price, mark_price, unrealized_profit, liquidation_price, isolated_margin, notional, margin_asset, isolated_wallet, initial_margin, maint_margin, position_initial_margin, open_order_initial_margin, adl, bid_notional, ask_notional, update_time, leverage, max_notional_value, margin_type, is_auto_add_margin, status, created_at, updated_at FROM positions WHERE status NOT IN ('CLOSED', 'LIQUIDATED')",
    )
    .fetch_all(pool)
    .await?;

    Ok(rows.into_iter().map(|r| r.into()).collect())
}

// ── ORDERS ─────────────────────────────────────────────────────────────────────

pub async fn insert_order(
    pool: &DbPool,
    symbol: Option<&str>,
    strategy: Option<&str>,
    label: Option<&str>,
    position_side: Option<&str>,
    order_id: Option<i64>,
    client_order_id: Option<&str>,
    label_order: i32,
    order_type: Option<&str>,
    side: Option<&str>,
    price: &str,
    avg_price: &str,
    orig_qty: &str,
    executed_qty: &str,
    status: Option<&str>,
    time_in_force: &str,
    reduce_only: bool,
    update_time: i64,
) -> Result<i64> {
    let result = sqlx::query(
        r#"
        INSERT INTO orders (symbol, strategy, label, position_side, order_id, client_order_id,
                          label_order, order_type, side, price, avg_price, orig_qty, executed_qty,
                          status, time_in_force, reduce_only, update_time)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        "#,
    )
    .bind(symbol)
    .bind(strategy)
    .bind(label)
    .bind(position_side)
    .bind(order_id)
    .bind(client_order_id)
    .bind(label_order)
    .bind(order_type)
    .bind(side)
    .bind(price)
    .bind(avg_price)
    .bind(orig_qty)
    .bind(executed_qty)
    .bind(status)
    .bind(time_in_force)
    .bind(reduce_only)
    .bind(update_time)
    .execute(pool)
    .await?;

    Ok(result.last_insert_rowid())
}

pub async fn get_orders(pool: &DbPool, symbol: Option<&str>) -> Result<Vec<Order>> {
    let rows = if let Some(s) = symbol {
        sqlx::query_as::<_, OrderRow>(
            "SELECT id, symbol, strategy, label, position_side, order_id, client_order_id, label_order, order_type, side, price, avg_price, orig_qty, executed_qty, status, time_in_force, reduce_only, update_time, created_at, updated_at FROM orders WHERE symbol = ? ORDER BY created_at DESC",
        )
        .bind(s)
        .fetch_all(pool)
        .await?
    } else {
        sqlx::query_as::<_, OrderRow>(
            "SELECT id, symbol, strategy, label, position_side, order_id, client_order_id, label_order, order_type, side, price, avg_price, orig_qty, executed_qty, status, time_in_force, reduce_only, update_time, created_at, updated_at FROM orders ORDER BY created_at DESC",
        )
        .fetch_all(pool)
        .await?
    };

    Ok(rows.into_iter().map(|r| r.into()).collect())
}

// ── STRATEGIES ─────────────────────────────────────────────────────────────────

pub async fn insert_strategy(
    pool: &DbPool,
    name: &str,
    symbol: &str,
    timeframe: &str,
    is_active: bool,
    parameters: Option<&str>,
) -> Result<i64> {
    let result = sqlx::query(
        "INSERT INTO strategies (name, symbol, timeframe, is_active, parameters) VALUES (?, ?, ?, ?, ?)",
    )
    .bind(name)
    .bind(symbol)
    .bind(timeframe)
    .bind(is_active)
    .bind(parameters)
    .execute(pool)
    .await?;

    Ok(result.last_insert_rowid())
}

pub async fn get_strategies(pool: &DbPool, active_only: bool) -> Result<Vec<Strategy>> {
    let rows = if active_only {
        sqlx::query_as::<_, StrategyRow>(
            "SELECT id, name, symbol, timeframe, is_active, parameters, created_at, updated_at FROM strategies WHERE is_active = 1",
        )
        .fetch_all(pool)
        .await?
    } else {
        sqlx::query_as::<_, StrategyRow>(
            "SELECT id, name, symbol, timeframe, is_active, parameters, created_at, updated_at FROM strategies",
        )
        .fetch_all(pool)
        .await?
    };

    Ok(rows.into_iter().map(|r| r.into()).collect())
}

// ── Internal row types ────────────────────────────────────────────────────────

#[derive(FromRow)]
struct LogRow {
    id: i64,
    created_at: String,
    level: String,
    event: String,
    symbol: Option<String>,
    strategy: Option<String>,
    message: Option<String>,
    payload: Option<String>,
}

impl From<LogRow> for Log {
    fn from(r: LogRow) -> Self {
        Log {
            id: r.id,
            created_at: r.created_at,
            level: r.level,
            event: r.event,
            symbol: r.symbol,
            strategy: r.strategy,
            message: r.message,
            payload: r.payload,
        }
    }
}

#[derive(FromRow)]
struct SymbolRow {
    id: i64,
    symbol: String,
    status: String,
    base_asset: String,
    quote_asset: String,
    price_precision: i32,
    quantity_precision: i32,
    tick_size: String,
    step_size: String,
    min_quantity: String,
    max_quantity: String,
    created_at: String,
}

impl From<SymbolRow> for Symbol {
    fn from(r: SymbolRow) -> Self {
        Symbol {
            id: r.id,
            symbol: r.symbol,
            status: r.status,
            base_asset: r.base_asset,
            quote_asset: r.quote_asset,
            price_precision: r.price_precision,
            quantity_precision: r.quantity_precision,
            tick_size: r.tick_size.parse().unwrap_or_default(),
            step_size: r.step_size.parse().unwrap_or_default(),
            min_quantity: r.min_quantity.parse().unwrap_or_default(),
            max_quantity: r.max_quantity.parse().unwrap_or_default(),
            created_at: r.created_at,
        }
    }
}

#[derive(FromRow)]
struct StrategyRow {
    id: i64,
    name: String,
    symbol: String,
    timeframe: String,
    is_active: bool,
    parameters: Option<String>,
    created_at: String,
    updated_at: String,
}

impl From<StrategyRow> for Strategy {
    fn from(r: StrategyRow) -> Self {
        Strategy {
            id: r.id,
            name: r.name,
            symbol: r.symbol,
            timeframe: r.timeframe,
            is_active: r.is_active,
            parameters: r.parameters,
            created_at: r.created_at,
            updated_at: r.updated_at,
        }
    }
}

#[derive(FromRow)]
struct PositionRow {
    id: i64,
    symbol: String,
    position_side: String,
    position_amt: String,
    entry_price: String,
    break_even_price: String,
    mark_price: String,
    unrealized_profit: String,
    liquidation_price: String,
    isolated_margin: String,
    notional: String,
    margin_asset: String,
    isolated_wallet: String,
    initial_margin: String,
    maint_margin: String,
    position_initial_margin: String,
    open_order_initial_margin: String,
    adl: i32,
    bid_notional: i32,
    ask_notional: i64,
    update_time: i64,
    leverage: i32,
    max_notional_value: f64,
    margin_type: String,
    is_auto_add_margin: bool,
    status: String,
    created_at: String,
    updated_at: String,
}

impl From<PositionRow> for Position {
    fn from(r: PositionRow) -> Self {
        Position {
            id: r.id,
            symbol: r.symbol,
            position_side: r.position_side,
            position_amt: r.position_amt.parse().unwrap_or_default(),
            entry_price: r.entry_price.parse().unwrap_or_default(),
            break_even_price: r.break_even_price.parse().unwrap_or_default(),
            mark_price: r.mark_price.parse().unwrap_or_default(),
            unrealized_profit: r.unrealized_profit.parse().unwrap_or_default(),
            liquidation_price: r.liquidation_price.parse().unwrap_or_default(),
            isolated_margin: r.isolated_margin.parse().unwrap_or_default(),
            notional: r.notional.parse().unwrap_or_default(),
            margin_asset: r.margin_asset,
            isolated_wallet: r.isolated_wallet.parse().unwrap_or_default(),
            initial_margin: r.initial_margin.parse().unwrap_or_default(),
            maint_margin: r.maint_margin.parse().unwrap_or_default(),
            position_initial_margin: r.position_initial_margin.parse().unwrap_or_default(),
            open_order_initial_margin: r.open_order_initial_margin.parse().unwrap_or_default(),
            adl: r.adl,
            bid_notional: r.bid_notional,
            ask_notional: r.ask_notional,
            update_time: r.update_time,
            leverage: r.leverage,
            max_notional_value: r.max_notional_value,
            margin_type: r.margin_type,
            is_auto_add_margin: r.is_auto_add_margin,
            status: r.status,
            created_at: r.created_at,
            updated_at: r.updated_at,
        }
    }
}

#[derive(FromRow)]
struct OrderRow {
    id: i64,
    symbol: Option<String>,
    strategy: Option<String>,
    label: Option<String>,
    position_side: Option<String>,
    order_id: Option<i64>,
    client_order_id: Option<String>,
    label_order: i32,
    order_type: Option<String>,
    side: Option<String>,
    price: String,
    avg_price: String,
    orig_qty: String,
    executed_qty: String,
    status: Option<String>,
    time_in_force: String,
    reduce_only: bool,
    update_time: i64,
    created_at: String,
    updated_at: String,
}

impl From<OrderRow> for Order {
    fn from(r: OrderRow) -> Self {
        Order {
            id: r.id,
            symbol: r.symbol,
            strategy: r.strategy,
            label: r.label,
            position_side: r.position_side,
            order_id: r.order_id,
            client_order_id: r.client_order_id,
            label_order: r.label_order,
            order_type: r.order_type,
            side: r.side,
            price: r.price.parse().unwrap_or_default(),
            avg_price: r.avg_price.parse().unwrap_or_default(),
            orig_qty: r.orig_qty.parse().unwrap_or_default(),
            executed_qty: r.executed_qty.parse().unwrap_or_default(),
            status: r.status,
            time_in_force: r.time_in_force,
            reduce_only: r.reduce_only,
            update_time: r.update_time,
            created_at: r.created_at,
            updated_at: r.updated_at,
        }
    }
}
