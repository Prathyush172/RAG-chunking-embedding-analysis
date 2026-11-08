import sys
import threading
import time
import traceback

def dump_threads():
    time.sleep(12)
    print("\n--- THREAD DUMP (STUCK) ---", flush=True)
    for th in threading.enumerate():
        print(f"Thread: {th.name}", flush=True)
        frame = sys._current_frames().get(th.ident)
        if frame:
            traceback.print_stack(frame)
    sys.exit(1)

threading.Thread(target=dump_threads, daemon=True).start()

print("1. Importing app...", flush=True)
from app.main import app
print("2. Importing TestClient...", flush=True)
from fastapi.testclient import TestClient
print("3. Instantiating TestClient...", flush=True)
with TestClient(app) as client:
    print("4. Inside TestClient context. Calling /api/health...", flush=True)
    r = client.get("/api/health")
    print(f"5. Response: {r.status_code} {r.json()}", flush=True)

print("6. All done successfully!", flush=True)
