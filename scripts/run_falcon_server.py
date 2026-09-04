#!/usr/bin/env python3
"""
High-Performance Falcon API Server Launcher.

Supports multi-worker execution with tuned thread pools for Granian (Rust Hyper WSGI)
and Gunicorn (gthread), along with SQLite WAL read-only concurrency optimization.

Usage:
    python scripts/run_falcon_server.py --engine granian --workers 4 --threads 8 --port 8000
    python scripts/run_falcon_server.py --engine gunicorn --workers 4 --threads 8 --port 8000
"""

from __future__ import annotations

import argparse
import importlib.util
import os
from pathlib import Path
import signal
import sqlite3
import subprocess
import sys
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

DEFAULT_SQLITE_DB = REPO_ROOT / "InflationItems" / "prices.db"

# Single source of truth for the read-optimized SQLite pragmas: the adapter
# (inflation_dashboard/adapters/sqlite_price_repository.py) defines the
# defaults and env-var overrides; this launcher only mirrors them so worker
# processes inherit exactly what the repository applies.
from inflation_dashboard.adapters import sqlite_price_repository  # noqa: E402
from inflation_dashboard.adapters.sqlite_price_repository import pragma_values  # noqa: E402


def check_installed(module_name: str) -> bool:
    """Return True if a python module is importable in current environment."""
    return importlib.util.find_spec(module_name) is not None


def tune_sqlite_for_concurrency(db_path: Path, read_only: bool = True) -> dict[str, Any]:
    """
    Verify and configure SQLite database for high-concurrency read-only access.

    Enables Write-Ahead Logging (WAL) mode, normal synchronous durability,
    sets busy timeout, memory-mapped I/O, and exports environment variables
    so all server workers operate in optimized read-only mode without lock contention.
    """
    values = pragma_values()
    info: dict[str, Any] = {
        "db_path": str(db_path),
        "exists": db_path.is_file(),
        "wal_enabled": False,
        "mmap_size_mb": values["mmap_size"] // (1024 * 1024),
        "busy_timeout_ms": values["busy_timeout"],
        "read_only": read_only,
    }

    if db_path.is_file():
        try:
            conn = sqlite3.connect(str(db_path), timeout=2.0)
            cursor = conn.cursor()

            # Check journal mode without exclusive lock if already WAL
            cursor.execute("PRAGMA journal_mode;")
            row = cursor.fetchone()
            current_mode = str(row[0]).lower() if row else "unknown"

            if current_mode != "wal":
                cursor.execute("PRAGMA journal_mode = WAL;")
                row = cursor.fetchone()
                current_mode = str(row[0]).lower() if row else current_mode

            info["wal_enabled"] = (current_mode == "wal")
            cursor.execute("PRAGMA synchronous = NORMAL;")
            cursor.execute(f"PRAGMA busy_timeout = {values['busy_timeout']};")
            conn.close()
        except Exception as exc:
            info["warning"] = f"Failed to tune SQLite database: {exc}"

    # Set process environment variables for worker inheritance
    os.environ["SQLITE_DB_PATH"] = str(db_path)
    os.environ["SQLITE_READ_ONLY"] = "1" if read_only else "0"
    os.environ["SQLITE_JOURNAL_MODE"] = "WAL"
    os.environ["SQLITE_SYNCHRONOUS"] = "NORMAL"
    os.environ["SQLITE_BUSY_TIMEOUT"] = str(values["busy_timeout"])
    os.environ["SQLITE_MMAP_SIZE"] = str(values["mmap_size"])
    os.environ["SQLITE_CACHE_SIZE"] = str(values["cache_size"])
    os.environ["SQLITE_URI"] = f"file:{db_path.resolve()}?mode=ro"

    return info


def get_readonly_sqlite_connection(db_path: Path | str | None = None) -> sqlite3.Connection:
    """Return an optimized read-only SQLite connection for application adapters.

    Delegates to the adapter's thread-local reusable reader (one connection per
    worker thread, reused across requests), which applies the same effective
    pragma set. The explicit ``db_path`` branch keeps a fresh-connection option
    for tooling; request-serving paths should use the reusable connection.
    """
    if db_path is None:
        return sqlite_price_repository.get_reusable_connection()
    return sqlite_price_repository.get_db_connection(read_only=True)


