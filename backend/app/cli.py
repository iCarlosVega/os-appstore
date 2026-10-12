import argparse
import logging
import signal
import threading
from .store import initialize
from .backup import backup_database
from .jobs import run_due_jobs

def main():
    parser = argparse.ArgumentParser(description="Software store backend operations")
    parser.add_argument("command", choices=("migrate", "worker", "backup"))
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    initialize(migration=args.command == "migrate")
    if args.command == "migrate":
        print("Database migration complete.")
    elif args.command == "backup":
        print(f"Backup saved: {backup_database()}")
    else:
        stopping = threading.Event()
        signal.signal(signal.SIGINT, lambda *_: stopping.set())
        signal.signal(signal.SIGTERM, lambda *_: stopping.set())
        while not stopping.is_set():
            try:
                run_due_jobs()
            except Exception:
                logging.exception("Scheduler unavailable")
                if args.once:
                    raise
            if args.once:
                break
            stopping.wait(30)

if __name__ == "__main__":
    main()
