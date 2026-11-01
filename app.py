from io import BytesIO

import pandas as pd
import streamlit as st

from matcher import compare_invoices
from pdf_parser import parse_invoice


st.set_page_config(page_title="Сравнение счетов PDF", page_icon="📄", layout="wide")
st.title("Сравнение счетов PDF")
st.caption("Загрузите два счёта. Программа извлечёт позиции, сопоставит их и сравнит цены.")

col1, col2 = st.columns(2)
with col1:
    pdf1 = st.file_uploader("Счёт 1", type=["pdf"], key="pdf1")
with col2:
    pdf2 = st.file_uploader("Счёт 2", type=["pdf"], key="pdf2")

threshold = st.slider("Минимальная уверенность сопоставления по названию, %", 50, 100, 72)

if pdf1 and pdf2:
    try:
        items1 = parse_invoice(pdf1)
        items2 = parse_invoice(pdf2)

        c1, c2 = st.columns(2)
        with c1:
            st.subheader(f"Позиции счёта 1: {len(items1)}")
            st.dataframe(items1[["article", "name", "price"]], use_container_width=True)
        with c2:
            st.subheader(f"Позиции счёта 2: {len(items2)}")
            st.dataframe(items2[["article", "name", "price"]], use_container_width=True)

        if items1.empty or items2.empty:
            st.warning("Не удалось извлечь позиции из одного из PDF. Возможно, PDF является сканом или для его формы нужно отдельное правило парсинга.")
        else:
            comparison = compare_invoices(items1, items2, threshold=threshold)
            st.subheader("Результат сравнения")
            st.dataframe(comparison, use_container_width=True, hide_index=True)

            output = BytesIO()
            with pd.ExcelWriter(output, engine="openpyxl") as writer:
                comparison.to_excel(writer, sheet_name="Сравнение", index=False)
                items1.to_excel(writer, sheet_name="Счёт 1", index=False)
                items2.to_excel(writer, sheet_name="Счёт 2", index=False)

            st.download_button(
                "Скачать сравнение Excel",
                data=output.getvalue(),
                file_name="invoice_comparison.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
    except Exception as exc:
        st.error(f"Ошибка обработки PDF: {exc}")
else:
    st.info("Загрузите оба PDF-файла, чтобы начать сравнение.")
