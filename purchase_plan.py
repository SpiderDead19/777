import pandas as pd


def build_purchase_plan(comparison: pd.DataFrame, default_quantity: float = 1.0):
    """Build purchase lines and supplier totals from comparison results."""
    if comparison is None or comparison.empty:
        return pd.DataFrame(), pd.DataFrame()

    rows = []
    for _, row in comparison.iterrows():
        price = pd.to_numeric(row.get("Лучшая цена"), errors="coerce")
        if pd.isna(price):
            continue
        qty = pd.to_numeric(row.get("Количество"), errors="coerce")
        if pd.isna(qty) or qty <= 0:
            qty = default_quantity
        rows.append({
            "Поставщик": row.get("Лучший поставщик", ""),
            "Артикул": row.get("Артикул", ""),
            "Наименование": row.get("Наименование", ""),
            "Количество": float(qty),
            "Цена": float(price),
            "Сумма": round(float(qty) * float(price), 2),
        })

    plan = pd.DataFrame(rows)
    if plan.empty:
        return plan, pd.DataFrame()
    totals = (
        plan.groupby("Поставщик", as_index=False)
        .agg(Позиций=("Наименование", "count"), "Общая сумма"=("Сумма", "sum"))
        .sort_values("Общая сумма", ascending=False)
    )
    return plan, totals
