from io import BytesIO

import pandas as pd
import streamlit as st

from excel_parser import parse_excel
from matcher import compare_invoices
from pdf_parser import parse_invoice


st.set_page_config(page_title="ИИ-Снабженец v2", page_icon="📊", layout="wide")
st.title("ИИ-Снабженец v2")
st.caption("Загружайте счета в PDF или Excel. Программа извлечёт позиции, сопоставит товары и сравнит цены.")


def parse_file(uploaded_file):
    name = uploaded_file.name.lower()
    if name.endswith(".pdf"):
        return parse_invoice(uploaded_file)
    if name.endswith((".xlsx", ".xls")):
        return parse_excel(uploaded_file)
    raise ValueError("Поддерживаются PDF, XLSX и XLS")


col1, col2 = st.columns(2)
with col1:
    file1 = st.file_uploader("Счёт / предложение 1", type=["pdf", "xlsx", "xls"], key="file1")
with col2:
    file2 = st.file_uploader("Счёт / предложение 2", type=["pdf", "xlsx", "xls"], key="file2")

threshold = st.slider("Минимальная уверенность сопоставления по названию, %", 50, 100, 72)

if file1 and file2:
    try:
        items1 = parse_file(file1)
        items2 = parse_file(file2)

        c1, c2 = st.columns(2)
        with c1:
            st.subheader(f"{file1.name}: {len(items1)} позиций")
            st.dataframe(items1, use_container_width=True, hide_index=True)
        with c2:
            st.subheader(f"{file2.name}: {len(items2)} позиций")
            st.dataframe(items2, use_container_width=True, hide_index=True)

        if items1.empty or items2.empty:
            st.warning("Не удалось извлечь позиции из одного из файлов. Для нестандартной формы счёта может потребоваться отдельное правило распознавания.")
        else:
            comparison = compare_invoices(items1, items2, threshold=threshold)
            st.subheader("Сравнение цен")
            st.dataframe(comparison, use_container_width=True, hide_index=True)

            output = BytesIO()
            with pd.ExcelWriter(output, engine="openpyxl") as writer:
                comparison.to_excel(writer, sheet_name="Сравнение", index=False)
                items1.to_excel(writer, sheet_name="Источник 1", index=False)
                items2.to_excel(writer, sheet_name="Источник 2", index=False)

            st.download_button(
                "Скачать результат в Excel",
                data=output.getvalue(),
                file_name="ai_procurement_comparison.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
    except Exception as exc:
        st.error(f"Ошибка обработки файла: {exc}")
else:
    st.info("Загрузите два файла. Можно сравнивать PDF ↔ PDF, Excel ↔ Excel или PDF ↔ Excel.")
