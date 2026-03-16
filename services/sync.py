"""
Background sync: pulls data from remote Railway PostgreSQL into local SQLite.
Runs in a daemon thread, never blocks the main Flask/UI thread.
"""
import time
import queue
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
    "project_contacts",
    "companies",
    "company_contacts",
    "payments",
    "incomes",
    "tasks",
    "task_assignments",
    "subtasks",
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

SYNC_INTERVAL = 10  # seconds (was 30 — reduced for near-real-time)
_META_CACHE_TTL = 300  # 5 minutes


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
        self._lock = threading.Lock()

        # Metadata cache (avoid reflecting 17 tables on every push)
        self._cached_local_meta = None
        self._cached_remote_meta = None
        self._meta_cache_time = 0

        # Sync version counter — incremented after each successful pull
        # Frontend polls this to detect changes and refresh UI
        self.sync_version = 0

    def ensure_remote_tables(self):
        """Create missing tables on remote PostgreSQL based on local SQLite schema."""
        try:
            local_meta = sa.MetaData()
            local_meta.reflect(bind=self.local_engine)
            remote_meta = sa.MetaData()
            remote_meta.reflect(bind=self.remote_engine)

            for table_name in SYNC_TABLES:
                if table_name in local_meta.tables and table_name not in remote_meta.tables:
                    local_table = local_meta.tables[table_name]
                    # Recreate table definition for remote engine (PostgreSQL)
                    cols = []
                    for col in local_table.columns:
                        # Map SQLite types to PostgreSQL-compatible types
                        col_type = col.type
                        if isinstance(col_type, sa.types.NullType):
                            col_type = sa.Text()
                        new_col = sa.Column(
                            col.name, col_type,
                            primary_key=col.primary_key,
                            nullable=col.nullable,
                        )
                        cols.append(new_col)
                    new_table = sa.Table(table_name, sa.MetaData(), *cols)
                    new_table.create(bind=self.remote_engine)
                    log.info(f"Created remote table: {table_name}")

            # Invalidate metadata cache after creating tables
            self._meta_cache_time = 0
        except Exception as e:
            log.warning(f"Failed to ensure remote tables: {e}")

    def start(self):
        """Start the background sync thread."""
        self.ensure_remote_tables()
        self._thread = threading.Thread(target=self._loop, daemon=True, name="sync")
        self._thread.start()

    def stop(self):
        self._stop.set()

    def wait_first_sync(self, timeout=15):
        """Block until the first sync completes (used at startup)."""
        return self._first_sync_done.wait(timeout=timeout)

    def _get_metadata(self, force_refresh=False):
        """Return (local_meta, remote_meta) with caching to avoid expensive reflection."""
        now = time.time()
        if (force_refresh
                or not self._cached_local_meta
                or (now - self._meta_cache_time) > _META_CACHE_TTL):
            local_meta = sa.MetaData()
            local_meta.reflect(bind=self.local_engine)
            remote_meta = sa.MetaData()
            remote_meta.reflect(bind=self.remote_engine)
            self._cached_local_meta = local_meta
            self._cached_remote_meta = remote_meta
            self._meta_cache_time = now
        return self._cached_local_meta, self._cached_remote_meta

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
        with self._lock:
            # Force-refresh metadata on pull (schema may have changed)
            local_meta, remote_meta = self._get_metadata(force_refresh=True)

            for table_name in SYNC_TABLES:
                if table_name not in remote_meta.tables:
                    continue

                remote_table = remote_meta.tables[table_name]
                local_table = local_meta.tables.get(table_name)
                if local_table is None:
                    continue

                # Read all rows from remote
                try:
                    with self.remote_engine.connect() as rconn:
                        rows = rconn.execute(sa.select(remote_table)).fetchall()
                        columns = list(remote_table.columns.keys())
                except Exception as e:
                    log.warning(f"Failed to read remote table {table_name}: {e}")
                    continue

                # SAFE: single transaction wraps DELETE + INSERT
                # If INSERT fails mid-way, the entire transaction rolls back
                # and local data is preserved intact.
                # Note: empty rows list correctly clears local table (syncs deletions)
                try:
                    with self.local_engine.begin() as lconn:
                        lconn.execute(sa.delete(local_table))
                        for row in rows:
                            values = {}
                            for col in columns:
                                if col in local_table.columns.keys():
                                    values[col] = getattr(row, col, None)
                            if values:
                                lconn.execute(sa.insert(local_table).values(**values))
                except Exception as e:
                    log.warning(f"Failed to sync table {table_name}: {e}")
                    # Transaction rolled back automatically — local data preserved
                    continue

        # Increment version so frontend knows data changed
        self.sync_version += 1
        log.info(f"Synced {len(SYNC_TABLES)} tables from remote (v{self.sync_version})")

    def push_to_remote(self, table_name, row_id):
        """Push a single row from local to remote (called after local writes)."""
        with self._lock:
            try:
                local_meta, remote_meta = self._get_metadata()

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

# Push queue — processes pushes sequentially in a single worker thread
_push_queue = queue.Queue()
_push_thread = None
_push_thread_lock = threading.Lock()


def _push_worker():
    """Process push requests sequentially (single thread, no races)."""
    while True:
        try:
            table_name, row_id = _push_queue.get(timeout=10)
        except queue.Empty:
            continue
        if sync_manager:
            sync_manager.push_to_remote(table_name, row_id)
        _push_queue.task_done()


def push_change(table_name, row_id):
    """Queue a push for background processing (replaces thread-per-push)."""
    global _push_thread
    if not sync_manager:
        return
    # Ensure the worker thread is alive
    with _push_thread_lock:
        if _push_thread is None or not _push_thread.is_alive():
            _push_thread = threading.Thread(
                target=_push_worker, daemon=True, name="push-worker"
            )
            _push_thread.start()
    _push_queue.put((table_name, row_id))


def pull_now():
    """Force an immediate pull from remote to local."""
    if sync_manager:
        sync_manager._pull_from_remote()
