#!/usr/bin/env python
"""Start the inscription retrieval system server"""
import subprocess
import socket
import time
import sys
import os

PORT = 8000
HOST = "127.0.0.1"

def get_port_pids(port):
    pids = set()
    try:
        result = subprocess.run(['netstat', '-ano'], capture_output=True, text=True, encoding='utf-8', errors='replace')
        for line in result.stdout.split('\n'):
            if f':{port}' in line and 'LISTENING' in line:
                parts = line.split()
                if len(parts) >= 5:
                    pid = parts[-1]
                    if pid and pid != '0':
                        pids.add(int(pid))
    except Exception as e:
        print(f"Error checking port: {e}")
    return pids

def kill_pids(pids):
    for pid in pids:
        try:
            print(f"Killing PID {pid}...")
            subprocess.run(['taskkill', '//F', '//PID', str(pid)], capture_output=True, timeout=5)
        except Exception as e:
            print(f"Failed to kill {pid}: {e}")

def check_port_free(port):
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.bind((HOST, port))
        sock.close()
        return True
    except OSError:
        return False

def main():
    dir_path = os.path.dirname(os.path.abspath(__file__))

    print(f"Checking port {PORT}...")
    pids = get_port_pids(PORT)

    if pids:
        print(f"Found processes: {pids}")
        kill_pids(pids)
        time.sleep(2)

        remaining = get_port_pids(PORT)
        if remaining:
            print(f"Still running: {remaining}")
            kill_pids(remaining)
            time.sleep(2)

    final = get_port_pids(PORT)
    if final:
        print(f"Warning: Cannot clean: {final}")
        if not check_port_free(PORT):
            print("Port still in use, waiting 30s...")
            time.sleep(30)

    if not check_port_free(PORT):
        print("Port not free, exiting")
        sys.exit(1)

    print(f"Starting server on {HOST}:{PORT}...")
    os.chdir(dir_path)

    server = subprocess.Popen(
        ['uvicorn', 'app.main:app', '--host', HOST, '--port', str(PORT)],
        stdout=sys.stdout,
        stderr=subprocess.STDOUT
    )

    try:
        server.wait()
    except KeyboardInterrupt:
        print("\nShutting down...")
        server.terminate()
        server.wait()
        print("Server stopped")

if __name__ == '__main__':
    main()