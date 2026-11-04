"""Parsing and procurement comparison for the browser app.

This module deliberately makes no network requests and does not persist uploaded files.
Brand quality scores are procurement *heuristics*, not proof of authenticity.
"""
from __future__ import annotations

import re
from io import BytesIO
from pathlib import Path
from collections import Counter
from typing import Any

import pandas as pd
from rapidfuzz import fuzz

from pdf_parser import parse_invoice

CATEGORIES = {
    "Оригинал": 100,
    "Премиум-аналог": 90,
    "Хороший аналог": 82,
    "Средний аналог": 72,
    "Восстановленный оригинал": 68,
    "Аналог без подтверждённого бренда": 65,
    "Бюджетный аналог": 60,
    "Качество не указано": 45,
}
PREMIUM = {"skf", "fag", "ina", "timken", "bosch", "dayco", "euroricambi"}
GOOD = {"dt spare parts", "vaden", "auger", "sampa", "ebs"}
MID = {"krauf", "motorhertz", "marshall", "patron", "tesla technics", "ttt", "topcover", "profi"}
BUDGET = {"stellox"}
OUTPUT_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
COLUMNS = ["article", "name", "qty", "unit", "price", "currency", "brand", "quality", "lead", "note", "source"]

def clean(value: Any) -> str:
    if value is None or (not isinstance(value, (list, dict)) and pd.isna(value)):
        return ""
    return " ".join(str(value).replace("\u00a0", " ").split()).strip()

def norm(value: Any) -> str:
    return re.sub(r"[^a-zа-я0-9]+", " ", clean(value).lower().replace("ё", "е")).strip()

def as_number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        v = float(value)
        return v if pd.notna(v) and v >= 0 else None
    s = clean(value).replace(" ", "").replace("₽", "").replace("€", "")
    if not s or s.lower() in {"nan", "none", "-", "непоставляем", "нет"}:
        return None
    if "," in s and "." in s:
        s = s.replace(",", "") if s.rfind(".") > s.rfind(",") else s.replace(".", "").replace(",", ".")
    else:
        s = s.replace(",", ".")
    try:
        v = float(s)
        return v if pd.notna(v) and v >= 0 else None
    except ValueError:
        return None

def article_from_name(name: str) -> str:
    # Search before the machine compatibility in parentheses ("Bell 40D").
    head = name.split("(")[0]
    codes = re.findall(r"\b(?:[A-Za-zА-Яа-я]{1,5}[- ]?)?\d{5,}[A-Za-zА-Яа-я0-9/-]*\b", head, flags=re.I)
    return codes[-1].upper().replace(" ", "") if codes else ""

def normalize_article(value: Any) -> str:
    return re.sub(r"[^A-ZА-Я0-9]+", "", clean(value).upper())

def quality_for(brand: str, mode: str) -> str:
    if mode == "original":
        return "Оригинал"
    if mode == "analogue":
        return "Аналог без подтверждённого бренда"
    b = norm(brand)
    if "восст" in b or "remanufactur" in b:
        return "Восстановленный оригинал"
    if "оригинал" in b or b in {"original", "oem", "genuine"}:
        return "Оригинал"
    if b in PREMIUM:
        return "Премиум-аналог"
    if b in GOOD:
        return "Хороший аналог"
    if b in MID or b == "стройтехникс":
        return "Средний аналог"
    if b in BUDGET:
        return "Бюджетный аналог"
    if b in {"аналог", "analog", "аналог не указан"}:
        return "Аналог без подтверждённого бренда"
    return "Качество не указано" if not b else "Аналог без подтверждённого бренда"

def _columns(row: list[Any]) -> dict[str, int]:
    found = {}
    for i, cell in enumerate(row):
        s = norm(cell)
        if not s:
            continue
        if any(w in s for w in ["номенклатур", "наименован", "описан", "наименование товара"]):
            found.setdefault("name", i)
        elif any(w in s for w in ["кат номер", "каталож", "артикул", "код товара", "парт номер"]):
            found.setdefault("article", i)
        elif "цена" in s and not any(w in s for w in ["сумма", "итого"]):
            found.setdefault("price", i)
        elif "сумма" in s or s == "стоимость":
            found.setdefault("total", i)
        elif any(w in s for w in ["кол во", "количество", "кол во шт", "кол во ед"]):
            found.setdefault("qty", i)
        elif "бренд" in s or "производител" in s or "качество" in s:
            found.setdefault("brand", i)
        elif "срок" in s or "наличие" in s or "готовност" in s:
            found.setdefault("lead", i)
        elif "примечан" in s or "комментар" in s:
            found.setdefault("note", i)
        elif s.startswith("ед изм") or s == "единица":
            found.setdefault("unit", i)
    return found

