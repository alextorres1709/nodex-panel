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
    "task_comments",
    "subtasks",
    "ideas",
    "credentials",
    "activity_log",
    "messages",
    "call_sessions",
    "leads",
    "lead_interactions",
    "clients",
    "notifications",
    "time_entries",
    "invoices",
    "documents",
    "resources",
    "automations",
    "calendar_events",
    "push_tokens",
    "objectives",
    "objective_snapshots",
    "project_templates",
    "project_template_tasks",
    "email_templates",
    "company_interactions",
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
        # RLock so Flask routes can hold the lock while also calling
        # push_change() (which re-acquires the lock in the same thread).
        self._lock = threading.RLock()

        # Metadata cache (avoid reflecting tables on every push)
        self._cached_local_meta = None
        self._cached_remote_meta = None
        self._meta_cache_time = 0

        # Sync version counter — incremented after each successful pull
        # Frontend polls this to detect changes and refresh UI
        self.sync_version = 0

        # Sync status (for /api/sync/status endpoint + header indicator)
        self.last_sync_at = None  # datetime of last successful sync
        self.last_error = None    # last error string
        self.is_syncing = False   # True while pull/push is running

        # Track known remote IDs per table (for detecting remote deletions)
        # None = first pull (no prior knowledge), set() = known IDs from last pull
        self._known_remote_ids = {}

        # IDs that were just push-deleted to remote, kept for one pull cycle
        # so the next merge phase skips them. Without this, a pull that
        # entered Phase 1 (network fetch, no lock) BEFORE the delete
        # would re-insert the row from its stale snapshot in Phase 2.
        # Maps table_name -> set of deleted ids.
        self._recently_deleted = {}
        self._recently_deleted_lock = threading.Lock()

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
        # NOTE: FK migration runs inside _loop() on the first iteration
        # (not here) because it does 20+ ALTER TABLE round-trips against
        # remote PG and would block app startup for ~1 minute otherwise.
        self._thread = threading.Thread(target=self._loop, daemon=True, name="sync")
        self._thread.start()

    def stop(self):
        """Stop sync, ensuring all pending pushes are saved first."""
        if self._stop.is_set():
            return
        log.info("Stopping sync — flushing pending pushes...")
        # Wait briefly for any pushes the worker is currently processing
        # (they hold the RLock, so we can't grab it while they're in-flight).
        try:
            _push_queue.join()
        except Exception:
            pass
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
        fk_migrated = False
        while not self._stop.is_set():
            try:
                self.is_syncing = True
                # Flush all pending pushes BEFORE pulling
                # This ensures local changes reach remote before we sync back
                self._flush_push_queue()
                self._pull_from_remote()
                self.last_sync_at = datetime.now(timezone.utc)
                self.last_error = None
                if not self._first_sync_done.is_set():
                    self._first_sync_done.set()
                    log.info("First sync complete")
                # Run FK migration AFTER first sync so app startup isn't
                # blocked waiting for ~20 remote ALTER TABLEs.
                if not fk_migrated:
                    try:
                        migrate_pg_fk_ondelete(self.remote_engine)
                    except Exception as e:
                        log.warning(f"FK migration failed: {e}")
                    fk_migrated = True
            except Exception as e:
                log.warning(f"Sync error: {e}")
                self.last_error = str(e)[:200]
                if not self._first_sync_done.is_set():
                    self._first_sync_done.set()  # Don't block startup on failure
            finally:
                self.is_syncing = False
            self._stop.wait(SYNC_INTERVAL)

    def _pull_from_remote(self):
        """Pull data from remote PostgreSQL and MERGE into local SQLite.

        Two-phase to keep the sync lock held only during the (fast) local
        merge, not during the (slow, network-bound) remote fetch:

        1. FETCH remote rows for every table WITHOUT holding the lock.
           This is the slow part (1-2 s of network I/O for a full pull).
        2. MERGE into local SQLite under the lock — purely local writes,
           typically <100 ms.

        Before the merge phase we re-flush the push queue, so any local
        writes that happened during the fetch get pushed before we merge
        the (possibly stale) remote snapshot back over them.

        Uses UPSERT (insert-or-update) instead of destructive DELETE ALL + INSERT.
        - Remote rows are inserted or updated locally.
        - Local-only rows (not yet pushed) are PRESERVED.
        - Remote deletions are detected by comparing with previously known remote IDs.
        - First pull for each table is aggressive (cleans up stale local data).
        """
        # Refresh metadata snapshot (no lock needed — read-only reflection)
        local_meta, remote_meta = self._get_metadata(force_refresh=True)

        # ── PHASE 1: Fetch all remote tables WITHOUT holding the lock ──
        fetched = {}
        for table_name in SYNC_TABLES:
            if table_name not in remote_meta.tables:
                continue
            remote_table = remote_meta.tables[table_name]
            try:
                with self.remote_engine.connect() as rconn:
                    rows = rconn.execute(sa.select(remote_table)).fetchall()
                    columns = list(remote_table.columns.keys())
                fetched[table_name] = (rows, columns)
            except Exception as e:
                log.warning(f"Failed to read remote table {table_name}: {e}")
                continue

        # ── PHASE 2: Merge into local SQLite WITH the lock held briefly ──
        any_changed = False
        with self._lock:
            # Drain any pushes that landed during phase 1 BEFORE we merge,
            # otherwise the merge would overwrite local writes with stale
            # remote snapshot data.
            self._flush_push_queue()

            for table_name, (rows, columns) in fetched.items():
                local_table = local_meta.tables.get(table_name)
                if local_table is None:
                    continue
                local_col_names = [c.name for c in local_table.columns]
                has_id = "id" in local_col_names

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

        # Snapshot of rows that were push-deleted since the last merge.
        # We pop them so they only suppress this one merge cycle — by the
        # next pull the remote fetch will reflect the deletion naturally.
        with self._recently_deleted_lock:
            skip_ids = self._recently_deleted.pop(table_name, set())

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
                if row_id in skip_ids:
                    # We just push-deleted this row to remote, but the
                    # Phase-1 fetch happened before the delete landed and
                    # so still includes it. Skip it entirely so we don't
                    # re-insert it locally and don't add it to remote_ids
                    # (which would otherwise survive into the next pull
                    # cycle and trigger a spurious "remote delete").
                    continue
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
        """Push a single row from local to remote (called after local writes).

        Optimized to minimize round-trips:
        - Reads local row outside the sync lock.
        - For deletes: 1 statement (DELETE WHERE id=?).
        - For upserts: 1 statement on PostgreSQL (INSERT … ON CONFLICT … DO UPDATE),
          falling back to SELECT-then-decide for other backends.
        """
        try:
            local_meta, remote_meta = self._get_metadata()
            local_table = local_meta.tables.get(table_name)
            remote_table = remote_meta.tables.get(table_name)
            if local_table is None or remote_table is None:
                log.warning(f"Push skipped — table '{table_name}' not found locally or remotely")
                return

            # Read the row from local (no sync lock needed — local SQLite is fast)
            with self.local_engine.connect() as lconn:
                row = lconn.execute(
                    sa.select(local_table).where(local_table.c.id == row_id)
                ).fetchone()

            if row is None:
                # Row was deleted locally — delete from remote in one statement.
                # Mark as recently deleted *before* the SQL so even if the
                # remote DELETE fails, the next merge still skips re-inserting
                # it.
                with self._recently_deleted_lock:
                    self._recently_deleted.setdefault(table_name, set()).add(row_id)

                def _do_remote_delete():
                    with self.remote_engine.begin() as rconn:
                        rconn.execute(
                            sa.delete(remote_table).where(remote_table.c.id == row_id)
                        )

                try:
                    _do_remote_delete()
                except Exception as del_err:
                    # Most likely an FK constraint without ON DELETE CASCADE.
                    # Run the FK migration on the spot and retry once. This
                    # makes the FIRST delete succeed even if the background
                    # FK migration hasn't finished yet.
                    msg = str(del_err).lower()
                    if "foreign key" in msg or "violates" in msg or "constraint" in msg:
                        log.warning(
                            f"Remote DELETE for {table_name} #{row_id} hit FK "
                            f"violation — running FK migration and retrying"
                        )
                        try:
                            migrate_pg_fk_ondelete(self.remote_engine)
                        except Exception as mig_err:
                            log.error(f"FK migration failed: {mig_err}")
                        try:
                            _do_remote_delete()
                        except Exception as retry_err:
                            log.error(
                                f"Remote DELETE retry failed for {table_name} "
                                f"#{row_id}: {retry_err}"
                            )
                            raise
                    else:
                        log.error(
                            f"Remote DELETE failed for {table_name} #{row_id}: "
                            f"{del_err}"
                        )
                        raise
                if table_name in self._known_remote_ids:
                    self._known_remote_ids[table_name].discard(row_id)
                return

            # Build values dict (columns present in both schemas)
            remote_col_names = set(remote_table.columns.keys())
            values = {}
            for col in local_table.columns.keys():
                if col in remote_col_names:
                    values[col] = getattr(row, col, None)

            # Single-statement UPSERT for PostgreSQL — saves a round-trip
            with self.remote_engine.begin() as rconn:
                if rconn.dialect.name == "postgresql":
                    from sqlalchemy.dialects.postgresql import insert as pg_insert
                    stmt = pg_insert(remote_table).values(**values)
                    update_cols = {c: stmt.excluded[c] for c in values if c != "id"}
                    if update_cols:
                        stmt = stmt.on_conflict_do_update(
                            index_elements=["id"], set_=update_cols
                        )
                    else:
                        stmt = stmt.on_conflict_do_nothing(index_elements=["id"])
                    rconn.execute(stmt)
                else:
                    # Fallback: SELECT-then-decide (used in HOSTED_MODE tests)
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

            if table_name not in self._known_remote_ids:
                self._known_remote_ids[table_name] = set()
            self._known_remote_ids[table_name].add(row_id)

        except Exception as e:
            log.warning(f"Push to remote failed ({table_name} #{row_id}): {e}")


