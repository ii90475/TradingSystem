"""Tests for database connection and health management."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tradingsystem.core import database


class TestInitPool:
    """Tests for database.init_pool()."""

    @pytest.mark.asyncio
    async def test_init_pool_creates_connection_pool(self):
        """Should create and open a connection pool."""
        with patch("tradingsystem.core.database.AsyncConnectionPool") as mock_pool_class:
            mock_pool = AsyncMock()
            mock_pool_class.return_value = mock_pool

            # Reset global pool
            database.pool = None

            await database.init_pool()

            mock_pool_class.assert_called_once()
            mock_pool.open.assert_called_once()
            assert database.pool is mock_pool

            # Cleanup
            database.pool = None

    @pytest.mark.asyncio
    async def test_init_pool_uses_settings_database_url(self):
        """Should use database URL from settings."""
        with patch("tradingsystem.core.database.AsyncConnectionPool") as mock_pool_class, \
             patch("tradingsystem.core.database.settings") as mock_settings:
            mock_settings.database_url = "postgresql://test:test@localhost/testdb"
            mock_pool = AsyncMock()
            mock_pool_class.return_value = mock_pool
            database.pool = None

            await database.init_pool()

            call_kwargs = mock_pool_class.call_args[1]
            assert call_kwargs["conninfo"] == "postgresql://test:test@localhost/testdb"

            database.pool = None


class TestClosePool:
    """Tests for database.close_pool()."""

    @pytest.mark.asyncio
    async def test_close_pool_closes_and_clears(self):
        """Should close pool and set to None."""
        mock_pool = AsyncMock()
        database.pool = mock_pool

        await database.close_pool()

        mock_pool.close.assert_called_once()
        assert database.pool is None

    @pytest.mark.asyncio
    async def test_close_pool_no_pool(self):
        """Should handle case when pool is None."""
        database.pool = None

        await database.close_pool()  # Should not raise

        assert database.pool is None


class TestGetConnection:
    """Tests for database.get_connection()."""

    @pytest.mark.asyncio
    async def test_get_connection_raises_when_pool_not_initialized(self):
        """Should raise RuntimeError when pool is None."""
        database.pool = None

        with pytest.raises(RuntimeError, match="not initialized"):
            async with database.get_connection():
                pass

    @pytest.mark.asyncio
    async def test_get_connection_yields_connection(self):
        """Should yield connection from pool."""
        mock_conn = AsyncMock()
        mock_pool = MagicMock()
        mock_pool.connection.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_pool.connection.return_value.__aexit__ = AsyncMock()
        database.pool = mock_pool

        async with database.get_connection() as conn:
            assert conn is mock_conn

        database.pool = None


class TestGetCursor:
    """Tests for database.get_cursor()."""

    @pytest.mark.asyncio
    async def test_get_cursor_raises_when_pool_not_initialized(self):
        """Should raise RuntimeError when pool is None."""
        database.pool = None

        with pytest.raises(RuntimeError, match="not initialized"):
            async with database.get_cursor():
                pass

    @pytest.mark.asyncio
    async def test_get_cursor_yields_dict_row_cursor(self):
        """Should yield cursor with dict_row factory."""
        mock_cursor = AsyncMock()
        mock_conn = MagicMock()
        mock_conn.cursor.return_value.__aenter__ = AsyncMock(return_value=mock_cursor)
        mock_conn.cursor.return_value.__aexit__ = AsyncMock()

        mock_pool = MagicMock()
        mock_pool.connection.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_pool.connection.return_value.__aexit__ = AsyncMock()
        database.pool = mock_pool

        async with database.get_cursor() as cur:
            assert cur is mock_cursor

        database.pool = None


class TestCheckDatabaseHealth:
    """Tests for database.check_database_health()."""

    @pytest.mark.asyncio
    async def test_health_check_healthy(self):
        """Should return healthy when query succeeds."""
        mock_cursor = AsyncMock()
        mock_cursor.execute = AsyncMock()
        mock_cursor.fetchone = AsyncMock(return_value=(1,))

        mock_conn = MagicMock()
        mock_conn.cursor.return_value.__aenter__ = AsyncMock(return_value=mock_cursor)
        mock_conn.cursor.return_value.__aexit__ = AsyncMock()

        mock_pool = MagicMock()
        mock_pool.connection.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_pool.connection.return_value.__aexit__ = AsyncMock()
        mock_pool.min_size = 2
        mock_pool.max_size = 10
        mock_pool.get_stats.return_value = {"pool_size": 5, "pool_available": 3, "requests_waiting": 0}
        database.pool = mock_pool

        result = await database.check_database_health()

        assert result["healthy"] is True
        assert result["error"] is None
        assert "pool" in result

        database.pool = None

    @pytest.mark.asyncio
    async def test_health_check_unhealthy_on_error(self):
        """Should return unhealthy when query fails."""
        with patch("tradingsystem.core.database.get_cursor") as mock_get_cursor:
            mock_get_cursor.side_effect = Exception("Connection refused")

            result = await database.check_database_health()

            assert result["healthy"] is False
            assert "Connection refused" in result["error"]

    @pytest.mark.asyncio
    async def test_health_check_returns_pool_stats(self):
        """Should include pool statistics when healthy."""
        mock_cursor = AsyncMock()
        mock_cursor.execute = AsyncMock()
        mock_cursor.fetchone = AsyncMock(return_value=(1,))

        mock_conn = MagicMock()
        mock_conn.cursor.return_value.__aenter__ = AsyncMock(return_value=mock_cursor)
        mock_conn.cursor.return_value.__aexit__ = AsyncMock()

        mock_pool = MagicMock()
        mock_pool.connection.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_pool.connection.return_value.__aexit__ = AsyncMock()
        mock_pool.min_size = 2
        mock_pool.max_size = 10
        mock_pool.get_stats.return_value = {
            "pool_size": 5,
            "pool_available": 3,
            "requests_waiting": 1,
        }
        database.pool = mock_pool

        result = await database.check_database_health()

        assert result["pool"]["min_size"] == 2
        assert result["pool"]["max_size"] == 10
        assert result["pool"]["size"] == 5
        assert result["pool"]["available"] == 3

        database.pool = None