def _cell(row: tuple | list, cols: dict, key: str) -> Any:
    i = cols.get(key)
    return row[i] if i is not None and i < len(row) else None

def parse_xlsx(data: bytes, filename: str, currency_mode: str = "auto") -> pd.DataFrame:
    result = []
    sheets = pd.read_excel(BytesIO(data), sheet_name=None, header=None, dtype=object)
    for sheet, raw in sheets.items():
        if raw.empty:
            continue
        header_ix, columns, score = None, {}, -1
        for i in range(min(25, len(raw))):
            c = _columns(raw.iloc[i].tolist())
            sc = len(c)
            if "name" in c and "price" in c and sc > score:
                header_ix, columns, score = i, c, sc
        if header_ix is None:
            continue
        header_text = " ".join(clean(x).lower() for x in raw.iloc[header_ix].tolist())
        auto_currency = "EUR" if any(k in header_text for k in ["евро", "eur", "€"]) else "RUB"
        currency = auto_currency if currency_mode == "auto" else currency_mode
        for j in range(header_ix + 1, min(len(raw), 5001)):
            cells = raw.iloc[j].tolist()
            name = clean(_cell(cells, columns, "name"))
            if not name or norm(name) in {"итого", "всего", "итого по счету"}:
                continue
            price = as_number(_cell(cells, columns, "price"))
            total = as_number(_cell(cells, columns, "total"))
            qty = as_number(_cell(cells, columns, "qty"))
            if price is None and total is not None and qty and qty > 0:
                price = total / qty
            if price == 0:
                price = None
            article = clean(_cell(cells, columns, "article")) or article_from_name(name)
            if article.lower() in {"nan", "none"}:
                article = article_from_name(name)
            # Rows without a price are retained so the request coverage is visible.
            if price is None and not article and not qty:
                continue
            result.append({
                "article": normalize_article(article),
                "name": name,
                "qty": qty if qty is not None and qty > 0 else None,
                "unit": clean(_cell(cells, columns, "unit")) or "шт",
                "price": price,
                "currency": currency,
                "brand": clean(_cell(cells, columns, "brand")),
                "lead": clean(_cell(cells, columns, "lead")),
                "note": clean(_cell(cells, columns, "note")),
                "source": f"{filename} / {sheet} / строка {j+1}",
            })
    return pd.DataFrame(result)

def parse_offer(data: bytes, filename: str, currency_mode: str = "auto", quality_mode: str = "as_file") -> pd.DataFrame:
    if not data:
        raise ValueError("Пустой файл.")
    suffix = Path(filename).suffix.lower()
    if suffix == ".xlsx":
        df = parse_xlsx(data, filename, currency_mode)
    elif suffix == ".pdf":
        pdf = parse_invoice(BytesIO(data))
        currency = "RUB" if currency_mode == "auto" else currency_mode
        df = pd.DataFrame([{
            "article": normalize_article(clean(row.get("article")) or article_from_name(clean(row.get("name")))),
            "name": clean(row.get("name")),
            "qty": as_number(row.get("quantity")),
            "unit": clean(row.get("unit")) or "шт",
            "price": as_number(row.get("price")),
            "currency": currency,
            "brand": "",
            "lead": "",
            "note": "PDF: качество/валюта требуют подтверждения",
            "source": f"{filename} / стр. {clean(row.get('page'))}",
        } for _, row in pdf.iterrows()])
    else:
        raise ValueError("Поддерживаются PDF и XLSX.")
    if df.empty:
        raise ValueError("Не удалось распознать позиции. Проверьте заголовки/таблицу файла.")
    df["quality"] = df["brand"].map(lambda b: quality_for(b, quality_mode))
    return df.reindex(columns=COLUMNS)

def _is_offer(row: dict, eur_rate: float) -> bool:
    price = as_number(row.get("price"))
    if price is None or price <= 0:
        return False
    return row.get("currency") == "RUB" or (row.get("currency") == "EUR" and eur_rate > 0)

def _price_rub(row: dict, eur_rate: float) -> float | None:
    if not _is_offer(row, eur_rate):
        return None
    price = float(row["price"])
    return price * eur_rate if row["currency"] == "EUR" else price

