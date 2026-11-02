pub mod cardiac;
pub mod load_unload;
pub mod recovery_zone;

use crate::exchange::models::OrderEvent;
use crate::exchange::BinanceClient;
use crate::store::get_strategy;

/// Send one filled order event to the strategy that owns the symbol.
///
/// The caller is responsible for serialising events per symbol.
pub async fn dispatch(client: &BinanceClient, event: &OrderEvent) -> crate::Result<()> {
    match get_strategy(&event.symbol).as_deref() {
        Some("THE_LOAD_UNLOAD_GRID") => {
            let mut grid = load_unload::LUGrid::new(&event.symbol)?;
            grid.attend_message(client, event).await
        }
        Some("CARDIAC") => {
            let mut grid = cardiac::CardiacGrid::new(&event.symbol)?;
            grid.attend_message(client, event).await
        }
        Some("RECOVERY_ZONE") => {
            let mut zone = recovery_zone::RecoveryZone::new(&event.symbol)?;
            zone.attend_message(client, event).await
        }
        Some(other) => {
            tracing::warn!("{} - unknown strategy {other}", event.symbol);
            Ok(())
        }
        None => {
            tracing::debug!("{} - no operation file, ignoring event", event.symbol);
            Ok(())
        }
    }
}
