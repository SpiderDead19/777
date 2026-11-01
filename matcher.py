import re

import pandas as pd
from rapidfuzz.fuzz import ratio


def _norm(value: str) -> str:
    value = str(value or "").lower().replace("ё", "е")
    return re.sub(r"[^a-zа-я0-9]+", "", value)


def compare_invoices(left: pd.DataFrame, right: pd.DataFrame, threshold: int = 72) -> pd.DataFrame:
    """Match by article first, then by fuzzy product name."""
    right_used = set()
    result = []

    right_articles = {}
    for idx, row in right.iterrows():
        key = _norm(row.get("article", ""))
        if key:
            right_articles.setdefault(key, []).append(idx)

    for left_idx, lrow in left.iterrows():
        match_idx = None
        score = 0
        method = ""
        article_key = _norm(lrow.get("article", ""))

        if article_key:
            for candidate in right_articles.get(article_key, []):
                if candidate not in right_used:
                    match_idx = candidate
                    score = 100
                    method = "артикул"
                    break

        if match_idx is None:
            left_name = _norm(lrow.get("name", ""))
            best_idx = None
            best_score = 0
            for idx, rrow in right.iterrows():
                if idx in right_used:
                    continue
                candidate_score = ratio(left_name, _norm(rrow.get("name", "")))
                if candidate_score > best_score:
                    best_score = candidate_score
                    best_idx = idx
            if best_idx is not None and best_score >= threshold:
                match_idx = best_idx
                score = best_score
                method = "название"

        if match_idx is not None:
            right_used.add(match_idx)
            rrow = right.loc[match_idx]
            price1 = float(lrow["price"])
            price2 = float(rrow["price"])
            diff = price2 - price1
            pct = (diff / price1 * 100) if price1 else None
            cheaper = "Счёт 1" if price1 < price2 else "Счёт 2" if price2 < price1 else "Одинаково"
            result.append({
                "Артикул 1": lrow.get("article", ""),
                "Наименование 1": lrow.get("name", ""),
                "Цена 1": price1,
                "Артикул 2": rrow.get("article", ""),
                "Наименование 2": rrow.get("name", ""),
                "Цена 2": price2,
                "Разница (2-1)": diff,
                "Разница, %": pct,
                "Дешевле": cheaper,
                "Совпадение": method,
                "Уверенность, %": round(score, 1),
            })
        else:
            result.append({
                "Артикул 1": lrow.get("article", ""),
                "Наименование 1": lrow.get("name", ""),
                "Цена 1": float(lrow["price"]),
                "Артикул 2": "",
                "Наименование 2": "Не найдено",
                "Цена 2": None,
                "Разница (2-1)": None,
                "Разница, %": None,
                "Дешевле": "",
                "Совпадение": "нет",
                "Уверенность, %": 0,
            })

    for idx, rrow in right.iterrows():
        if idx not in right_used:
            result.append({
                "Артикул 1": "",
                "Наименование 1": "Не найдено",
                "Цена 1": None,
                "Артикул 2": rrow.get("article", ""),
                "Наименование 2": rrow.get("name", ""),
                "Цена 2": float(rrow["price"]),
                "Разница (2-1)": None,
                "Разница, %": None,
                "Дешевле": "",
                "Совпадение": "нет",
                "Уверенность, %": 0,
            })

    return pd.DataFrame(result)
