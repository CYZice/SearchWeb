#!/usr/bin/env python
"""Stop the inscription retrieval system server"""
import subprocess
import sys
import time

PORT = 8000

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
        print(f"Error: {e}")
    return pids

def main():
    print(f"Finding processes on port {PORT}...")
    pids = get_port_pids(PORT)

    if not pids:
        print(f"No processes found on port {PORT}")
        sys.exit(0)

    print(f"Found: {pids}")
    for pid in pids:
        try:
            print(f"Killing PID {pid}...")
            subprocess.run(['taskkill', '/F', '/PID', str(pid)], check=True)
        except Exception as e:
            print(f"Failed to kill {pid}: {e}")

    # Verify
    time.sleep(1)
    remaining = get_port_pids(PORT)
    if remaining:
        print(f"Warning: Still running: {remaining}")
        sys.exit(1)
    else:
        print(f"Port {PORT} is now free")
        sys.exit(0)

if __name__ == '__main__':
    main()