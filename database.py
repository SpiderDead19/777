import sqlite3
from pathlib import Path
from datetime import datetime

DB_PATH = Path("data/procurement.db")


def _connect():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with _connect() as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS purchases (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT NOT NULL,
            purchase_name TEXT NOT NULL,
            article TEXT,
            name TEXT,
            supplier TEXT,
            price REAL NOT NULL,
            quantity REAL DEFAULT 1,
            confidence REAL DEFAULT 100
        );
        CREATE INDEX IF NOT EXISTS idx_purchases_article ON purchases(article);
        CREATE INDEX IF NOT EXISTS idx_purchases_created ON purchases(created_at);
        """)


def save_best_offers(purchase_name, comparison):
    init_db()
    saved = 0
    with _connect() as conn:
        for _, row in comparison.iterrows():
            price = row.get("Лучшая цена")
            if price is None:
                continue
            conn.execute(
                "INSERT INTO purchases(created_at,purchase_name,article,name,supplier,price,quantity,confidence) VALUES(?,?,?,?,?,?,?,?)",
                (datetime.now().isoformat(timespec="seconds"), purchase_name,
                 str(row.get("Артикул", "")), str(row.get("Наименование", "")),
                 str(row.get("Лучший поставщик", "")), float(price),
                 float(row.get("Количество", 1) or 1), float(row.get("Уверенность, %", 100) or 0)),
            )
            saved += 1
    return saved


def price_history(article):
    init_db()
    with _connect() as conn:
        return [dict(r) for r in conn.execute(
            "SELECT created_at, supplier, price, purchase_name FROM purchases WHERE article=? ORDER BY created_at",
            (article,),
        ).fetchall()]
