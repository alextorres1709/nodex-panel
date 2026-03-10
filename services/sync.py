"""
Background sync: pulls data from remote Railway PostgreSQL into local SQLite.
Runs in a daemon thread, never blocks the main Flask/UI thread.
"""
import time
import logging
import threading
from datetime import datetime, timezone

import sqlalchemy as sa

log = logging.getLogger("sync")

# Tables to sync (order matters — respect FK dependencies)
SYNC_TABLES = [
    "users",
    "company_info",
    "tools",
    "projects",
    "payments",
    "incomes",
    "tasks",
    "ideas",
    "credentials",
    "activity_log",
    "messages",
    "call_sessions",
    "clients",
    "notifications",
    "time_entries",
    "invoices",
]

SYNC_INTERVAL = 30  # seconds


class SyncManager:
    """Bidirectional sync between local SQLite and remote PostgreSQL."""

    def __init__(self, local_url, remote_url):
        self.local_engine = sa.create_engine(local_url)
        self.remote_engine = sa.create_engine(
            remote_url,
            pool_pre_ping=True,
            pool_size=2,
            connect_args={"connect_timeout": 10},
        )
        self._stop = threading.Event()
        self._thread = None
        self._first_sync_done = threading.Event()

    def start(self):
        """Start the background sync thread."""
        self._thread = threading.Thread(target=self._loop, daemon=True, name="sync")
        self._thread.start()

    def stop(self):
        self._stop.set()

    def wait_first_sync(self, timeout=15):
        """Block until the first sync completes (used at startup)."""
        return self._first_sync_done.wait(timeout=timeout)

    def _loop(self):
        log.info("Sync thread started")
        while not self._stop.is_set():
            try:
                self._pull_from_remote()
                if not self._first_sync_done.is_set():
                    self._first_sync_done.set()
                    log.info("First sync complete")
            except Exception as e:
                log.warning(f"Sync error: {e}")
                if not self._first_sync_done.is_set():
                    self._first_sync_done.set()  # Don't block startup on failure
            self._stop.wait(SYNC_INTERVAL)

    def _pull_from_remote(self):
        """Pull all data from remote PostgreSQL and upsert into local SQLite."""
        remote_meta = sa.MetaData()
        remote_meta.reflect(bind=self.remote_engine)

        local_meta = sa.MetaData()
        local_meta.reflect(bind=self.local_engine)

        for table_name in SYNC_TABLES:
            if table_name not in remote_meta.tables:
                continue

            remote_table = remote_meta.tables[table_name]

            # Read all rows from remote
            with self.remote_engine.connect() as rconn:
                rows = rconn.execute(sa.select(remote_table)).fetchall()
                columns = list(remote_table.columns.keys())

            if not rows:
                continue

            # Upsert into local SQLite
            with self.local_engine.begin() as lconn:
                local_table = local_meta.tables.get(table_name)
                if local_table is None:
                    continue

                # For SQLite: delete + insert is simplest and fast
                lconn.execute(sa.delete(local_table))
                for row in rows:
                    values = {}
                    for col in columns:
                        if col in local_table.columns.keys():
                            values[col] = getattr(row, col, None)
                    if values:
                        lconn.execute(sa.insert(local_table).values(**values))

        log.info(f"Synced {len(SYNC_TABLES)} tables from remote")

    def push_to_remote(self, table_name, row_id):
        """Push a single row from local to remote (called after local writes)."""
        try:
            local_meta = sa.MetaData()
            local_meta.reflect(bind=self.local_engine)
            remote_meta = sa.MetaData()
            remote_meta.reflect(bind=self.remote_engine)

            local_table = local_meta.tables.get(table_name)
            remote_table = remote_meta.tables.get(table_name)
            if local_table is None or remote_table is None:
                return

            # Read the row from local
            with self.local_engine.connect() as lconn:
                row = lconn.execute(
                    sa.select(local_table).where(local_table.c.id == row_id)
                ).fetchone()

            if row is None:
                # Row was deleted locally — delete from remote too
                with self.remote_engine.begin() as rconn:
                    rconn.execute(
                        sa.delete(remote_table).where(remote_table.c.id == row_id)
                    )
                return

            # Upsert into remote
            columns = list(local_table.columns.keys())
            values = {}
            for col in columns:
                if col in remote_table.columns.keys():
                    values[col] = getattr(row, col, None)

            with self.remote_engine.begin() as rconn:
                existing = rconn.execute(
                    sa.select(remote_table).where(remote_table.c.id == row_id)
                ).fetchone()
                if existing:
                    rconn.execute(
                        sa.update(remote_table)
                        .where(remote_table.c.id == row_id)
                        .values(**values)
                    )
                else:
                    rconn.execute(sa.insert(remote_table).values(**values))

        except Exception as e:
            log.warning(f"Push to remote failed ({table_name} #{row_id}): {e}")


# Global sync manager instance (set in app.py)
sync_manager = None


def push_change(table_name, row_id):
    """Convenience function to push a change in a background thread."""
    if sync_manager:
        threading.Thread(
            target=sync_manager.push_to_remote,
            args=(table_name, row_id),
            daemon=True,
        ).start()
