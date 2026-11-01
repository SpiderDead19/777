from io import BytesIO
from pathlib import Path

import pandas as pd
import streamlit as st

from excel_parser import parse_excel_invoice
from history_db import history_summary, load_history, save_suppliers
from multi_matcher import compare_suppliers
from pdf_parser import parse_invoice
from purchase_plan import build_purchase_plan

st.set_page_config(page_title="ИИ-Снабженец v2", page_icon="📊", layout="wide")
st.title("ИИ-Снабженец v2")
st.caption("PDF/Excel → сравнение поставщиков → лучшие цены → заявка на закупку → история цен.")

threshold = st.slider("Минимальная уверенность сопоставления по названию, %", 50, 100, 72)
alert_pct = st.number_input("Предупреждать о росте цены выше, %", min_value=0.0, value=10.0, step=1.0)
files = st.file_uploader("Счета / коммерческие предложения", type=["pdf", "xlsx", "xls"], accept_multiple_files=True)


def parse_file(uploaded):
    return parse_invoice(uploaded) if Path(uploaded.name).suffix.lower() == ".pdf" else parse_excel_invoice(uploaded)


def price_alerts(suppliers, summary):
    if summary.empty:
        return pd.DataFrame()
    by_article = {str(r["Артикул"]).strip().lower(): r for _, r in summary.iterrows() if str(r["Артикул"]).strip()}
    alerts = []
    for supplier, df in suppliers.items():
        for _, row in df.iterrows():
            article = str(row.get("article", "") or "").strip().lower()
            if not article or article not in by_article:
                continue
            old = float(by_article[article]["Последняя цена"])
            new = pd.to_numeric(row.get("price"), errors="coerce")
            if pd.isna(new) or not old:
                continue
            change = (float(new) - old) / old * 100
            if change >= alert_pct:
                alerts.append({"Артикул": row.get("article", ""), "Наименование": row.get("name", ""), "Поставщик": supplier, "Предыдущая цена": old, "Новая цена": float(new), "Рост, %": round(change, 2)})
    return pd.DataFrame(alerts)


if files:
    suppliers, errors = {}, []
    st.subheader("Поставщики и загруженные позиции")
    for i, uploaded in enumerate(files, start=1):
        default_name = Path(uploaded.name).stem
        supplier = st.text_input(f"Поставщик для {uploaded.name}", value=default_name, key=f"supplier_{i}_{uploaded.name}")
        try:
            df = parse_file(uploaded)
            if df.empty:
                errors.append(f"{uploaded.name}: позиции не найдены")
                continue
            label = supplier.strip() or default_name
            unique_label, n = label, 2
            while unique_label in suppliers:
                unique_label, n = f"{label} ({n})", n + 1
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

        plan, supplier_totals = build_purchase_plan(comparison)
        if not comparison.empty:
            total_saving = comparison["Экономия с макс. цены"].fillna(0).sum()
            total_order = plan["Сумма"].sum() if not plan.empty else 0
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Товаров", len(comparison))
            c2.metric("Поставщиков", len(suppliers))
            c3.metric("Сумма закупки", f"{total_order:,.2f}")
            c4.metric("Потенциальная экономия", f"{total_saving:,.2f}")

        if not plan.empty:
            st.subheader("Заявка на закупку")
            edited_plan = st.data_editor(plan, use_container_width=True, hide_index=True, num_rows="fixed", disabled=["Поставщик", "Артикул", "Наименование", "Цена", "Сумма"], column_config={"Количество": st.column_config.NumberColumn(min_value=0.0, step=1.0)})
            edited_plan["Сумма"] = pd.to_numeric(edited_plan["Количество"], errors="coerce").fillna(0) * pd.to_numeric(edited_plan["Цена"], errors="coerce").fillna(0)
            supplier_totals = edited_plan.groupby("Поставщик", as_index=False).agg(Позиций=("Наименование", "count"), "Общая сумма"=("Сумма", "sum"))
            st.subheader("Заказы по поставщикам")
            st.dataframe(supplier_totals, use_container_width=True, hide_index=True)

        summary_before = history_summary()
        alerts = price_alerts(suppliers, summary_before)
        if not alerts.empty:
            st.subheader("⚠️ Предупреждения о росте цен")
            st.dataframe(alerts, use_container_width=True, hide_index=True)

        if st.button("Сохранить текущие цены в историю", type="primary"):
            count = save_suppliers(suppliers)
            st.success(f"В историю сохранено записей: {count}")

        output = BytesIO()
        with pd.ExcelWriter(output, engine="openpyxl") as writer:
            comparison.to_excel(writer, sheet_name="Лучшие цены", index=False)
            if not plan.empty:
                edited_plan.to_excel(writer, sheet_name="Заявка на закупку", index=False)
                supplier_totals.to_excel(writer, sheet_name="Итого по поставщикам", index=False)
                for supplier, group in edited_plan.groupby("Поставщик"):
                    safe = "".join(ch for ch in str(supplier) if ch not in "[]:*?/\\")[:24]
                    group.to_excel(writer, sheet_name=f"Заказ_{safe}"[:31], index=False)
            if not alerts.empty:
                alerts.to_excel(writer, sheet_name="Предупреждения", index=False)
            for idx, (supplier, df) in enumerate(suppliers.items(), start=1):
                safe = "".join(ch for ch in supplier if ch not in "[]:*?/\\")[:25]
                df.to_excel(writer, sheet_name=f"Исх_{idx}_{safe}"[:31], index=False)
        st.download_button("Скачать заявку и сравнение Excel", data=output.getvalue(), file_name="ai_procurement_order.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
else:
    st.info("Загрузите минимум одно предложение в PDF или Excel. Для сравнения рекомендуется 2 и более поставщика.")

st.divider()
st.subheader("История закупочных цен")
summary = history_summary()
if summary.empty:
    st.caption("История пока пуста. Загрузите предложения и нажмите «Сохранить текущие цены в историю».")
else:
    st.dataframe(summary, use_container_width=True, hide_index=True)
    with st.expander("Все записи истории"):
        st.dataframe(load_history(), use_container_width=True, hide_index=True)
