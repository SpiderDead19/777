import re
from io import BytesIO

import pandas as pd
import pdfplumber

NUMBER_RE = re.compile(r"-?\d[\d\s\u00a0]*(?:[.,]\d+)?")


def _to_float(value) -> float:
    value = str(value).replace("\u00a0", "").replace(" ", "").replace(",", ".")
    return float(value)


def _clean(value) -> str:
    return " ".join(str(value or "").split()).strip()


def _number(value):
    text = _clean(value)
    if not text:
        return None
    match = NUMBER_RE.search(text)
    if not match:
        return None
    try:
        return _to_float(match.group(0))
    except ValueError:
        return None


def extract_text(pdf_file) -> str:
    data = pdf_file.getvalue() if hasattr(pdf_file, "getvalue") else pdf_file.read()
    pages = []
    with pdfplumber.open(BytesIO(data)) as pdf:
        for page in pdf.pages:
            pages.append(page.extract_text(x_tolerance=2, y_tolerance=3) or "")
    return "\n".join(pages)


def _parse_tables(data: bytes):
    rows = []
    with pdfplumber.open(BytesIO(data)) as pdf:
        for page_no, page in enumerate(pdf.pages, start=1):
            for table in page.extract_tables() or []:
                for raw in table:
                    cells = [_clean(x) for x in (raw or [])]
                    if len(cells) < 6:
                        continue
                    # Expected procurement table: N, name, characteristic, unit, qty, price, total.
                    n = _number(cells[0])
                    if n is None or not cells[1]:
                        continue
                    qty = _number(cells[-3])
                    price = _number(cells[-2])
                    total = _number(cells[-1])
                    if price is None:
                        continue
                    rows.append({
                        "line_no": int(n),
                        "page": page_no,
                        "article": "",
                        "name": cells[1],
                        "characteristic": cells[2] if len(cells) >= 7 else "",
                        "unit": cells[-4] if len(cells) >= 7 else "",
                        "quantity": qty,
                        "price": price,
                        "total": total,
                        "source_line": " | ".join(cells),
                    })
    return rows


def parse_invoice(pdf_file) -> pd.DataFrame:
    """Parse procurement PDF tables and return normalized line items."""
    data = pdf_file.getvalue() if hasattr(pdf_file, "getvalue") else pdf_file.read()
    rows = _parse_tables(data)
    columns = ["line_no", "page", "article", "name", "characteristic", "unit", "quantity", "price", "total", "source_line"]
    if rows:
        return pd.DataFrame(rows, columns=columns)

    # Fallback for text PDFs without detectable table geometry.
    text = extract_text(BytesIO(data))
    fallback = []
    for line_no, raw in enumerate(text.splitlines(), start=1):
        line = _clean(raw)
        nums = NUMBER_RE.findall(line)
        if len(nums) < 3:
            continue
        try:
            price = _to_float(nums[-2])
            total = _to_float(nums[-1])
        except ValueError:
            continue
        fallback.append({"line_no": line_no, "page": None, "article": "", "name": line, "characteristic": "", "unit": "", "quantity": None, "price": price, "total": total, "source_line": line})
    return pd.DataFrame(fallback, columns=columns)
