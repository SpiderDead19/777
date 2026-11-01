import re
import pandas as pd
from rapidfuzz.fuzz import ratio


def _norm(value):
    return re.sub(r"[^a-zа-я0-9]+", "", str(value or "").lower().replace("ё", "е"))


def _find_match(base_row, offer, threshold):
    article = _norm(base_row.get("article", ""))
    if article:
        exact = offer[offer["article"].fillna("").map(_norm) == article]
        if not exact.empty:
            return exact.iloc[0], 100.0, "артикул"
    name = _norm(base_row.get("name", ""))
    if not name:
        return None, 0, "нет"
    best, score = None, 0
    for _, row in offer.iterrows():
        s = ratio(name, _norm(row.get("name", "")))
        if s > score:
            best, score = row, s
    if best is not None and score >= threshold:
        return best, float(score), "название"
    return None, float(score), "нет"


def compare_suppliers(offers, threshold=72):
    """offers: list[(supplier_name, dataframe)]. First offer is the comparison base."""
    if not offers:
        return pd.DataFrame()
    base_supplier, base = offers[0]
    rows = []
    for _, item in base.iterrows():
        prices, scores, methods = {}, [], []
        for supplier, offer in offers:
            match, score, method = _find_match(item, offer, threshold)
            prices[supplier] = float(match["price"]) if match is not None else None
            if match is not None:
                scores.append(score)
                methods.append(method)
        valid = {k: v for k, v in prices.items() if v is not None}
        best_supplier = min(valid, key=valid.get) if valid else ""
        best_price = valid.get(best_supplier)
        base_price = prices.get(base_supplier)
        saving = (base_price - best_price) if base_price is not None and best_price is not None else None
        row = {
            "Артикул": item.get("article", ""), "Наименование": item.get("name", ""),
            "Количество": item.get("quantity", 1), "Лучший поставщик": best_supplier,
            "Лучшая цена": best_price, "Экономия": saving,
            "Совпадение": " / ".join(sorted(set(methods))),
            "Уверенность, %": round(min(scores), 1) if scores else 0,
        }
        for supplier, price in prices.items():
            row[f"Цена · {supplier}"] = price
        rows.append(row)
    return pd.DataFrame(rows)
