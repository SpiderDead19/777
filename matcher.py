import re

import pandas as pd
from rapidfuzz.fuzz import ratio


def _norm(value) -> str:
    value = str(value or "").lower().replace("ё", "е")
    return re.sub(r"[^a-zа-я0-9]+", "", value)


def _key(row) -> str:
    return _norm(row.get("name", "")) + "|" + _norm(row.get("characteristic", "")) + "|" + _norm(row.get("unit", ""))


def compare_invoices(left: pd.DataFrame, right: pd.DataFrame, threshold: int = 82) -> pd.DataFrame:
    """Match same procurement items, prioritizing exact name+characteristic+unit."""
    right_used = set()
    result = []
    exact = {}
    for idx, row in right.iterrows():
        exact.setdefault(_key(row), []).append(idx)

    for _, lrow in left.iterrows():
        match_idx = None
        score = 0.0
        method = ""
        for idx in exact.get(_key(lrow), []):
            if idx not in right_used:
                match_idx, score, method = idx, 100.0, "точное"
                break

        if match_idx is None:
            best_idx, best_score = None, 0.0
            lname = _norm(lrow.get("name", ""))
            lchar = _norm(lrow.get("characteristic", ""))
            for idx, rrow in right.iterrows():
                if idx in right_used:
                    continue
                # Do not fuzzy-match different explicit sizes/characteristics.
                rchar = _norm(rrow.get("characteristic", ""))
                if lchar and rchar and lchar != rchar:
                    continue
                candidate = ratio(lname, _norm(rrow.get("name", "")))
                if candidate > best_score:
                    best_idx, best_score = idx, candidate
            if best_idx is not None and best_score >= threshold:
                match_idx, score, method = best_idx, best_score, "название"

        if match_idx is None:
            result.append({"Позиция": lrow.get("line_no"), "Наименование": lrow.get("name", ""), "Характеристика": lrow.get("characteristic", ""), "Количество": lrow.get("quantity"), "Цена 1": lrow.get("price"), "Цена 2": None, "Разница за ед.": None, "Экономия": None, "Дешевле": "Не найдено во счёте 2", "Совпадение": "нет", "Уверенность, %": 0})
            continue

        right_used.add(match_idx)
        rrow = right.loc[match_idx]
        p1, p2 = float(lrow["price"]), float(rrow["price"])
        qty = lrow.get("quantity")
        qty = float(qty) if pd.notna(qty) else None
        diff_unit = p2 - p1
        savings = abs(diff_unit) * qty if qty is not None else None
        cheaper = "Счёт 1" if p1 < p2 else "Счёт 2" if p2 < p1 else "Одинаково"
        result.append({"Позиция": lrow.get("line_no"), "Наименование": lrow.get("name", ""), "Характеристика": lrow.get("characteristic", ""), "Количество": qty, "Цена 1": p1, "Цена 2": p2, "Разница за ед.": diff_unit, "Экономия": savings, "Дешевле": cheaper, "Совпадение": method, "Уверенность, %": round(score, 1)})

    for idx, rrow in right.iterrows():
        if idx not in right_used:
            result.append({"Позиция": rrow.get("line_no"), "Наименование": rrow.get("name", ""), "Характеристика": rrow.get("characteristic", ""), "Количество": rrow.get("quantity"), "Цена 1": None, "Цена 2": rrow.get("price"), "Разница за ед.": None, "Экономия": None, "Дешевле": "Не найдено во счёте 1", "Совпадение": "нет", "Уверенность, %": 0})

    return pd.DataFrame(result)
