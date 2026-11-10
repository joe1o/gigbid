"""
db.py - GigSim's memory, stored in a small SQLite file.

In simple words:
    The marketplace has to remember things between requests (and restarts):
    which proposals were sent, the messages in each conversation, how many
    Connects each freelancer has left, and "timers" for when a fake client
    should react. SQLite is a database that lives in one file, needs no
    server, and comes built into Python. Good enough for a simulator.

Tables:
    proposals    - every submitted proposal and its status (submitted -> viewed -> replied/lost -> interview -> hired)
    messages     - chat messages; the thread id is the proposal id
    events       - timers: "at time T, do X to thread Y" (e.g. client replies)
    idempotency  - remembers the answer for each Idempotency-Key, so a retried
                   request never submits twice or spends Connects twice
    connects     - each freelancer's Connects balance
"""

import json
import sqlite3
import threading
import time
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS proposals (
    proposal_id TEXT PRIMARY KEY, freelancer_id TEXT, job_id TEXT, cover_letter TEXT,
    bid_amount REAL, screening_answers TEXT, connects_spent INTEGER, status TEXT,
    stage INTEGER DEFAULT 0, decision TEXT, created_at REAL
);
CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT, thread_id TEXT, sender TEXT, text TEXT, created_at REAL
);
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT, due_at REAL, kind TEXT, thread_id TEXT, done INTEGER DEFAULT 0
);
CREATE TABLE IF NOT EXISTS idempotency (
    key TEXT, freelancer_id TEXT, response TEXT, PRIMARY KEY (key, freelancer_id)
);
CREATE TABLE IF NOT EXISTS connects (freelancer_id TEXT PRIMARY KEY, balance INTEGER);
CREATE TABLE IF NOT EXISTS meta (k TEXT PRIMARY KEY, v TEXT);
"""


class DB:
    def __init__(self, path: str):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        # One shared connection guarded by a lock: simple and safe for a small simulator.
        self.conn = sqlite3.connect(path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.lock = threading.RLock()
        with self.lock:
            self.conn.executescript(SCHEMA)
            self.conn.commit()

    def q(self, sql: str, args: tuple = ()) -> list[dict]:
        """Run a SELECT and return rows as plain dicts."""
        with self.lock:
            return [dict(r) for r in self.conn.execute(sql, args).fetchall()]

    def x(self, sql: str, args: tuple = ()) -> None:
        """Run an INSERT/UPDATE/DELETE and save it."""
        with self.lock:
            self.conn.execute(sql, args)
            self.conn.commit()

    # --- small helpers -------------------------------------------------------

    def reset(self, accounts: list[str], weekly_connects: int) -> None:
        """Wipe everything and give each freelancer a full Connects balance."""
        with self.lock:
            for t in ["proposals", "messages", "events", "idempotency", "connects", "meta"]:
                self.conn.execute(f"DELETE FROM {t}")
            for fid in accounts:
                self.conn.execute("INSERT INTO connects VALUES (?, ?)", (fid, weekly_connects))
            self.conn.execute("INSERT INTO meta VALUES ('started_at', ?)", (str(time.time()),))
            self.conn.commit()

    def started_at(self) -> float:
        rows = self.q("SELECT v FROM meta WHERE k='started_at'")
        return float(rows[0]["v"]) if rows else time.time()

    def get_idem(self, key: str, fid: str):
        rows = self.q("SELECT response FROM idempotency WHERE key=? AND freelancer_id=?", (key, fid))
        return json.loads(rows[0]["response"]) if rows else None

    def put_idem(self, key: str, fid: str, response: dict) -> None:
        self.x("INSERT OR REPLACE INTO idempotency VALUES (?, ?, ?)", (key, fid, json.dumps(response)))

    def schedule(self, delay_s: float, kind: str, thread_id: str) -> None:
        self.x("INSERT INTO events (due_at, kind, thread_id) VALUES (?, ?, ?)",
               (time.time() + delay_s, kind, thread_id))

    def add_message(self, thread_id: str, sender: str, text: str) -> None:
        self.x("INSERT INTO messages (thread_id, sender, text, created_at) VALUES (?, ?, ?, ?)",
               (thread_id, sender, text, time.time()))