def migrate_pg_fk_ondelete(engine):
    """Alter all FK constraints on a PostgreSQL engine so deletes cascade.

    For each FK constraint with ON DELETE NO ACTION / RESTRICT:
    - If the local column is NOT NULL → ON DELETE CASCADE
      (the child row is "owned" by the parent)
    - If the local column is nullable → ON DELETE SET NULL
      (the child row outlives the parent, just loses the link)

    This is the root cause of the "deleted item comes back after a few
    seconds" bug: SQLAlchemy ORM cascades children locally, but
    push_to_remote only pushes the parent delete, so PostgreSQL refuses
    it (FK violation from orphaned children) and the row stays in
    remote — the next pull then re-inserts it locally.

    Idempotent: skips constraints already configured with CASCADE/SET NULL.
    """
    if engine is None or engine.dialect.name != "postgresql":
        return
    try:
        inspector = sa.inspect(engine)
        with engine.connect() as conn:
            for table_name in inspector.get_table_names():
                try:
                    cols = {c["name"]: c for c in inspector.get_columns(table_name)}
                    fks = inspector.get_foreign_keys(table_name)
                except Exception:
                    continue
                for fk in fks:
                    constraint_name = fk.get("name")
                    referred_table = fk.get("referred_table")
                    local_cols = fk.get("constrained_columns") or []
                    referred_cols = fk.get("referred_columns") or []
                    if not (constraint_name and referred_table and local_cols and referred_cols):
                        continue
                    options = fk.get("options") or {}
                    current_action = (options.get("ondelete") or "").upper()
                    if current_action in ("CASCADE", "SET NULL"):
                        continue
                    nullable = cols.get(local_cols[0], {}).get("nullable", True)
                    action = "SET NULL" if nullable else "CASCADE"
                    cols_csv = ", ".join(f'"{c}"' for c in local_cols)
                    refs_csv = ", ".join(f'"{c}"' for c in referred_cols)
                    try:
                        conn.execute(sa.text(
                            f'ALTER TABLE "{table_name}" '
                            f'DROP CONSTRAINT IF EXISTS "{constraint_name}"'
                        ))
                        conn.execute(sa.text(
                            f'ALTER TABLE "{table_name}" '
                            f'ADD CONSTRAINT "{constraint_name}" '
                            f'FOREIGN KEY ({cols_csv}) '
                            f'REFERENCES "{referred_table}" ({refs_csv}) '
                            f'ON DELETE {action}'
                        ))
                        conn.commit()
                        log.info(
                            f"FK migration: {table_name}.{local_cols[0]} → "
                            f"{referred_table} (ON DELETE {action})"
                        )
                    except Exception as e:
                        try:
                            conn.rollback()
                        except Exception:
                            pass
                        log.warning(
                            f"FK migration failed for {table_name}.{constraint_name}: {e}"
                        )
    except Exception as e:
        log.warning(f"FK migration scan failed: {e}")


