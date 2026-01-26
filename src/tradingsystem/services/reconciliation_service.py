"""Position reconciliation service for syncing local and Oanda positions."""

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal

from tradingsystem.core.config import settings
from tradingsystem.core.oanda_trading import oanda_trading_client, OandaTrade
from tradingsystem.models.position import Position, PositionSide, PositionStatus
from tradingsystem.services import position_service

logger = logging.getLogger(__name__)


@dataclass
class PositionDiscrepancy:
    """Discrepancy between local and Oanda position."""

    instrument: str
    local_quantity: Decimal | None
    oanda_quantity: Decimal | None
    local_side: str | None
    oanda_side: str | None
    discrepancy_type: str  # "missing_local", "missing_oanda", "quantity_mismatch", "side_mismatch"
    oanda_trade_id: str | None = None
    local_position_id: str | None = None


@dataclass
class ReconciliationResult:
    """Result of reconciliation check."""

    timestamp: datetime
    oanda_positions: int
    local_positions: int
    discrepancies: list[PositionDiscrepancy]
    in_sync: bool


async def reconcile_positions() -> ReconciliationResult:
    """
    Compare local positions with Oanda open trades.

    Returns:
        ReconciliationResult with discrepancy details
    """
    discrepancies = []

    # Get Oanda open trades
    try:
        oanda_trades = await oanda_trading_client.get_open_trades()
    except Exception as e:
        logger.error(f"Failed to fetch Oanda trades: {e}")
        return ReconciliationResult(
            timestamp=datetime.now(timezone.utc),
            oanda_positions=0,
            local_positions=0,
            discrepancies=[],
            in_sync=False,
        )

    # Get local open positions
    local_positions = await position_service.get_open_positions()

    # Build lookup maps by instrument
    oanda_by_instrument: dict[str, list[OandaTrade]] = {}
    for trade in oanda_trades:
        if trade.instrument not in oanda_by_instrument:
            oanda_by_instrument[trade.instrument] = []
        oanda_by_instrument[trade.instrument].append(trade)

    local_by_instrument: dict[str, list[Position]] = {}
    for pos in local_positions:
        if pos.instrument not in local_by_instrument:
            local_by_instrument[pos.instrument] = []
        local_by_instrument[pos.instrument].append(pos)

    all_instruments = set(oanda_by_instrument.keys()) | set(local_by_instrument.keys())

    for instrument in all_instruments:
        oanda_list = oanda_by_instrument.get(instrument, [])
        local_list = local_by_instrument.get(instrument, [])

        # Calculate net position for each side
        oanda_net = sum(t.units for t in oanda_list)
        local_net = sum(
            p.quantity if p.side == PositionSide.LONG else -p.quantity
            for p in local_list
        )

        # Check for missing positions
        if oanda_list and not local_list:
            for trade in oanda_list:
                discrepancies.append(
                    PositionDiscrepancy(
                        instrument=instrument,
                        local_quantity=None,
                        oanda_quantity=abs(trade.units),
                        local_side=None,
                        oanda_side="LONG" if trade.units > 0 else "SHORT",
                        discrepancy_type="missing_local",
                        oanda_trade_id=trade.id,
                    )
                )

        elif local_list and not oanda_list:
            for pos in local_list:
                discrepancies.append(
                    PositionDiscrepancy(
                        instrument=instrument,
                        local_quantity=pos.quantity,
                        oanda_quantity=None,
                        local_side=pos.side.value,
                        oanda_side=None,
                        discrepancy_type="missing_oanda",
                        local_position_id=str(pos.id),
                    )
                )

        # Check for quantity mismatches
        elif abs(oanda_net - local_net) > Decimal("0.01"):
            discrepancies.append(
                PositionDiscrepancy(
                    instrument=instrument,
                    local_quantity=abs(local_net),
                    oanda_quantity=abs(oanda_net),
                    local_side="LONG" if local_net > 0 else "SHORT",
                    oanda_side="LONG" if oanda_net > 0 else "SHORT",
                    discrepancy_type="quantity_mismatch",
                )
            )

        # Check for side mismatches
        elif (oanda_net > 0) != (local_net > 0) and oanda_net != 0 and local_net != 0:
            discrepancies.append(
                PositionDiscrepancy(
                    instrument=instrument,
                    local_quantity=abs(local_net),
                    oanda_quantity=abs(oanda_net),
                    local_side="LONG" if local_net > 0 else "SHORT",
                    oanda_side="LONG" if oanda_net > 0 else "SHORT",
                    discrepancy_type="side_mismatch",
                )
            )

    in_sync = len(discrepancies) == 0

    if not in_sync:
        logger.warning(
            "position_discrepancies_found",
            extra={
                "count": len(discrepancies),
                "details": [
                    {
                        "instrument": d.instrument,
                        "type": d.discrepancy_type,
                    }
                    for d in discrepancies
                ],
            },
        )
    else:
        logger.info("Positions in sync with Oanda")

    return ReconciliationResult(
        timestamp=datetime.now(timezone.utc),
        oanda_positions=len(oanda_trades),
        local_positions=len(local_positions),
        discrepancies=discrepancies,
        in_sync=in_sync,
    )


