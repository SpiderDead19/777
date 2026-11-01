import re

import pandas as pd


ALIASES = {
    "article": ["артикул", "арт", "код", "код товара", "номенклатурный номер", "sku", "article"],
    "name": ["наименование", "товар", "номенклатура", "описание", "name", "product"],
    "quantity": ["количество", "кол-во", "кол во", "qty", "quantity"],
    "price": ["цена", "цена за единицу", "цена ед", "price", "unit price"],
}


def _norm(value):
    value = str(value or "").strip().lower().replace("ё", "е")
    return re.sub(r"[^a-zа-я0-9]+", " ", value).strip()


def _to_number(value):
    if pd.isna(value):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).replace("\xa0", "").replace(" ", "").replace(",", ".")
    text = re.sub(r"[^0-9.\-]", "", text)
    try:
        return float(text)
    except ValueError:
        return None


def _find_header(raw: pd.DataFrame):
    best_row, best_score = 0, -1
    for idx in range(min(len(raw), 30)):
        values = [_norm(v) for v in raw.iloc[idx].tolist()]
        score = 0
        for aliases in ALIASES.values():
            if any(any(alias == cell or alias in cell for alias in aliases) for cell in values):
                score += 1
        if score > best_score:
            best_row, best_score = idx, score
    return best_row


def parse_excel(file) -> pd.DataFrame:
    """Extract article/name/quantity/price from the most likely table in xlsx/xls."""
    sheets = pd.read_excel(file, sheet_name=None, header=None)
    candidates = []

    for sheet_name, raw in sheets.items():
        if raw.empty:
            continue
        header_row = _find_header(raw)
        headers = [_norm(v) for v in raw.iloc[header_row].tolist()]
        mapping = {}
        for field, aliases in ALIASES.items():
            for col_idx, header in enumerate(headers):
                if any(alias == header or alias in header for alias in aliases):
                    mapping[field] = col_idx
                    break
        if "name" not in mapping or "price" not in mapping:
            continue

        rows = []
        for _, row in raw.iloc[header_row + 1:].iterrows():
            name = str(row.iloc[mapping["name"]] if mapping["name"] < len(row) else "").strip()
            price = _to_number(row.iloc[mapping["price"]])
            if not name or name.lower() == "nan" or price is None:
                continue
            article = ""
            if "article" in mapping:
                article = str(row.iloc[mapping["article"]]).strip()
                if article.lower() == "nan":
                    article = ""
            quantity = None
            if "quantity" in mapping:
                quantity = _to_number(row.iloc[mapping["quantity"]])
            rows.append({"article": article, "name": name, "quantity": quantity, "price": price, "sheet": sheet_name})

        if rows:
            candidates.append(pd.DataFrame(rows))

    if not candidates:
        return pd.DataFrame(columns=["article", "name", "quantity", "price", "sheet"])
    return pd.concat(candidates, ignore_index=True)
