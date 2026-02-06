"""WebSocket connection manager for real-time rate streaming."""

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any

from fastapi import WebSocket, WebSocketDisconnect

from tradingsystem.core.config import settings
from tradingsystem.core.rateservice import rateservice_client

logger = logging.getLogger(__name__)


class RateConnectionManager:
    """Manages WebSocket connections for real-time rate updates."""

    def __init__(self):
        self.active_connections: list[WebSocket] = []
        self._broadcast_task: asyncio.Task | None = None
        self._running = False

    async def connect(self, websocket: WebSocket) -> None:
        """Accept a new WebSocket connection."""
        await websocket.accept()
        self.active_connections.append(websocket)
        logger.info(f"WebSocket connected. Total connections: {len(self.active_connections)}")

    def disconnect(self, websocket: WebSocket) -> None:
        """Remove a WebSocket connection."""
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
        logger.info(f"WebSocket disconnected. Total connections: {len(self.active_connections)}")

    async def broadcast(self, message: dict[str, Any]) -> None:
        """Broadcast a message to all connected clients."""
        if not self.active_connections:
            return

        disconnected = []
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except Exception as e:
                logger.warning(f"Failed to send to WebSocket: {e}")
                disconnected.append(connection)

        # Clean up disconnected clients
        for conn in disconnected:
            self.disconnect(conn)

    async def _poll_and_broadcast(self) -> None:
        """Background task that polls RateService and broadcasts to clients."""
        poll_interval = settings.ws_rate_poll_interval_ms / 1000.0  # Convert to seconds
        logger.info(f"Rate broadcaster started with {poll_interval*1000:.0f}ms interval")

        while self._running:
            try:
                if self.active_connections:
                    # Fetch current rates from RateService
                    rates = await rateservice_client.get_current_rates()
                    now = datetime.now(timezone.utc)

                    # Format for broadcast
                    rate_data = []
                    for rate in rates:
                        age_seconds = (now - rate.time.replace(tzinfo=timezone.utc)).total_seconds()
                        bid = float(rate.bid)
                        ask = float(rate.ask)
                        mid = (bid + ask) / 2

                        rate_data.append({
                            "pair": rate.pair,
                            "bid": f"{bid:.5f}",
                            "ask": f"{ask:.5f}",
                            "mid": f"{mid:.5f}",
                            "spread": f"{(ask - bid):.5f}",
                            "time": rate.time.isoformat(),
                            "age_seconds": round(age_seconds, 1),
                            "tradeable": rate.tradeable,
                        })

                    await self.broadcast({
                        "type": "rates",
                        "timestamp": now.isoformat(),
                        "data": rate_data,
                    })

            except Exception as e:
                logger.error(f"Rate broadcast error: {e}")
                # Send error to clients
                await self.broadcast({
                    "type": "error",
                    "message": str(e),
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                })

            await asyncio.sleep(poll_interval)

    async def start_broadcasting(self) -> None:
        """Start the background rate broadcasting task."""
        if self._running:
            return

        self._running = True
        self._broadcast_task = asyncio.create_task(self._poll_and_broadcast())
        logger.info("Rate broadcaster started")

    async def stop_broadcasting(self) -> None:
        """Stop the background rate broadcasting task."""
        self._running = False
        if self._broadcast_task:
            self._broadcast_task.cancel()
            try:
                await self._broadcast_task
            except asyncio.CancelledError:
                pass
            self._broadcast_task = None
        logger.info("Rate broadcaster stopped")

    @property
    def connection_count(self) -> int:
        """Return the number of active connections."""
        return len(self.active_connections)

    @property
    def is_running(self) -> bool:
        """Return whether the broadcaster is running."""
        return self._running


# Global instance
rate_manager = RateConnectionManager()