def compare_offers(offers: list[tuple[str, pd.DataFrame]], eur_rate: float, threshold: int = 85,
                   quality_weight: float = 0.60) -> tuple[pd.DataFrame, dict[str, pd.DataFrame]]:
    """Build a union of supplier items with one-to-one links per supplier.

    Exact article match is preferred. Fuzzy name matches are labeled for manual review.
    """
    if len({s for s, _ in offers}) != len(offers):
        raise ValueError("Названия поставщиков должны быть уникальными.")
    groups: list[dict] = []
    for supplier, df in offers:
        for raw in df.to_dict("records"):
            item = dict(raw)
            article = normalize_article(item.get("article"))
            name = norm(item.get("name"))
            match = None
            match_score = 0
            match_method = ""
            for group in groups:
                if supplier in group["items"]:
                    continue
                base_article = group["article"]
                base_name = group["norm"]
                similarity = fuzz.token_sort_ratio(name, base_name)
                if article and base_article and article == base_article:
                    # Same catalog number with radically different descriptions is suspicious.
                    if similarity >= 30 and similarity > match_score:
                        match, match_score, match_method = group, similarity, "артикул"
                elif (not article or not base_article) and similarity >= threshold and similarity > match_score:
                    match, match_score, match_method = group, similarity, "название"
            if match is None:
                groups.append({
                    "article": article, "name": clean(item.get("name")), "norm": name,
                    "qty": as_number(item.get("qty")), "items": {supplier: item},
                    "match_warnings": [],
                })
            else:
                match["items"][supplier] = item
                if not match["article"]:
                    match["article"] = article
                if match_method == "название":
                    match["match_warnings"].append(f"{supplier}: совпадение по названию {match_score:.0f}%")
                elif match_score < 65:
                    match["match_warnings"].append(f"{supplier}: проверить описание при одинаковом артикуле")
                if as_number(item.get("qty")) and match["qty"] and abs(float(item["qty"]) - match["qty"]) > 0.001:
                    match["match_warnings"].append(f"{supplier}: количество отличается")

    combined = []
    allocations: dict[str, list[dict]] = {s: [] for s, _ in offers}
    for k, group in enumerate(groups, 1):
        row = {
            "№": k, "Артикул": group["article"], "Наименование": group["name"],
            "Кол-во": group["qty"], "Проверка сопоставления": "; ".join(group["match_warnings"]),
        }
        candidates = []
        for supplier, _ in offers:
            offer = group["items"].get(supplier)
            price = _price_rub(offer, eur_rate) if offer else None
            quality = clean(offer.get("quality")) if offer else ""
            row[f"{supplier} · цена ₽"] = round(price, 2) if price is not None else None
            row[f"{supplier} · качество"] = quality
            row[f"{supplier} · бренд"] = clean(offer.get("brand")) if offer else ""
            row[f"{supplier} · срок"] = clean(offer.get("lead")) if offer else ""
            if price is not None:
                candidates.append((supplier, price, quality, offer))
        if candidates:
            cheapest = min(p for _, p, _, _ in candidates)
            ranked = []
            for supplier, price, quality, offer in candidates:
                score = quality_weight * CATEGORIES.get(quality, 45) + (1 - quality_weight) * 100 * cheapest / price
                ranked.append((score, CATEGORIES.get(quality, 45), -price, supplier, price, quality, offer))
            best = max(ranked)
            _, _, _, winner, best_price, best_quality, best_offer = best
            quantity = group["qty"]
            # Do not assume missing demand quantity is one; avoid misleading totals.
            total = round(best_price * quantity, 2) if quantity else None
            risk = list(group["match_warnings"])
            if not quantity:
                risk.append("Не указано количество")
            if best_quality in {"Качество не указано", "Аналог без подтверждённого бренда", "Средний аналог", "Бюджетный аналог", "Восстановленный оригинал"}:
                risk.append("Проверить качество/производителя")
            if best_offer["currency"] == "EUR":
                risk.append("Проверить курс EUR и условия НДС/доставки")
            if not clean(best_offer.get("lead")):
                risk.append("Срок поставки не указан")
            row.update({
                "Победитель": winner, "Выбранный класс": best_quality,
                "Лучшая цена ₽": round(best_price, 2), "Сумма ₽": total,
                "Проверки": "; ".join(dict.fromkeys(risk)),
                "Причина": ("Минимальная цена" if best_price == cheapest else "Лучшее сочетание цены и качества")
                            + f"; {best_quality}",
            })
            allocations[winner].append({
                "№": k, "Артикул": group["article"], "Наименование": group["name"],
                "Кол-во": quantity, "Ед.": best_offer.get("unit", "шт"),
                "Требование к качеству": best_quality, "Указанный бренд": clean(best_offer.get("brand")),
                "Цена за ед.": best_offer.get("price"), "Валюта": best_offer["currency"],
                "Сумма": round(float(best_offer["price"]) * quantity, 2) if quantity else None,
                "Срок": clean(best_offer.get("lead")), "Примечание": "Просим подтвердить цену, качество, наличие, срок, гарантию и совместимость",
            })
        else:
            row.update({
                "Победитель": "Нет цены", "Выбранный класс": "",
                "Лучшая цена ₽": None, "Сумма ₽": None,
                "Проверки": "Нет действующей цены" + ("; укажите курс EUR" if eur_rate <= 0 else ""),
                "Причина": "Нет предложения с положительной ценой",
            })
        combined.append(row)
    return pd.DataFrame(combined), {s: pd.DataFrame(rows) for s, rows in allocations.items()}