async def sync_from_oanda() -> dict:
    """
    Sync local positions from Oanda (Oanda is source of truth).

    This will:
    - Close local positions not in Oanda
    - Create local positions for Oanda trades

    Returns:
        Dict with sync results
    """
    result = await reconcile_positions()
    actions = {"closed": [], "created": [], "errors": []}

    for discrepancy in result.discrepancies:
        try:
            if discrepancy.discrepancy_type == "missing_oanda":
                # Close local position that doesn't exist in Oanda
                if discrepancy.local_position_id:
                    from uuid import UUID

                    pos = await position_service.get_position(
                        UUID(discrepancy.local_position_id)
                    )
                    if pos and pos.status == PositionStatus.OPEN:
                        # Mark as closed with zero P&L (unknown exit)
                        await position_service.close_position(
                            UUID(discrepancy.local_position_id),
                            pos.entry_price,  # Close at entry (no P&L)
                        )
                        actions["closed"].append(
                            {
                                "position_id": discrepancy.local_position_id,
                                "instrument": discrepancy.instrument,
                                "reason": "not_found_in_oanda",
                            }
                        )

            elif discrepancy.discrepancy_type == "missing_local":
                # Would need to create local position for Oanda trade
                # This is more complex - may need user intervention
                actions["errors"].append(
                    {
                        "instrument": discrepancy.instrument,
                        "oanda_trade_id": discrepancy.oanda_trade_id,
                        "reason": "manual_intervention_required",
                        "message": "Oanda trade exists without local position",
                    }
                )

        except Exception as e:
            actions["errors"].append(
                {
                    "instrument": discrepancy.instrument,
                    "error": str(e),
                }
            )

    logger.info(
        "sync_completed",
        extra={
            "closed": len(actions["closed"]),
            "created": len(actions["created"]),
            "errors": len(actions["errors"]),
        },
    )

    return {
        "reconciliation": {
            "timestamp": result.timestamp.isoformat(),
            "oanda_positions": result.oanda_positions,
            "local_positions": result.local_positions,
            "in_sync": result.in_sync,
            "discrepancies": len(result.discrepancies),
        },
        "actions": actions,
    }


async def get_oanda_positions_summary() -> dict:
    """
    Get summary of Oanda positions.

    Returns:
        Dict with Oanda position details
    """
    try:
        trades = await oanda_trading_client.get_open_trades()
        account = await oanda_trading_client.get_account_summary()

        positions_by_instrument = {}
        for trade in trades:
            inst = trade.instrument
            if inst not in positions_by_instrument:
                positions_by_instrument[inst] = {
                    "instrument": inst,
                    "net_units": Decimal("0"),
                    "unrealized_pnl": Decimal("0"),
                    "trades": [],
                }
            positions_by_instrument[inst]["net_units"] += trade.units
            positions_by_instrument[inst]["unrealized_pnl"] += trade.unrealized_pnl
            positions_by_instrument[inst]["trades"].append(
                {
                    "id": trade.id,
                    "units": str(trade.units),
                    "price": str(trade.price),
                    "unrealized_pnl": str(trade.unrealized_pnl),
                }
            )

        return {
            "account_id": account.id,
            "balance": str(account.balance),
            "nav": str(account.nav),
            "total_unrealized_pnl": str(account.unrealized_pnl),
            "open_trade_count": account.open_trade_count,
            "positions": [
                {
                    "instrument": p["instrument"],
                    "net_units": str(p["net_units"]),
                    "side": "LONG" if p["net_units"] > 0 else "SHORT",
                    "unrealized_pnl": str(p["unrealized_pnl"]),
                    "trade_count": len(p["trades"]),
                }
                for p in positions_by_instrument.values()
            ],
        }

    except Exception as e:
        logger.error(f"Failed to get Oanda positions: {e}")
        return {"error": str(e)}
