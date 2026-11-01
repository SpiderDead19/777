from io import BytesIO
from pathlib import Path

import pandas as pd
import streamlit as st

from excel_parser import parse_excel_invoice
from multi_matcher import compare_suppliers
from pdf_parser import parse_invoice


st.set_page_config(page_title="ИИ-Снабженец v2", page_icon="📊", layout="wide")
st.title("ИИ-Снабженец v2")
st.caption("Загрузите предложения поставщиков в PDF или Excel. Система сопоставит позиции и найдёт лучшие цены.")

threshold = st.slider("Минимальная уверенность сопоставления по названию, %", 50, 100, 72)
files = st.file_uploader(
    "Счета / коммерческие предложения",
    type=["pdf", "xlsx", "xls"],
    accept_multiple_files=True,
    help="Можно загрузить несколько PDF и Excel файлов разных поставщиков одновременно.",
)


def parse_file(uploaded):
    suffix = Path(uploaded.name).suffix.lower()
    if suffix == ".pdf":
        return parse_invoice(uploaded)
    return parse_excel_invoice(uploaded)


if files:
    suppliers = {}
    errors = []
    st.subheader("Поставщики и загруженные позиции")

    for i, uploaded in enumerate(files, start=1):
        default_name = Path(uploaded.name).stem
        supplier = st.text_input(f"Поставщик для {uploaded.name}", value=default_name, key=f"supplier_{i}_{uploaded.name}")
        try:
            df = parse_file(uploaded)
            if df.empty:
                errors.append(f"{uploaded.name}: позиции не найдены")
                continue
            # Ensure duplicate supplier labels do not overwrite each other.
            label = supplier.strip() or default_name
            unique_label = label
            n = 2
            while unique_label in suppliers:
                unique_label = f"{label} ({n})"
                n += 1
            suppliers[unique_label] = df
            with st.expander(f"{unique_label} — {len(df)} поз."):
                cols = [c for c in ["article", "name", "quantity", "price"] if c in df.columns]
                st.dataframe(df[cols], use_container_width=True, hide_index=True)
        except Exception as exc:
            errors.append(f"{uploaded.name}: {exc}")

    for error in errors:
        st.warning(error)

    if suppliers:
        comparison = compare_suppliers(suppliers, threshold=threshold)
        st.subheader("Оптимальный выбор по поставщикам")
        st.dataframe(comparison, use_container_width=True, hide_index=True)

        if not comparison.empty:
            total_saving = comparison["Экономия с макс. цены"].fillna(0).sum()
            c1, c2, c3 = st.columns(3)
            c1.metric("Сопоставлено товаров", len(comparison))
            c2.metric("Поставщиков", len(suppliers))
            c3.metric("Потенциальная экономия", f"{total_saving:,.2f}")

            output = BytesIO()
            with pd.ExcelWriter(output, engine="openpyxl") as writer:
                comparison.to_excel(writer, sheet_name="Лучшие цены", index=False)
                for idx, (supplier, df) in enumerate(suppliers.items(), start=1):
                    safe = "".join(ch for ch in supplier if ch not in "[]:*?/\\")[:25]
                    df.to_excel(writer, sheet_name=f"{idx}_{safe}"[:31], index=False)

            st.download_button(
                "Скачать итоговый Excel",
                data=output.getvalue(),
                file_name="ai_procurement_comparison.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
else:
    st.info("Загрузите минимум одно предложение в PDF или Excel. Для сравнения цен рекомендуется 2 и более поставщика.")
