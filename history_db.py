import sqlite3
from datetime import datetime

import pandas as pd

DB_PATH = "procurement_history.db"


def _connect():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS price_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT NOT NULL,
            supplier TEXT NOT NULL,
            article TEXT,
            name TEXT NOT NULL,
            quantity REAL,
            price REAL NOT NULL
        )
    """)
    return conn


def save_suppliers(suppliers):
    now = datetime.now().isoformat(timespec="seconds")
    rows = []
    for supplier, df in suppliers.items():
        for _, row in df.iterrows():
            price = pd.to_numeric(row.get("price"), errors="coerce")
            if pd.isna(price):
                continue
            quantity = pd.to_numeric(row.get("quantity"), errors="coerce")
            rows.append((now, supplier, str(row.get("article", "") or ""), str(row.get("name", "") or ""), None if pd.isna(quantity) else float(quantity), float(price)))
    if not rows:
        return 0
    with _connect() as conn:
        conn.executemany("INSERT INTO price_history (created_at, supplier, article, name, quantity, price) VALUES (?, ?, ?, ?, ?, ?)", rows)
    return len(rows)


def load_history():
    with _connect() as conn:
        return pd.read_sql_query("SELECT * FROM price_history ORDER BY created_at DESC, id DESC", conn)


def history_summary():
    history = load_history()
    if history.empty:
        return history
    history["key"] = history["article"].fillna("").str.strip().str.lower()
    no_article = history["key"].eq("")
    history.loc[no_article, "key"] = history.loc[no_article, "name"].fillna("").str.strip().str.lower()
    rows = []
    for _, group in history.groupby("key", sort=False):
        latest = group.sort_values(["created_at", "id"], ascending=False).iloc[0]
        minimum = group.loc[group["price"].idxmin()]
        earliest = group.sort_values(["created_at", "id"]).iloc[0]
        change = ((latest["price"] - earliest["price"]) / earliest["price"] * 100) if earliest["price"] else None
        rows.append({
            "Артикул": latest["article"],
            "Наименование": latest["name"],
            "Последняя цена": latest["price"],
            "Последний поставщик": latest["supplier"],
            "Минимальная цена": minimum["price"],
            "Поставщик мин. цены": minimum["supplier"],
            "Изменение с первой записи, %": change,
            "Записей": len(group),
        })
    return pd.DataFrame(rows)