def build_command(
    engine: str,
    host: str,
    port: int,
    workers: int,
    threads: int,
    backlog: int,
    log_level: str,
    interface: str = "wsgi",
) -> list[str]:
    """Construct command arguments for the specified WSGI server engine."""
    if interface == "asgi":
        # High-scale ASGI entry point (falcon.asgi.App; scaling refactor).
        # Granian and uvicorn both speak ASGI natively.
        app_target = "inflation_dashboard.api.asgi_app:create_asgi_app"
    else:
        app_target = "inflation_dashboard.api.falcon_app:create_app"

    if interface == "asgi" and engine in ("gunicorn", "waitress"):
        raise ValueError(
            f"Engine '{engine}' is WSGI-only; use --interface asgi with "
            "--engine uvicorn or --engine granian."
        )

    if engine == "granian":
        cmd = [
            sys.executable,
            "-m",
            "granian",
            "--interface",
            interface,
            "--host",
            host,
            "--port",
            str(port),
            "--workers",
            str(workers),
            "--blocking-threads",
            str(threads),
            "--backlog",
            str(backlog),
            "--log-level",
            log_level,
            "--factory",
            app_target,
        ]
    elif engine == "gunicorn":
        cmd = [
            sys.executable,
            "-m",
            "gunicorn",
            "-k",
            "gthread",
            "--workers",
            str(workers),
            "--threads",
            str(threads),
            "--backlog",
            str(backlog),
            "--log-level",
            log_level,
            "-b",
            f"{host}:{port}",
            f"{app_target}()",
        ]
    elif engine == "waitress":
        # Waitress treats the positional argument as the WSGI app itself; a
        # module:factory reference must be marked with --call or waitress will
        # invoke create_app() as a WSGI application and every request 500s.
        cmd = [
            sys.executable,
            "-m",
            "waitress",
            "--call",
            f"--listen={host}:{port}",
            f"--threads={workers * threads}",
            "--backlog",
            str(backlog),
            app_target,
        ]
    elif engine == "uvicorn":
        # Uvicorn is an ASGI server; a WSGI app must be run through its native
        # (deprecated but functional) --interface wsgi path, or wrapped with
        # a2wsgi. Without the interface flag, Falcon's WSGI app is driven as
        # ASGI and every request 500s.
        uvicorn_interface = "asgi3" if interface == "asgi" else interface
        cmd = [
            sys.executable,
            "-m",
            "uvicorn",
            "--interface",
            uvicorn_interface,
            "--host",
            host,
            "--port",
            str(port),
            "--workers",
            str(workers),
            "--factory",
            app_target,
        ]
    else:
        raise ValueError(f"Unsupported engine: {engine}")

    return cmd


def print_banner(
    engine: str,
    host: str,
    port: int,
    workers: int,
    threads: int,
    backlog: int,
    cors_origins: str,
    sqlite_info: dict[str, Any],
    interface: str = "wsgi",
) -> None:
    """Print high-performance server startup banner."""
    total_slots = workers * threads if engine in ("granian", "gunicorn") else threads
    sep = "=" * 70
    print(sep)
    print("   Falcon API Production Concurrency Server Launcher")
    print(sep)
    print(f"   Server Engine       : {engine.upper()}")
    print(f"   App Interface       : {interface.upper()}")
    print(f"   Listen Address      : http://{host}:{port}")
    print(f"   Worker Processes    : {workers}")
    print(f"   Threads per Worker  : {threads}")
    print(f"   Concurrent Slots    : {total_slots} execution threads")
    print(f"   Connection Backlog  : {backlog} queued sockets")
    print(f"   CORS Allowed Origins: {cors_origins}")
    if sqlite_info["exists"]:
        print(f"   SQLite Database     : {sqlite_info['db_path']} (WAL={sqlite_info['wal_enabled']}, RO=Active)")
    else:
        print(f"   SQLite Database     : {sqlite_info['db_path']} (Not found, CSV fallback)")
    print(sep)
    print("   Press Ctrl+C to terminate gracefully.")
    print(sep, flush=True)