def excel_safe(df: pd.DataFrame) -> pd.DataFrame:
    """Prevent Excel formula execution from untrusted supplier text."""
    result = df.copy()
    for column in result.select_dtypes(include=["object", "string"]).columns:
        result[column] = result[column].map(
            lambda value: "'" + value if isinstance(value, str) and value.lstrip().startswith(("=", "+", "-", "@")) else value
        )
    return result

def make_excel(comparison: pd.DataFrame, allocations: dict[str, pd.DataFrame],
               quality_weight: float, eur_rate: float) -> bytes:
    from openpyxl.styles import Font, PatternFill, Alignment
    out = BytesIO()
    summary = []
    for supplier, df in allocations.items():
        rows = len(df)
        total = pd.to_numeric(df.get("Сумма", pd.Series(dtype=float)), errors="coerce").sum()
        summary.append({"Поставщик": supplier, "Позиций": rows, "Сумма в валюте КП": None,
                        "Сумма выбранных позиций, ₽": round(sum(
                            (float(r["Сумма"]) * eur_rate if r["Валюта"] == "EUR" else float(r["Сумма"]))
                            for r in df.to_dict("records") if as_number(r.get("Сумма")) is not None
                        ), 2)})
    with pd.ExcelWriter(out, engine="openpyxl") as writer:
        pd.DataFrame(summary).to_excel(writer, sheet_name="Итоги", index=False)
        excel_safe(comparison).to_excel(writer, sheet_name="Сравнение", index=False)
        risk = comparison[comparison["Проверки"].fillna("").ne("")].copy()
        excel_safe(risk).to_excel(writer, sheet_name="Требует проверки", index=False)
        pd.DataFrame([
            {"Параметр": "Вес качества", "Значение": quality_weight},
            {"Параметр": "Вес цены", "Значение": 1-quality_weight},
            {"Параметр": "Курс EUR/RUB (указан пользователем)", "Значение": eur_rate},
            {"Параметр": "Источник классификации", "Значение": "Маркировка КП + ориентировочные брендовые категории"},
            {"Параметр": "Статус", "Значение": "Предварительный анализ; оригинальность и аналоги требуют проверки"},
        ]).to_excel(writer, sheet_name="Методика", index=False)
        for sheet in writer.book:
            sheet.freeze_panes = "E2" if sheet.title == "Сравнение" else "A2"
            sheet.auto_filter.ref = sheet.dimensions
            for cell in sheet[1]:
                cell.font = Font(color="FFFFFF", bold=True)
                cell.fill = PatternFill("solid", fgColor="16365C")
                cell.alignment = Alignment(wrap_text=True, vertical="center")
            sheet.row_dimensions[1].height = 34
            for col in sheet.columns:
                letter = col[0].column_letter
                maximum = max((len(str(cell.value or "")) for cell in col[:100]), default=12)
                sheet.column_dimensions[letter].width = min(52, max(12, maximum + 3))
            if sheet.title == "Сравнение":
                winners = {s: list(comparison.columns).index(f"{s} · цена ₽")+1 for s in allocations}
                winner_col = list(comparison.columns).index("Победитель")+1
                for r in range(2, len(comparison)+2):
                    name = sheet.cell(r, winner_col).value
                    if name in winners:
                        for c in (winners[name], winner_col):
                            sheet.cell(r, c).fill = PatternFill("solid", fgColor="C6EFCE")
                            sheet.cell(r, c).font = Font(color="006100", bold=True)
    return out.getvalue()

def supplier_excel(df: pd.DataFrame, supplier: str) -> bytes:
    from openpyxl.styles import Font, PatternFill
    out = BytesIO()
    with pd.ExcelWriter(out, engine="openpyxl") as writer:
        headers = ["№", "Артикул", "Наименование", "Кол-во", "Ед.", "Требование к качеству",
                   "Указанный бренд", "Цена за ед.", "Валюта", "Сумма", "Срок", "Примечание"]
        excel_safe(df.reindex(columns=headers)).to_excel(writer, sheet_name="Запрос подтверждения", index=False)
        sheet = writer.sheets["Запрос подтверждения"]
        sheet.freeze_panes = "D2"
        sheet.auto_filter.ref = sheet.dimensions
        for cell in sheet[1]:
            cell.fill = PatternFill("solid", fgColor="16365C")
            cell.font = Font(color="FFFFFF", bold=True)
        for col in sheet.columns:
            letter = col[0].column_letter
            maximum = max((len(str(cell.value or "")) for cell in col[:100]), default=12)
            sheet.column_dimensions[letter].width = min(50, max(12, maximum+3))
    return out.getvalue()