# Global sync manager instance (set in app.py)
sync_manager = None

# Push queue — processes pushes sequentially in a single worker thread so
# that Flask request handlers can return immediately instead of blocking
# on the sync lock (which the background pull thread holds for 1-3 s per
# cycle). Without this, a form submit during a pull freezes the pywebview
# WebView for seconds and users end up triple-submitting.
_push_queue = queue.Queue()
_push_thread = None
_push_thread_lock = threading.Lock()


def _push_worker():
    """Process push requests sequentially (single thread, no races)."""
    while True:
        try:
            item = _push_queue.get()
        except Exception:
            continue
        if item is None:  # poison pill (not currently used)
            _push_queue.task_done()
            break
        table_name, row_id = item
        try:
            if sync_manager:
                sync_manager.push_to_remote(table_name, row_id)
        except Exception as e:
            log.warning(f"Async push failed ({table_name} #{row_id}): {e}")
        finally:
            _push_queue.task_done()


def _ensure_push_worker():
    """Lazily start the push worker thread on first use."""
    global _push_thread
    with _push_thread_lock:
        if _push_thread is None or not _push_thread.is_alive():
            _push_thread = threading.Thread(
                target=_push_worker, daemon=True, name="sync-push",
            )
            _push_thread.start()


def push_change(table_name, row_id):
    """Enqueue a push to remote. Returns immediately.

    The push runs in a dedicated worker thread so the Flask request can
    return a redirect to the WebView without waiting on the remote
    database. Ordering is preserved per-table via the FIFO queue, and the
    background sync thread flushes the queue before every pull, so no
    local change is ever lost.

    For operations where the push MUST complete before the HTTP response
    (e.g. deletes that race against a concurrent pull), use
    push_change_now() inside a sync_locked() block instead.
    """
    if not sync_manager:
        return
    _ensure_push_worker()
    _push_queue.put((table_name, row_id))


def push_change_now(table_name, row_id):
    """Push synchronously in the current thread.

    Only use this inside a sync_locked() block when you need the push to
    complete before the HTTP response returns (e.g. the delete path where
    the next sync pull could otherwise re-insert the row).
    """
    if not sync_manager:
        return
    try:
        sync_manager.push_to_remote(table_name, row_id)
    except Exception as e:
        log.warning(f"Synchronous push failed ({table_name} #{row_id}): {e}")


class _NullContext:
    def __enter__(self):
        return self
    def __exit__(self, *a):
        return False


def sync_locked():
    """Context manager that holds the sync lock, preventing the background
    sync thread from running a pull while the caller performs a critical
    local mutation + push.

    Use this around delete operations to prevent the sync pull from
    re-inserting the row between the local delete and the remote push.
    """
    if sync_manager:
        return sync_manager._lock
    return _NullContext()


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