def main() -> int:
    default_workers = max(1, min(os.cpu_count() or 4, 8))

    parser = argparse.ArgumentParser(
        description="Launch Falcon API with production-grade multi-worker concurrency."
    )
    parser.add_argument(
        "--interface",
        choices=["wsgi", "asgi"],
        default=os.getenv("FALCON_INTERFACE", "wsgi"),
        help="App interface: wsgi (falcon_app.create_app) or asgi (asgi_app.create_asgi_app).",
    )
    parser.add_argument(
        "--engine",
        choices=["granian", "gunicorn", "waitress", "uvicorn"],
        default="granian",
        help="WSGI server engine to use (default: granian).",
    )
    parser.add_argument(
        "--host",
        default=os.getenv("HOST", "127.0.0.1"),
        help="Host address to bind to (default: 127.0.0.1).",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.getenv("PORT", "8000")),
        help="Port to listen on (default: 8000).",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=int(os.getenv("WEB_CONCURRENCY", default_workers)),
        help=f"Number of worker processes (default: {default_workers}).",
    )
    parser.add_argument(
        "--threads",
        type=int,
        default=int(os.getenv("SERVER_THREADS", "8")),
        help="Thread pool size per worker process (default: 8).",
    )
    parser.add_argument(
        "--backlog",
        type=int,
        default=int(os.getenv("SERVER_BACKLOG", "2048")),
        help="Connection backlog size (default: 2048).",
    )
    parser.add_argument(
        "--cors-origins",
        default=os.getenv("FALCON_CORS_ORIGINS", "*"),
        help="Allowed CORS origins, comma-separated (default: *).",
    )
    parser.add_argument(
        "--sqlite-db",
        default=str(DEFAULT_SQLITE_DB),
        help=f"Path to SQLite database file (default: {DEFAULT_SQLITE_DB}).",
    )
    parser.add_argument(
        "--no-sqlite-readonly",
        action="store_true",
        help="Disable SQLite WAL read-only tuning.",
    )
    parser.add_argument(
        "--log-level",
        choices=["critical", "error", "warning", "warn", "info", "debug"],
        default="info",
        help="Server log level (default: info).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print server command without executing.",
    )

    args = parser.parse_args()

    # Engine selection and fallback
    chosen_engine = args.engine
    if not check_installed(chosen_engine):
        if chosen_engine == "granian" and check_installed("gunicorn"):
            print(f"[WARN] Engine '{chosen_engine}' not found, falling back to 'gunicorn'.", file=sys.stderr)
            chosen_engine = "gunicorn"
        elif chosen_engine == "gunicorn" and check_installed("granian"):
            print(f"[WARN] Engine '{chosen_engine}' not found, falling back to 'granian'.", file=sys.stderr)
            chosen_engine = "granian"
        else:
            print(f"[ERROR] Selected engine '{chosen_engine}' is not installed in current environment.", file=sys.stderr)
            return 1

    # SQLite read-only concurrency configuration
    sqlite_path = Path(args.sqlite_db).resolve()
    sqlite_info = tune_sqlite_for_concurrency(
        sqlite_path,
        read_only=not args.no_sqlite_readonly,
    )

    # Set CORS environment variable
    os.environ["FALCON_CORS_ORIGINS"] = args.cors_origins
    # Ensure project root is in PYTHONPATH
    pythonpath = os.getenv("PYTHONPATH", "")
    if str(REPO_ROOT) not in pythonpath.split(os.pathsep):
        os.environ["PYTHONPATH"] = f"{REPO_ROOT}{os.pathsep}{pythonpath}" if pythonpath else str(REPO_ROOT)

    cmd = build_command(
        engine=chosen_engine,
        host=args.host,
        port=args.port,
        workers=args.workers,
        threads=args.threads,
        backlog=args.backlog,
        log_level=args.log_level,
        interface=args.interface,
    )

    if args.dry_run:
        print_banner(
            engine=chosen_engine,
            host=args.host,
            port=args.port,
            workers=args.workers,
            threads=args.threads,
            backlog=args.backlog,
            cors_origins=args.cors_origins,
            sqlite_info=sqlite_info,
            interface=args.interface,
        )
        print("Dry run command:", " ".join(cmd))
        return 0

    print_banner(
        engine=chosen_engine,
        host=args.host,
        port=args.port,
        workers=args.workers,
        threads=args.threads,
        backlog=args.backlog,
        cors_origins=args.cors_origins,
        sqlite_info=sqlite_info,
    )

    # Execute server process directly replacing current process
    try:
        os.execvp(cmd[0], cmd)
    except Exception as exc:
        print(f"[ERROR] Failed to execute {cmd[0]}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
