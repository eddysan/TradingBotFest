use super::queries::*;
use crate::core::commands::DbCommand;
use crate::db::DbPool;

pub async fn handle_db_command(pool: &DbPool, cmd: DbCommand) {
    match cmd {
        DbCommand::PostLog {
            level,
            event,
            symbol,
            strategy,
            message,
            payload,
        } => {
            insert_log(
                &pool,
                &level,
                &event,
                symbol.as_deref(),
                strategy.as_deref(),
                message.as_deref(),
                payload.as_deref(),
            )
            .await
            .ok();
        }
        DbCommand::PostSymbol {
            symbol,
            status,
            base_asset,
            quote_asset,
            price_precision,
            quantity_precision,
            tick_size,
            step_size,
            min_quantity,
            max_quantity,
        } => {
            upsert_symbol(
                &pool,
                &symbol,
                &status,
                &base_asset,
                &quote_asset,
                price_precision,
                quantity_precision,
                &tick_size,
                &step_size,
                &min_quantity,
                &max_quantity,
            )
            .await
            .ok();
        }
        DbCommand::GetSymbol { symbol, tx } => {
            let result = get_symbol(&pool, &symbol).await.ok();
            let _ = tx.send(result.flatten());
        }
        DbCommand::PostPosition {
            symbol,
            position_side,
            position_amt,
            entry_price,
            break_even_price,
            mark_price,
            unrealized_profit,
            liquidation_price,
            isolated_margin,
            notional,
            margin_asset,
            isolated_wallet,
            initial_margin,
            maint_margin,
            position_initial_margin,
            open_order_initial_margin,
            adl,
            bid_notional,
            ask_notional,
            update_time,
            leverage,
            max_notional_value,
            margin_type,
            is_auto_add_margin,
            status,
        } => {
            upsert_position(
                &pool,
                &symbol,
                &position_side,
                &position_amt,
                &entry_price,
                &break_even_price,
                &mark_price,
                &unrealized_profit,
                &liquidation_price,
                &isolated_margin,
                &notional,
                &margin_asset,
                &isolated_wallet,
                &initial_margin,
                &maint_margin,
                &position_initial_margin,
                &open_order_initial_margin,
                adl,
                bid_notional,
                ask_notional,
                update_time,
                leverage,
                max_notional_value,
                &margin_type,
                is_auto_add_margin,
                &status,
            )
            .await
            .ok();
        }
        DbCommand::GetPosition { symbol, tx } => {
            let result = get_positions(&pool, &symbol).await.ok().unwrap_or_default();
            let _ = tx.send(result);
        }
        DbCommand::PostOrder { .. } => {
            // Placeholder for now as DbCommand::PostOrder is missing many fields for insert_order
        }
        DbCommand::GetOrder { .. } => {
            // Placeholder for now as DbCommand::GetOrder is missing a return channel
        }
    }
}
