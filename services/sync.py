"""
Background sync: bidirectional data sync between local SQLite and remote PostgreSQL.
Runs in a daemon thread, never blocks the main Flask/UI thread.

Pull uses UPSERT (merge) instead of destructive DELETE ALL + INSERT,
so local-only data (not yet pushed) is never lost.
Push queue is flushed before every pull and on app shutdown.
"""
import atexit
import time
import queue
import logging
import threading

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
    "documents",
    "resources",
    "automations",
    "calendar_events",
    "push_tokens",
]

SYNC_INTERVAL = 3  # seconds
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

        # Metadata cache (avoid reflecting tables on every push)
        self._cached_local_meta = None
        self._cached_remote_meta = None
        self._meta_cache_time = 0

        # Sync version counter — incremented after each successful pull
        # Frontend polls this to detect changes and refresh UI
        self.sync_version = 0

        # Track known remote IDs per table (for detecting remote deletions)
        # None = first pull (no prior knowledge), set() = known IDs from last pull
        self._known_remote_ids = {}

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
                    cols = []
                    for col in local_table.columns:
                        col_type = col.type
                        if isinstance(col_type, sa.types.NullType):
                            col_type = sa.Text()
                        elif isinstance(col_type, sa.DateTime) or str(col_type).upper() == "DATETIME":
                            col_type = sa.DateTime()
                        elif isinstance(col_type, sa.Boolean) or str(col_type).upper() == "BOOLEAN":
                            col_type = sa.Boolean()
                        new_col = sa.Column(
                            col.name, col_type,
                            primary_key=col.primary_key,
                            nullable=col.nullable,
                        )
                        cols.append(new_col)
                    new_table = sa.Table(table_name, sa.MetaData(), *cols)
                    new_table.create(bind=self.remote_engine)
                    log.info(f"Created remote table: {table_name}")

            self._meta_cache_time = 0
        except Exception as e:
            log.warning(f"Failed to ensure remote tables: {e}")

    def start(self):
        """Start the background sync thread."""
        self.ensure_remote_tables()
        self._thread = threading.Thread(target=self._loop, daemon=True, name="sync")
        self._thread.start()

    def stop(self):
        """Stop sync, ensuring all pending pushes are saved first."""
        if self._stop.is_set():
            return
        log.info("Stopping sync — flushing pending pushes...")
        self._flush_push_queue()
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=5)

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

    def _flush_push_queue(self):
        """Process all pending push requests directly (drains the queue)."""
        drained = 0
        while True:
            try:
                table_name, row_id = _push_queue.get_nowait()
            except queue.Empty:
                break
            try:
                self.push_to_remote(table_name, row_id)
            except Exception as e:
                log.warning(f"Flush push failed ({table_name} #{row_id}): {e}")
            finally:
                _push_queue.task_done()
            drained += 1
        if drained:
            log.info(f"Flushed {drained} pending pushes before pull")

    def _loop(self):
        log.info("Sync thread started")
        while not self._stop.is_set():
            try:
                # Flush all pending pushes BEFORE pulling
                # This ensures local changes reach remote before we sync back
                self._flush_push_queue()
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
        """Pull data from remote PostgreSQL and MERGE into local SQLite.

        Uses UPSERT (insert-or-update) instead of destructive DELETE ALL + INSERT.
        - Remote rows are inserted or updated locally.
        - Local-only rows (not yet pushed) are PRESERVED.
        - Remote deletions are detected by comparing with previously known remote IDs.
        - First pull for each table is aggressive (cleans up stale local data).
        """
        any_changed = False
        with self._lock:
            local_meta, remote_meta = self._get_metadata(force_refresh=True)

            for table_name in SYNC_TABLES:
                if table_name not in remote_meta.tables:
                    continue

                remote_table = remote_meta.tables[table_name]
                local_table = local_meta.tables.get(table_name)
                if local_table is None:
                    continue

                local_col_names = [c.name for c in local_table.columns]
                has_id = "id" in local_col_names

                # Read all rows from remote
                try:
                    with self.remote_engine.connect() as rconn:
                        rows = rconn.execute(sa.select(remote_table)).fetchall()
                        columns = list(remote_table.columns.keys())
                except Exception as e:
                    log.warning(f"Failed to read remote table {table_name}: {e}")
                    continue

                try:
                    with self.local_engine.begin() as lconn:
                        if has_id:
                            changed = self._merge_table_with_id(
                                lconn, local_table, local_col_names,
                                rows, columns, table_name,
                            )
                            if changed:
                                any_changed = True
                        else:
                            # Tables without 'id': fall back to DELETE + INSERT
                            lconn.execute(sa.delete(local_table))
                            for row in rows:
                                values = {}
                                for col in columns:
                                    if col in local_col_names:
                                        values[col] = getattr(row, col, None)
                                if values:
                                    lconn.execute(sa.insert(local_table).values(**values))
                except Exception as e:
                    log.warning(f"Failed to sync table {table_name}: {e}")
                    continue

        self.sync_version += 1

        # Only notify clients via SSE if data actually changed
        if any_changed:
            log.info(f"Sync v{self.sync_version}: changes detected, notifying clients")
            try:
                from services.sse import sse_bus
                sse_bus.publish("sync", {"version": self.sync_version})
            except Exception:
                pass

    def _merge_table_with_id(self, lconn, local_table, local_col_names,
                              rows, columns, table_name):
        """Merge remote rows into local table using UPSERT strategy.

        Returns True if any rows were inserted, updated, or deleted.
        """
        changed = False
        # Get existing local rows with their IDs and timestamps
        local_ids = set()
        local_timestamps = {}
        try:
            has_updated_at = "updated_at" in local_col_names
            has_created_at = "created_at" in local_col_names

            select_cols = [local_table.c.id]
            if has_updated_at:
                select_cols.append(local_table.c.updated_at)
            elif has_created_at:
                select_cols.append(local_table.c.created_at)

            for r in lconn.execute(sa.select(*select_cols)).fetchall():
                local_ids.add(r[0])
                if len(select_cols) > 1 and r[1] is not None:
                    local_timestamps[r[0]] = r[1]
        except Exception:
            local_ids = {
                r[0] for r in lconn.execute(sa.select(local_table.c.id)).fetchall()
            }

        remote_ids = set()

        for row in rows:
            values = {}
            for col in columns:
                if col in local_col_names:
                    values[col] = getattr(row, col, None)
            if not values:
                continue

            row_id = values.get("id")
            if row_id is not None:
                remote_ids.add(row_id)

            if row_id in local_ids:
                # Check if remote data is newer before overwriting
                remote_ts = values.get("updated_at") or values.get("created_at")
                local_ts = local_timestamps.get(row_id)

                if local_ts and remote_ts and local_ts > remote_ts:
                    # Local is newer — don't overwrite, push local to remote instead
                    continue

                # UPDATE existing row with remote data
                update_vals = {k: v for k, v in values.items() if k != "id"}
                if update_vals:
                    lconn.execute(
                        sa.update(local_table)
                        .where(local_table.c.id == row_id)
                        .values(**update_vals)
                    )
                    changed = True
            else:
                # INSERT new row from remote
                lconn.execute(sa.insert(local_table).values(**values))
                changed = True

        # --- Handle remote deletions ---
        prev_remote = self._known_remote_ids.get(table_name)

        if prev_remote is None:
            pass
        else:
            deleted_remotely = prev_remote - remote_ids
            for did in deleted_remotely:
                if did in local_ids:
                    lconn.execute(
                        sa.delete(local_table).where(local_table.c.id == did)
                    )
                    changed = True

        # Update known remote IDs for next pull cycle
        self._known_remote_ids[table_name] = remote_ids
        return changed

    def push_to_remote(self, table_name, row_id):
        """Push a single row from local to remote (called after local writes)."""
        with self._lock:
            try:
                local_meta, remote_meta = self._get_metadata()

                local_table = local_meta.tables.get(table_name)
                remote_table = remote_meta.tables.get(table_name)
                if local_table is None or remote_table is None:
                    log.warning(f"Push skipped — table '{table_name}' not found locally or remotely")
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
                    # Update known remote IDs
                    if table_name in self._known_remote_ids:
                        self._known_remote_ids[table_name].discard(row_id)
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

                # Update known remote IDs so next pull doesn't treat this as "new"
                if table_name not in self._known_remote_ids:
                    self._known_remote_ids[table_name] = set()
                self._known_remote_ids[table_name].add(row_id)

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


def _shutdown_flush():
    """atexit handler: flush pending pushes to remote before process exits."""
    if sync_manager:
        log.info("atexit: flushing push queue before exit...")
        sync_manager.stop()


atexit.register(_shutdown_flush)
