"""
Session API endpoints for chart state persistence.

This module provides REST endpoints for saving and retrieving chart session state,
including the current instrument, period, and active indicators. Session state is
persisted to the database, allowing users to resume their chart configuration
across browser sessions and devices.

Endpoints:
    GET  /session - Retrieve saved session state
    PUT  /session - Save/update session state
    DELETE /session - Clear session state

The session_key parameter allows for multiple saved sessions (e.g., per-user),
but defaults to "default" for single-user setups.
"""

from fastapi import APIRouter, HTTPException

from tradingsystem.models.session import ChartSession, ChartSessionUpdate
from tradingsystem.services import session_service

router = APIRouter(prefix="/session", tags=["session"])


@router.get("", response_model=ChartSession | None)
async def get_session(session_key: str = "default") -> ChartSession | None:
    """
    Get the current chart session state.

    Retrieves the saved chart configuration including:
    - instrument: Currently selected currency pair (e.g., EUR_USD)
    - period: Chart timeframe (e.g., M5, H1, D)
    - indicators: List of active indicators with their settings

    Args:
        session_key: Session identifier (default: "default")

    Returns:
        ChartSession object if found, null if no session exists.
        Frontend should fall back to defaults when null is returned.
    """
    return await session_service.get_session(session_key)


@router.put("", response_model=ChartSession)
async def save_session(
    update: ChartSessionUpdate,
    session_key: str = "default",
) -> ChartSession:
    """
    Save the current chart session state.

    Persists the chart configuration to the database. Uses upsert semantics:
    creates a new session if one doesn't exist, or updates the existing one.

    The frontend should call this endpoint whenever:
    - User changes instrument or period
    - User adds, removes, or modifies indicators

    Args:
        update: Session state to save (instrument, period, indicators)
        session_key: Session identifier (default: "default")

    Returns:
        The saved ChartSession with updated timestamp.
    """
    return await session_service.save_session(session_key, update)


@router.delete("", status_code=204)
async def delete_session(session_key: str = "default") -> None:
    """
    Delete a chart session.

    Removes the saved session state, causing the frontend to revert to defaults
    on next load.

    Args:
        session_key: Session identifier (default: "default")

    Raises:
        HTTPException 404: If no session exists with the given key.
    """
    deleted = await session_service.delete_session(session_key)
    if not deleted:
        raise HTTPException(status_code=404, detail="Session not found")
