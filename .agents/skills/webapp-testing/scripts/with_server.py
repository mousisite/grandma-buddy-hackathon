#!/usr/bin/env python3
"""
Start one or more servers, wait for them to be ready, run a command, then clean up.

Usage:
    # Single server
    python scripts/with_server.py --server "npm run dev" --port 5173 -- python automation.py
    python scripts/with_server.py --server "npm start" --port 3000 -- python test.py

    # Multiple servers
    python scripts/with_server.py \
      --server "cd backend && python server.py" --port 3000 \
      --server "cd frontend && npm run dev" --port 5173 \
      -- python test.py

Original: anthropics/skills, skills/webapp-testing/scripts/with_server.py (Apache License 2.0).
Modified by the Grandma Buddy project in October 2026:
- Refuses to start if the port is already in use, so a leftover server running
  old code isn't tested by mistake.
- Sends server output to a log file instead of an unread pipe, so a server that
  prints a lot can't fill the pipe and freeze. Shows the end of the log if a
  server fails to start.
- Stops the whole server process tree. On Windows it uses taskkill, because
  stopping the shell alone leaves the real server running in the background.
"""

import argparse
import os
import signal
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

IS_WINDOWS = os.name == "nt"


def port_in_use(port):
    """Return True if something is already listening on this port."""
    try:
        with socket.create_connection(("localhost", port), timeout=1):
            return True
    except OSError:
        return False


def is_server_ready(port, timeout=30):
    """Wait for server to be ready by polling the port."""
    start_time = time.time()
    while time.time() - start_time < timeout:
        if port_in_use(port):
            return True
        time.sleep(0.5)
    return False


def start_server(cmd, log_file):
    """Start a server command in its own process group, logging to log_file."""
    kwargs = {"shell": True, "stdout": log_file, "stderr": subprocess.STDOUT}
    if IS_WINDOWS:
        kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
    else:
        kwargs["start_new_session"] = True
    return subprocess.Popen(cmd, **kwargs)


def stop_server(process):
    """Stop a server and everything it started."""
    if process.poll() is not None:
        return
    if IS_WINDOWS:
        subprocess.run(
            ["taskkill", "/PID", str(process.pid), "/T", "/F"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
    else:
        try:
            os.killpg(process.pid, signal.SIGTERM)
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            process.wait()
        except ProcessLookupError:
            pass


def show_log_tail(log_path, lines=30):
    """Print the last lines of a server log to help explain a failure."""
    try:
        text = Path(log_path).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return
    tail = text.splitlines()[-lines:]
    if tail:
        print(f"\nLast {len(tail)} lines of {log_path}:")
        print("\n".join(tail))


def main():
    parser = argparse.ArgumentParser(description="Run command with one or more servers")
    parser.add_argument("--server", action="append", dest="servers", required=True, help="Server command (can be repeated)")
    parser.add_argument("--port", action="append", dest="ports", type=int, required=True, help="Port for each server (must match --server count)")
    parser.add_argument("--timeout", type=int, default=30, help="Timeout in seconds per server (default: 30)")
    parser.add_argument("command", nargs=argparse.REMAINDER, help="Command to run after server(s) ready")

    args = parser.parse_args()

    # Remove the '--' separator if present
    if args.command and args.command[0] == "--":
        args.command = args.command[1:]

    if not args.command:
        print("Error: No command specified to run")
        sys.exit(1)

    if len(args.servers) != len(args.ports):
        print("Error: Number of --server and --port arguments must match")
        sys.exit(1)

    for port in args.ports:
        if port_in_use(port):
            print(f"Error: port {port} is already in use. Another copy of the server may still be running.")
            print("Stop it first (close its terminal), then try again.")
            sys.exit(1)

    servers = [{"cmd": cmd, "port": port} for cmd, port in zip(args.servers, args.ports)]
    running = []  # (process, log_file, log_path)

    try:
        for i, server in enumerate(servers):
            print(f"Starting server {i + 1}/{len(servers)}: {server['cmd']}")
            log_path = Path(tempfile.gettempdir()) / f"with_server_{server['port']}.log"
            log_file = open(log_path, "w", encoding="utf-8", errors="replace")
            process = start_server(server["cmd"], log_file)
            running.append((process, log_file, log_path))

            print(f"Waiting for server on port {server['port']} (log: {log_path})...")
            if not is_server_ready(server["port"], timeout=args.timeout):
                log_file.flush()
                show_log_tail(log_path)
                print(f"\nError: server failed to start on port {server['port']} within {args.timeout}s")
                sys.exit(1)

            print(f"Server ready on port {server['port']}")

        print(f"\nAll {len(servers)} server(s) ready")

        print(f"Running: {' '.join(args.command)}\n")
        result = subprocess.run(args.command)
        sys.exit(result.returncode)

    finally:
        print(f"\nStopping {len(running)} server(s)...")
        for i, (process, log_file, _log_path) in enumerate(running):
            stop_server(process)
            log_file.close()
            print(f"Server {i + 1} stopped")
        print("All servers stopped")


if __name__ == "__main__":
    main()
