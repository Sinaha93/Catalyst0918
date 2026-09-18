import os
import sys
import json
import sqlite3
from pathlib import Path
from datetime import datetime
from contextlib import contextmanager

ROOT = Path(os.environ.get('CATALYST_HOME') or (Path(sys.executable).parent if getattr(sys, 'frozen', False) else Path(__file__).resolve().parents[1]))

def stamp():
    return datetime.now().astimezone().isoformat(timespec='seconds')

def init():
    for folder in ('data', 'input', 'archive', 'outputs', 'backups'):
        (ROOT / folder).mkdir(parents=True, exist_ok=True)
    with db() as c:
        c.executescript('''
        CREATE TABLE IF NOT EXISTS schema_version(version INTEGER PRIMARY KEY);
        INSERT OR IGNORE INTO schema_version VALUES(1);
        CREATE TABLE IF NOT EXISTS sources(id INTEGER PRIMARY KEY, name TEXT NOT NULL, hash TEXT UNIQUE NOT NULL, path TEXT NOT NULL, status TEXT NOT NULL, meta TEXT NOT NULL, created TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS profiles(id INTEGER PRIMARY KEY, name TEXT NOT NULL, signature TEXT NOT NULL, config TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS batches(id INTEGER PRIMARY KEY, source_id INTEGER, scope TEXT NOT NULL, mode TEXT NOT NULL, active INTEGER NOT NULL DEFAULT 1, created TEXT NOT NULL, FOREIGN KEY(source_id) REFERENCES sources(id));
        CREATE TABLE IF NOT EXISTS records(id INTEGER PRIMARY KEY, batch_id INTEGER NOT NULL, kind TEXT NOT NULL, part TEXT NOT NULL DEFAULT '', customer TEXT NOT NULL DEFAULT '', date TEXT NOT NULL, quantity TEXT, price TEXT, amount TEXT, note TEXT NOT NULL DEFAULT '', provenance TEXT NOT NULL, FOREIGN KEY(batch_id) REFERENCES batches(id));
        CREATE INDEX IF NOT EXISTS records_period ON records(date,kind);
        CREATE TABLE IF NOT EXISTS issues(id INTEGER PRIMARY KEY, source_id INTEGER, code TEXT NOT NULL, message TEXT NOT NULL, detail TEXT NOT NULL, resolved INTEGER NOT NULL DEFAULT 0, created TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS runs(id INTEGER PRIMARY KEY, period TEXT NOT NULL, version INTEGER NOT NULL, snapshot TEXT NOT NULL, created TEXT NOT NULL, UNIQUE(period,version));
        CREATE TABLE IF NOT EXISTS jobs(id TEXT PRIMARY KEY, state TEXT NOT NULL, message TEXT NOT NULL, result TEXT, created TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS audit(id INTEGER PRIMARY KEY, action TEXT NOT NULL, detail TEXT NOT NULL, created TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS part_links(id INTEGER PRIMARY KEY, part TEXT NOT NULL, customer TEXT NOT NULL, factory TEXT NOT NULL DEFAULT '', supplier TEXT NOT NULL DEFAULT '', vehicle TEXT NOT NULL DEFAULT '', price_type TEXT NOT NULL DEFAULT '', updated TEXT NOT NULL, UNIQUE(part,customer));
        CREATE TABLE IF NOT EXISTS price_estimates(period TEXT NOT NULL, part TEXT NOT NULL, customer TEXT NOT NULL, price TEXT NOT NULL, reason TEXT NOT NULL, enabled INTEGER NOT NULL DEFAULT 1, updated TEXT NOT NULL, PRIMARY KEY(period,part,customer));
        ''')

@contextmanager
def db():
    c = sqlite3.connect(ROOT / 'data' / 'master.sqlite3', timeout=30)
    c.row_factory = sqlite3.Row
    c.execute('PRAGMA foreign_keys=ON')
    try:
        yield c
        c.commit()
    except Exception:
        c.rollback()
        raise
    finally:
        c.close()

def encode(value):
    return json.dumps(value, ensure_ascii=False, default=str)

def audit(c, action, detail):
    c.execute('INSERT INTO audit(action,detail,created) VALUES(?,?,?)', (action, encode(detail), stamp()))

def backup():
    name = datetime.now().strftime('%Y%m%d_%H%M%S_%f') + '.sqlite3'
    path = ROOT / 'backups' / name
    with db() as origin:
        target = sqlite3.connect(path)
        try:
            origin.backup(target)
        finally:
            target.close()
    return name
