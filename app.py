from io import BytesIO

import pandas as pd
import streamlit as st

from matcher import compare_invoices
from pdf_parser import parse_invoice

st.set_page_config(page_title="ИИ Снабженец", page_icon="📊", layout="wide")
st.title("ИИ Снабженец")
st.caption("Загрузите два PDF. Система сопоставит номенклатуру, характеристики и количества, покажет изменения цен и экономию.")

c1, c2 = st.columns(2)
with c1:
    pdf1 = st.file_uploader("Счёт / КП 1", type=["pdf"], key="pdf1")
with c2:
    pdf2 = st.file_uploader("Счёт / КП 2", type=["pdf"], key="pdf2")

threshold = st.slider("Уверенность сопоставления по названию, %", 60, 100, 82)

if pdf1 and pdf2:
    try:
        items1, items2 = parse_invoice(pdf1), parse_invoice(pdf2)
        if items1.empty or items2.empty:
            st.warning("Не удалось извлечь таблицу из одного из PDF.")
        else:
            comparison = compare_invoices(items1, items2, threshold=threshold)
            matched = comparison[comparison["Цена 1"].notna() & comparison["Цена 2"].notna()].copy()
            changed = matched[matched["Цена 1"].round(4) != matched["Цена 2"].round(4)].copy()

            total1 = float(items1["total"].dropna().sum()) if items1["total"].notna().any() else 0.0
            total2 = float(items2["total"].dropna().sum()) if items2["total"].notna().any() else 0.0
            delta = total2 - total1

            a, b, c = st.columns(3)
            a.metric("Итого счёт 1", f"{total1:,.2f} ₽".replace(",", " "))
            b.metric("Итого счёт 2", f"{total2:,.2f} ₽".replace(",", " "))
            if delta < 0:
                c.metric("Экономия счёта 2", f"{-delta:,.2f} ₽".replace(",", " "))
                st.success(f"Счёт 2 дешевле на {-delta:,.2f} ₽".replace(",", " "))
            elif delta > 0:
                c.metric("Экономия счёта 1", f"{delta:,.2f} ₽".replace(",", " "))
                st.success(f"Счёт 1 дешевле на {delta:,.2f} ₽".replace(",", " "))
            else:
                c.metric("Разница", "0 ₽")

            st.subheader("Позиции с изменившейся ценой")
            if changed.empty:
                st.info("Различий в ценах сопоставленных позиций нет.")
            else:
                st.dataframe(changed, use_container_width=True, hide_index=True)

            with st.expander("Показать полное сопоставление"):
                st.dataframe(comparison, use_container_width=True, hide_index=True)

            output = BytesIO()
            with pd.ExcelWriter(output, engine="openpyxl") as writer:
                changed.to_excel(writer, sheet_name="Изменения цен", index=False)
                comparison.to_excel(writer, sheet_name="Все позиции", index=False)
                items1.to_excel(writer, sheet_name="Счёт 1", index=False)
                items2.to_excel(writer, sheet_name="Счёт 2", index=False)
            st.download_button("Скачать анализ Excel", output.getvalue(), "ai_procurement_comparison.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    except Exception as exc:
        st.error(f"Ошибка обработки PDF: {exc}")
else:
    st.info("Загрузите два PDF-файла для сравнения.")
