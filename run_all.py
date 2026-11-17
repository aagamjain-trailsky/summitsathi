import subprocess
import sys
import os
import time
import signal
from pathlib import Path

BASE_DIR = Path(__file__).parent

SERVICES = [
    {
        "name":    "Simulator",
        "module":  "simulator.satellite_sim",
        "colour":  "\033[36m",   # cyan
    },
    {
        "name":    "Alert Engine",
        "module":  "pipeline.alert_engine",
        "colour":  "\033[33m",   # yellow
    },
    {
        "name":    "UI Server",
        "module":  "ui.server",
        "colour":  "\033[35m",   # magenta
    },
]

RESET  = "\033[0m"
GREEN  = "\033[32m"
RED    = "\033[31m"
BOLD   = "\033[1m"

processes = []

def banner():
    print(f"""
{BOLD}
  ████████╗██████╗  █████╗ ██╗██╗      ███████╗██╗  ██╗██╗   ██╗
     ██╔══╝██╔══██╗██╔══██╗██║██║      ██╔════╝██║ ██╔╝╚██╗ ██╔╝
     ██║   ██████╔╝███████║██║██║      ███████╗█████╔╝  ╚████╔╝ 
     ██║   ██╔══██╗██╔══██║██║██║      ╚════██║██╔═██╗   ╚██╔╝  
     ██║   ██║  ██║██║  ██║██║███████╗ ███████║██║  ██╗   ██║   
     ╚═╝   ╚═╝  ╚═╝╚═╝  ╚═╝╚═╝╚══════╝╚══════╝╚═╝  ╚═╝   ╚═╝   
{RESET}
  Portable Weather Satellite Receiver — Development Mode
  ─────────────────────────────────────────────────────
""")

def start_service(service: dict) -> subprocess.Popen:
    col  = service["colour"]
    name = service["name"]
    print(f"  {col}▶ Starting {name}...{RESET}")
    proc = subprocess.Popen(
        [sys.executable, "-m", service["module"]],
        cwd=str(BASE_DIR),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1
    )
    return proc

def stream_output(proc, name, colour):
    import threading
    def _read():
        for line in proc.stdout:
            line = line.rstrip()
            if line:
                print(f"  {colour}[{name}]{RESET} {line}")
    t = threading.Thread(target=_read, daemon=True)
    t.start()
    return t

def shutdown(sig=None, frame=None):
    print(f"\n\n  {RED}Shutting down TrailSky...{RESET}")
    for p in processes:
        try:
            p.terminate()
        except Exception:
            pass
    time.sleep(1)
    for p in processes:
        try:
            p.kill()
        except Exception:
            pass
    print(f"  {GREEN}All services stopped.{RESET}\n")
    sys.exit(0)

def main():
    banner()

    signal.signal(signal.SIGINT,  shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    print(f"  {BOLD}Starting all services:{RESET}\n")

    for service in SERVICES:
        proc = start_service(service)
        processes.append(proc)
        stream_output(proc, service["name"], service["colour"])
        time.sleep(1.5)

    print(f"""
  {GREEN}✓ All services running{RESET}

  {BOLD}Dashboard:{RESET}  http://127.0.0.1:5000
  {BOLD}Stop:{RESET}       Ctrl + C

  ─────────────────────────────────────────────────────
""")

    # Monitor — restart any service that crashes
    while True:
        for i, proc in enumerate(processes):
            if proc.poll() is not None:
                name = SERVICES[i]["name"]
                print(f"\n  {RED}[WATCHDOG] {name} crashed — restarting...{RESET}")
                new_proc = start_service(SERVICES[i])
                stream_output(new_proc, name, SERVICES[i]["colour"])
                processes[i] = new_proc
        time.sleep(5)

if __name__ == "__main__":
    main()