from io import BytesIO
import pandas as pd
import streamlit as st

from database import init_db, save_best_offers
from multi_matcher import compare_suppliers
from pdf_parser import parse_invoice

st.set_page_config(page_title="ИИ-Снабженец 2.0", page_icon="⚙️", layout="wide")
init_db()

st.title("⚙️ ИИ-Снабженец 2.0")
st.caption("Мультисравнение коммерческих предложений · оптимальный выбор · история закупок")

purchase_name = st.text_input("Название закупки", "Новая закупка")
threshold = st.slider("Минимальная уверенность сопоставления, %", 50, 100, 72)
files = st.file_uploader("Загрузите счета / КП поставщиков", type=["pdf"], accept_multiple_files=True)

if files:
    suppliers = []
    st.subheader("Поставщики")
    for i, f in enumerate(files):
        c1, c2 = st.columns([1, 2])
        with c1:
            supplier = st.text_input(f"Поставщик {i+1}", value=f"Поставщик {i+1}", key=f"supplier_{i}")
        with c2:
            st.caption(f.name)
        suppliers.append((supplier, f))

    if st.button("🔎 Анализировать предложения", type="primary"):
        with st.spinner("Извлекаю позиции и сравниваю предложения..."):
            offers = [(name, parse_invoice(file)) for name, file in suppliers]
            valid = [(n, df) for n, df in offers if not df.empty]
            if not valid:
                st.error("Не удалось извлечь позиции из загруженных PDF.")
                st.stop()
            comparison = compare_suppliers(valid, threshold)
            st.session_state["comparison"] = comparison

if "comparison" in st.session_state:
    comparison = st.session_state["comparison"]
    total_saving = comparison["Экономия"].fillna(0).clip(lower=0).sum()
    covered = comparison["Лучшая цена"].notna().mean() * 100 if len(comparison) else 0
    k1, k2, k3 = st.columns(3)
    k1.metric("Позиций", len(comparison))
    k2.metric("Покрытие", f"{covered:.0f}%")
    k3.metric("Потенциальная экономия", f"{total_saving:,.2f} ₽".replace(",", " "))

    st.subheader("Сравнение предложений")
    st.dataframe(comparison, use_container_width=True, hide_index=True)

    st.subheader("Рекомендация")
    allocation = comparison.groupby("Лучший поставщик", dropna=False).agg(
        Позиций=("Артикул", "count"), Сумма=("Лучшая цена", "sum")
    ).reset_index()
    st.dataframe(allocation, use_container_width=True, hide_index=True)

    output = BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        comparison.to_excel(writer, sheet_name="Сравнение", index=False)
        allocation.to_excel(writer, sheet_name="Распределение", index=False)
    st.download_button("📊 Скачать Excel", output.getvalue(), "procurement_comparison.xlsx",
                       "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

    if st.button("💾 Зафиксировать лучшие цены в истории"):
        count = save_best_offers(purchase_name, comparison)
        st.success(f"Сохранено позиций: {count}")
