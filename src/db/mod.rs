// /src/db/mod.rs
//! This module is responsible for database operations.
//! It is used to store and retrieve data from the database.

use crate::core::commands::DbCommand;
use anyhow::Result;
use sqlx::SqlitePool;
use std::env;
use tokio::sync::mpsc;

use std::sync::OnceLock;

pub mod handlers;
pub mod models;
pub mod queries;

pub use handlers::*;
pub use models::*;
pub use queries::*;

pub type DbPool = SqlitePool;

static POOL: OnceLock<DbPool> = OnceLock::new();

pub async fn init() -> Result<&'static DbPool> {
    if let Some(pool) = POOL.get() {
        return Ok(pool);
    }

    dotenvy::dotenv().ok();
    let db_url =
        env::var("DATABASE_URL").unwrap_or_else(|_| "sqlite://tbf.db?mode=rwc".to_string());

    let pool = SqlitePool::connect(&db_url).await?;

    run_migrations(&pool).await?;

    let _ = POOL.set(pool);
    Ok(POOL.get().unwrap())
}

pub fn pool() -> &'static DbPool {
    POOL.get().expect("Database not initialized. Call db::init().await first.")
}

/// Attend commands from core and services for database operations
pub async fn run(mut rx_db: mpsc::Receiver<DbCommand>) -> Result<()> {
    let pool = init().await?;

    // listen commands
    while let Some(cmd) = rx_db.recv().await {
        handle_db_command(pool, cmd).await;
    }

    Ok(())
}

/// Run migration process for database
async fn run_migrations(pool: &DbPool) -> Result<()> {
    let migration = include_str!("../../migrations/001_create_tables.sql");

    for statement in migration.split(';').filter(|s| !s.trim().is_empty()) {
        sqlx::query(statement).execute(pool).await?;
    }

    Ok(())
}
