import re
import sqlite3
from pathlib import Path


def normalize_store(s: str | None) -> str:
    if not s: return ''
    s = re.sub(r'\b(d\.?o\.?o\.?|a\.?d\.?|doo|ad)\b', '', s, flags=re.I)
    s = re.sub(r'[,.؛;·•]', '', s)
    return s.strip()


def _compile_rules(rows: list[dict]) -> list[tuple[re.Pattern, str]]:
    compiled: list[tuple[re.Pattern, str]] = []
    for r in rows:
        if r.get("enabled", 1):
            try:
                compiled.append((re.compile(r["pattern"], re.I), r["category"]))
            except re.error:
                pass
    return compiled

def _db_rules(db: Path) -> list[tuple[re.Pattern, str]]:
    try:
        conn = sqlite3.connect(db)
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        cur.execute("SELECT pattern, category, enabled FROM rules ORDER BY priority ASC, id ASC")
        rows = [dict(r) for r in cur.fetchall()]
        conn.close()
        return _compile_rules(rows)
    except Exception:
        return []


def guess_category(store: str | None, db: Path | None = None) -> str:
    s = normalize_store(store)
    if not s:
        return 'other'
    if db:
        for rex, cat in _db_rules(db):
            if rex.search(s):
                return cat
    return 'other'
