import re
from io import BytesIO

import pdfplumber
import pandas as pd

PRICE_RE = re.compile(r"(?<!\d)(\d{1,3}(?:[\s\u00a0]\d{3})*(?:[.,]\d{2})|\d+[.,]\d{2})(?!\d)")
ARTICLE_RE = re.compile(r"\b[A-Za-zА-Яа-я0-9][A-Za-zА-Яа-я0-9._/-]{2,}\b")


def _to_float(value: str) -> float:
    value = value.replace("\u00a0", "").replace(" ", "").replace(",", ".")
    return float(value)


def extract_text(pdf_file) -> str:
    data = pdf_file.getvalue() if hasattr(pdf_file, "getvalue") else pdf_file.read()
    pages = []
    with pdfplumber.open(BytesIO(data)) as pdf:
        for page in pdf.pages:
            pages.append(page.extract_text(x_tolerance=2, y_tolerance=3) or "")
    return "\n".join(pages)


def parse_invoice(pdf_file) -> pd.DataFrame:
    """Best-effort parser for text-based invoices.

    Each line containing a decimal price is treated as a candidate item line.
    The final decimal number is used as the candidate unit price. This is a
    starting point; supplier-specific rules can be added once sample invoices
    are available.
    """
    text = extract_text(pdf_file)
    rows = []

    for line_no, raw_line in enumerate(text.splitlines(), start=1):
        line = " ".join(raw_line.split())
        if not line:
            continue

        prices = PRICE_RE.findall(line)
        if not prices:
            continue

        try:
            price = _to_float(prices[-1])
        except ValueError:
            continue

        tokens = ARTICLE_RE.findall(line)
        article = ""
        for token in tokens:
            if any(ch.isdigit() for ch in token) and not re.fullmatch(r"\d+[.,]?\d*", token):
                article = token
                break

        # Remove price-like values from the display name, but keep the source line.
        name = PRICE_RE.sub(" ", line)
        name = re.sub(r"\s+", " ", name).strip(" -;|")

        rows.append(
            {
                "line_no": line_no,
                "article": article,
                "name": name,
                "price": price,
                "source_line": line,
            }
        )

    return pd.DataFrame(rows, columns=["line_no", "article", "name", "price", "source_line"])
