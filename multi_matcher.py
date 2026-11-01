import re

import pandas as pd
from rapidfuzz.fuzz import ratio


def _norm(value):
    value = str(value or "").lower().replace("ё", "е")
    return re.sub(r"[^a-zа-я0-9]+", "", value)


def _find_group(groups, article, name, threshold):
    article_key = _norm(article)
    name_key = _norm(name)
    if article_key:
        for i, group in enumerate(groups):
            if group["article_key"] and group["article_key"] == article_key:
                return i, 100
    best_i, best_score = None, 0
    for i, group in enumerate(groups):
        score = ratio(name_key, group["name_key"])
        if score > best_score:
            best_i, best_score = i, score
    return (best_i, best_score) if best_i is not None and best_score >= threshold else (None, 0)


def compare_suppliers(suppliers, threshold=72):
    """Combine any number of supplier DataFrames and select the cheapest offer per item."""
    groups = []
    for supplier, df in suppliers.items():
        for _, row in df.iterrows():
            article = row.get("article", "")
            name = row.get("name", "")
            try:
                price = float(row.get("price"))
            except (TypeError, ValueError):
                continue
            quantity = pd.to_numeric(row.get("quantity", None), errors="coerce")
            idx, score = _find_group(groups, article, name, threshold)
            offer = {"supplier": supplier, "article": article, "name": name, "price": price, "quantity": quantity, "score": score}
            if idx is None:
                groups.append({"article_key": _norm(article), "name_key": _norm(name), "article": article, "name": name, "offers": [offer]})
            else:
                groups[idx]["offers"].append(offer)

    rows = []
    for group in groups:
        offers = group["offers"]
        best = min(offers, key=lambda x: x["price"])
        prices = [x["price"] for x in offers]
        quantities = [x["quantity"] for x in offers if not pd.isna(x["quantity"]) and x["quantity"] > 0]
        quantity = quantities[0] if quantities else 1.0
        row = {
            "Артикул": group["article"],
            "Наименование": group["name"],
            "Количество": float(quantity),
            "Лучшая цена": best["price"],
            "Лучший поставщик": best["supplier"],
            "Предложений": len(offers),
            "Макс. цена": max(prices),
            "Экономия с макс. цены": (max(prices) - best["price"]) * float(quantity),
            "Разброс, %": ((max(prices) - min(prices)) / min(prices) * 100) if min(prices) else None,
        }
        for offer in offers:
            row[f"Цена | {offer['supplier']}"] = offer["price"]
        rows.append(row)
    return pd.DataFrame(rows)
