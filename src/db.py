import sqlite3
import json
from pathlib import Path

def get_conn(db_path: Path):
    return sqlite3.connect(db_path)

def init_db(db_path: Path):
    conn = get_conn(db_path)
    cur = conn.cursor()
    cur.execute('''
CREATE TABLE IF NOT EXISTS transactions (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  ts TEXT NOT NULL,
  store TEXT NOT NULL,
  amount REAL NOT NULL,
  currency TEXT NOT NULL DEFAULT 'RSD',
  category TEXT NOT NULL,
  source TEXT NOT NULL,
  raw_url TEXT,
  meta_json TEXT
);''')
    cur.execute('''
CREATE TABLE IF NOT EXISTS rules (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  pattern TEXT NOT NULL,
  category TEXT NOT NULL,
  enabled INTEGER NOT NULL DEFAULT 1,
  priority INTEGER NOT NULL DEFAULT 100
);''')
    try:
        cur.execute("ALTER TABLE transactions ADD COLUMN kind TEXT NOT NULL DEFAULT 'expense'")
    except Exception:
        pass
    cur.execute("SELECT COUNT(*) FROM rules")
    (cnt,) = cur.fetchone()
    if (cnt or 0) == 0:
        DEFAULT_RULES_SEED = [
            (r' (MAXI|IDEA|RODA|LIDL|VERO) ', 'Stores', 1, 10),
            (r'(APOTEKA|PHARM)', 'Pharmacy', 1, 20),
            (r'(OMV|GAZPROM|NIS|LUKOIL|БС)', 'Fuel', 1, 30),
            (r'(DM|LILLY)', 'Household', 1, 40),
            (r'(MC ?DONALD|KFC|PIZZA|BURGER|CAF?E|TOSTER)', 'Restaurants & Cafes', 1, 50),
        ]
        cur.executemany("INSERT INTO rules(pattern, category, enabled, priority) VALUES (?,?,?,?)",
                        DEFAULT_RULES_SEED)
    conn.commit()
    conn.close()

def insert_tx(db_path: Path, t: dict[str, any]):
    conn = get_conn(db_path)
    cur = conn.cursor()
    cur.execute(
        """INSERT INTO transactions(ts,store,amount,currency,category,source,raw_url,meta_json,kind)
           VALUES (?,?,?,?,?,?,?,?,?)""",
        (
            t["ts"], t["store"], t["amount"], t.get("currency","RSD"),
            t["category"], t.get("source","qr"), t.get("raw_url"),
            json.dumps(t.get("meta_json")) if t.get("meta_json") is not None else None,
            t.get("kind","expense")
        )
    )
    conn.commit()
    conn.close()

def update_tx(db_path, tx_id, **fields):
    if not fields:
        return
    allowed = {"ts","store","amount","currency","category","kind","source","raw_url","meta_json"}
    cols = [k for k in fields.keys() if k in allowed]
    vals = [fields[k] for k in cols]
    sets = ", ".join(f"{k}=?" for k in cols)
    conn = get_conn(db_path)
    cur = conn.cursor()
    cur.execute(f"UPDATE transactions SET {sets} WHERE id=?", (*vals, tx_id))
    conn.commit()
    conn.close()

def delete_tx(db_path, tx_id: int):
    conn = get_conn(db_path)
    cur = conn.cursor()
    cur.execute("DELETE FROM transactions WHERE id=?", (tx_id,))
    conn.commit()
    conn.close()

def list_tx(db_path: Path, limit=1000) -> list[dict[str, any]]:
    conn = get_conn(db_path)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute(
        "SELECT id, ts, store, amount, currency, category, kind FROM transactions ORDER BY ts DESC LIMIT ?",
        (limit,))
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows

def get_all_rules(db_path: Path):
    conn = get_conn(db_path); conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute("SELECT id, pattern, category, enabled, priority FROM rules ORDER BY priority ASC, id ASC")
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows

def add_rule(db_path: Path, pattern: str, category: str, enabled: int = 1, priority: int = 100):
    conn = get_conn(db_path); cur = conn.cursor()
    cur.execute("INSERT INTO rules(pattern, category, enabled, priority) VALUES (?,?,?,?)",
                (pattern, category, enabled, priority))
    conn.commit(); conn.close()

def update_rule(db_path: Path, rule_id: int, pattern: str, category: str, enabled: int, priority: int):
    conn = get_conn(db_path); cur = conn.cursor()
    cur.execute("""UPDATE rules SET pattern=?, category=?, enabled=?, priority=? WHERE id=?""",
                (pattern, category, enabled, priority, rule_id))
    conn.commit(); conn.close()

def delete_rule(db_path: Path, rule_id: int):
    conn = get_conn(db_path); cur = conn.cursor()
    cur.execute("DELETE FROM rules WHERE id=?", (rule_id,))
    conn.commit(); conn.close()

def current_balance(db_path: Path) -> int:
    conn = get_conn(db_path)
    cur = conn.cursor()
    cur.execute("""SELECT
        COALESCE(SUM(CASE WHEN kind='income' THEN amount END),0) -
        COALESCE(SUM(CASE WHEN kind='expense' THEN amount END),0)
      FROM transactions""")
    (bal,) = cur.fetchone()
    conn.close()
    return float(bal)
