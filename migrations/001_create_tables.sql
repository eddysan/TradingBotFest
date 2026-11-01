-- Migration: Create all tables for trading bot

-- Logs table
CREATE TABLE IF NOT EXISTS logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    level TEXT NOT NULL,
    event TEXT NOT NULL,
    symbol TEXT,
    strategy TEXT,
    message TEXT,
    payload TEXT
);

-- Symbols table
CREATE TABLE IF NOT EXISTS symbols (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol TEXT NOT NULL UNIQUE,
    status TEXT NOT NULL,
    base_asset TEXT NOT NULL,
    quote_asset TEXT NOT NULL,
    price_precision INTEGER NOT NULL,
    quantity_precision INTEGER NOT NULL,
    tick_size TEXT NOT NULL,
    step_size TEXT NOT NULL,
    min_quantity TEXT NOT NULL,
    max_quantity TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Strategies table
CREATE TABLE IF NOT EXISTS strategies (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    symbol TEXT NOT NULL,
    timeframe TEXT NOT NULL,
    is_active INTEGER NOT NULL DEFAULT 1,
    parameters TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Positions table
CREATE TABLE IF NOT EXISTS positions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol TEXT NOT NULL,
    position_side TEXT NOT NULL,
    position_amt TEXT NOT NULL,
    entry_price TEXT NOT NULL,
    break_even_price TEXT NOT NULL,
    mark_price TEXT NOT NULL,
    unrealized_profit TEXT NOT NULL,
    liquidation_price TEXT NOT NULL,
    isolated_margin TEXT NOT NULL,
    notional TEXT NOT NULL,
    margin_asset TEXT NOT NULL,
    isolated_wallet TEXT NOT NULL,
    initial_margin TEXT NOT NULL,
    maint_margin TEXT NOT NULL,
    position_initial_margin TEXT NOT NULL,
    open_order_initial_margin TEXT NOT NULL,
    adl INTEGER NOT NULL,
    bid_notional INTEGER NOT NULL,
    ask_notional INTEGER NOT NULL,
    update_time INTEGER NOT NULL,
    leverage INTEGER NOT NULL,
    max_notional_value REAL NOT NULL,
    margin_type TEXT NOT NULL,
    is_auto_add_margin INTEGER NOT NULL,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Orders table
CREATE TABLE IF NOT EXISTS orders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol TEXT,
    strategy TEXT,
    label TEXT,
    position_side TEXT,
    order_id INTEGER,
    client_order_id TEXT,
    label_order INTEGER NOT NULL DEFAULT 0,
    order_type TEXT,
    side TEXT,
    price TEXT NOT NULL,
    avg_price TEXT NOT NULL,
    orig_qty TEXT NOT NULL,
    executed_qty TEXT NOT NULL,
    status TEXT,
    time_in_force TEXT NOT NULL DEFAULT 'GTC',
    reduce_only INTEGER NOT NULL DEFAULT 0,
    update_time INTEGER NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Indexes for common queries
CREATE INDEX IF NOT EXISTS idx_positions_symbol ON positions(symbol);
CREATE INDEX IF NOT EXISTS idx_positions_status ON positions(status);
CREATE INDEX IF NOT EXISTS idx_orders_symbol ON orders(symbol);
CREATE INDEX IF NOT EXISTS idx_orders_status ON orders(status);
CREATE INDEX IF NOT EXISTS idx_logs_event ON logs(event);
CREATE INDEX IF NOT EXISTS idx_logs_created_at ON logs(created_at);
