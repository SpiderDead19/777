"""Browser-based ИИ-Снабженец: supplier quote comparison and secure Excel exports."""
from __future__ import annotations

import hmac
import os
import re
from pathlib import Path

import pandas as pd
import streamlit as st

from online_core import (
    CATEGORIES, OUTPUT_MIME, compare_offers, make_excel,
    parse_offer, supplier_excel,
)

st.set_page_config(
    page_title="ИИ-Снабженец | Анализ КП",
    page_icon="⚙️",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown("""
<style>
    .block-container {padding-top: 2rem; max-width: 1650px;}
    div[data-testid="stMetric"] {border: 1px solid #30445D; border-radius: 12px; padding: 16px;}
    div[data-testid="stMetricLabel"] {font-weight: 600;}
    .main h1 {letter-spacing: -1px;}
</style>
""", unsafe_allow_html=True)

def secret_password() -> str:
    value = os.environ.get("SNAB_ACCESS_PASSWORD", "")
    if value:
        return value
    try:
        return str(st.secrets.get("SNAB_ACCESS_PASSWORD", ""))
    except (FileNotFoundError, Exception):
        return ""

def guard():
    configured = secret_password()
    if not configured:
        st.title("🔐 ИИ-Снабженец")
        st.error("Доступ закрыт: администратор ещё не настроил пароль в Secrets.")
        st.caption("Настройте SNAB_ACCESS_PASSWORD в Streamlit Cloud → Advanced settings → Secrets.")
        st.stop()
    if st.session_state.get("snab_authenticated"):
        return
    st.title("⚙️ ИИ-Снабженец")
    st.caption("Закрытый онлайн-кабинет отдела снабжения")
    st.markdown("**Введите пароль доступа к приложению:**")
    show_password = st.checkbox("Показать вводимые символы", key="snab_show_password")
    with st.form("sign_in", clear_on_submit=False):
        password = st.text_input(
            "Пароль",
            type="default" if show_password else "password",
            placeholder="Нажмите сюда и введите пароль",
            label_visibility="visible",
            key="snab_login_password",
        )
        ok = st.form_submit_button("Войти", type="primary", use_container_width=True)
    if ok:
        if not password:
            st.warning("Сначала нажмите на поле и введите пароль.")
        elif hmac.compare_digest(password.encode(), configured.encode()):
            st.session_state["snab_authenticated"] = True
            st.rerun()
        else:
            st.error("Неверный пароль. Используйте тот, который задан в настройках Secrets.")
    st.caption("Если пароль неизвестен: откройте панель управления Streamlit Cloud → App settings → Secrets. Не публикуйте пароль в чате.")
    st.stop()

guard()

with st.sidebar:
    st.title("⚙️ ИИ-Снабженец")
    st.caption("Онлайн · Сравнение поставщиков")
    st.divider()
    st.markdown("**Модули**")
    st.markdown("🟢 Анализ коммерческих предложений")
    st.markdown("🟢 Оптимальная закупка")
    st.markdown("🟢 Выгрузка заявок поставщикам")
    st.caption("История закупок и AI-проверка аналогов — следующие этапы.")
    st.divider()
    st.caption("PDF / Excel · До 20 файлов · Без отправки файлов в сторонний AI API")
    if st.button("Выйти", use_container_width=True):
        for key in ["snab_authenticated", "snab_analysis", "snab_files"]:
            st.session_state.pop(key, None)
        st.rerun()

st.title("ИИ-Снабженец")
st.caption("Сравнение КП · Оригинал и аналоги · Выбор лучшего поставщика · Excel-заявки")

st.markdown("### 1. Коммерческие предложения")
files = st.file_uploader(
    "Загрузите счета или предложения от поставщиков",
    type=["xlsx", "pdf"],
    accept_multiple_files=True,
    help="XLSX: номенклатура, количество, цена, бренд/качество, срок. PDF: таблицы с текстовым слоем.",
)
if files and len(files) > 20:
    st.error("Допустимо не более 20 файлов за один расчёт.")
    st.stop()

offer_settings = []
if files:
    st.caption("Укажите поставщика и качество. Для ТД СК НОВОСИБ по вашему правилу по умолчанию установлен оригинал.")
    with st.container(border=True):
        for i, file in enumerate(files):
            if file.size > 15 * 1024 * 1024:
                st.error(f"{file.name}: превышен предел 15 МБ на файл.")
                st.stop()
            proposed_name = Path(file.name).stem[:80]
            c1, c2, c3, c4 = st.columns([2, 2, 2, 2.6])
            supplier = c1.text_input("Поставщик", proposed_name, key=f"snab_name_{i}")
            modes = ["По данным КП", "Все позиции — оригинал", "Все позиции — аналог"]
            guess_original = bool(re.search(r"тд\s*ск|новосиб", supplier.lower()))
            mode = c2.selectbox(
                "Тип качества", modes,
                index=1 if guess_original else 0,
                key=f"snab_quality_{i}",
            )
            currency = c3.selectbox(
                "Валюта", ["Авто", "RUB", "EUR"],
                key=f"snab_currency_{i}",
            )
            c4.caption(f"**Файл {i+1}:** {file.name}")
            offer_settings.append((
                supplier.strip(), file,
                {"По данным КП":"as_file", "Все позиции — оригинал":"original", "Все позиции — аналог":"analogue"}[mode],
                {"Авто":"auto", "RUB":"RUB", "EUR":"EUR"}[currency],
            ))

st.markdown("### 2. Правила расчёта")
p1, p2, p3 = st.columns([1, 1, 1])
eur = p1.number_input(
    "Курс EUR → RUB", min_value=0.0, max_value=1000.0, value=0.0, step=0.1,
    help="Если в предложении цены в евро, укажите ваш актуальный расчётный курс. 0 — расчёт EUR запрещён.",
)
quality_pct = p2.slider("Вес качества, %", 0, 100, 60, 5)
threshold = p3.slider("Совпадение по названию, %", 75, 98, 85, 1)

st.info(
    "Качество определяется по маркировке предложения и ориентировочной категории бренда. "
    "Это предварительная закупочная оценка, а не подтверждение оригинальности. "
    "Перед заказом обязательно проверьте производителя, применимость, гарантию и НДС/доставку."
)

if st.button("🔎 Сопоставить и рассчитать закупку", type="primary", use_container_width=True,
             disabled=not bool(files)):
    if len(offer_settings) < 2:
        st.warning("Для сравнения загрузите предложения минимум двух поставщиков.")
    elif any(not supplier for supplier, *_ in offer_settings):
        st.error("У всех поставщиков должно быть название.")
    elif len({supplier.lower() for supplier, *_ in offer_settings}) != len(offer_settings):
        st.error("Название каждого поставщика должно быть уникальным.")
    else:
        offers = []
        errors = []
        with st.spinner("Распознаю номенклатуру и сравниваю предложения..."):
            for supplier, file, quality, currency in offer_settings:
                try:
                    parsed = parse_offer(file.getvalue(), file.name, currency, quality)
                    offers.append((supplier, parsed))
                except (ValueError, KeyError, TypeError, IndexError, RuntimeError) as exc:
                    errors.append(f"**{file.name}**: {exc}")
            if any("EUR" in set(df["currency"]) for _, df in offers) and eur <= 0:
                errors.append("В КП обнаружены цены в EUR. Укажите актуальный курс EUR → RUB.")
            if errors:
                for err in errors:
                    st.error(err)
            elif len(offers) >= 2:
                comparison, allocations = compare_offers(
                    offers, eur_rate=eur, threshold=threshold, quality_weight=quality_pct / 100,
                )
                st.session_state["snab_analysis"] = {
                    "comparison": comparison,
                    "allocations": allocations,
                    "quality_weight": quality_pct / 100,
                    "eur_rate": eur,
                    "offer_counts": {name: len(df) for name, df in offers},
                }
                st.success("Анализ завершён. Распределение сформировано по всем предложениям, включая дополнительные позиции.")
            else:
                st.error("Нужны два успешно распознанных файла.")

if "snab_analysis" in st.session_state:
    analysis = st.session_state["snab_analysis"]
    comparison: pd.DataFrame = analysis["comparison"]
    allocations: dict[str, pd.DataFrame] = analysis["allocations"]
    total = float(pd.to_numeric(comparison["Сумма ₽"], errors="coerce").sum())
    selected = comparison["Победитель"].ne("Нет цены")
    risks = comparison["Проверки"].fillna("").ne("")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Позиций", f"{len(comparison):,}".replace(",", " "))
    c2.metric("Закрыто", int(selected.sum()))
    c3.metric("Плановая закупка", f"{total:,.0f} ₽".replace(",", " "))
    c4.metric("Требуют проверки", int(risks.sum()))

    tab1, tab2, tab3 = st.tabs(["📋 Сравнение", "🏷️ Поставщики", "⚠️ Контроль качества"])
    with tab1:
        st.caption("Зелёным в Excel выделены цены выбранных поставщиков. Для совпадений по названию указана необходимость ручной проверки.")
        st.dataframe(
            comparison, use_container_width=True, hide_index=True,
            column_config={"Сумма ₽": st.column_config.NumberColumn(format="%.2f ₽"),
                           "Лучшая цена ₽": st.column_config.NumberColumn(format="%.2f ₽")},
        )
    with tab2:
        summary = []
        for supplier, df in allocations.items():
            selected_rows = comparison[comparison["Победитель"] == supplier]
            summary.append({
                "Поставщик": supplier,
                "Позиций": len(df),
                "Сумма, ₽": float(pd.to_numeric(selected_rows["Сумма ₽"], errors="coerce").sum()),
            })
        st.dataframe(pd.DataFrame(summary), use_container_width=True, hide_index=True)
        for supplier, df in allocations.items():
            with st.expander(f"{supplier} — {len(df)} позиций", expanded=False):
                st.dataframe(df, use_container_width=True, hide_index=True)
    with tab3:
        flagged = comparison[risks]
        if flagged.empty:
            st.success("Автоматические предупреждения не обнаружены.")
        else:
            st.dataframe(
                flagged[["Артикул", "Наименование", "Победитель", "Проверка сопоставления", "Проверки"]],
                use_container_width=True, hide_index=True,
            )
        st.warning("Совпадения по названию и аналоги нужно проверять по каталогу техники до оформления заказа.")

    st.markdown("### 3. Скачать готовые файлы")
    excel = make_excel(comparison, allocations, analysis["quality_weight"], analysis["eur_rate"])
    st.download_button(
        "📊 Общая сводная таблица Excel",
        data=excel, file_name="snab_svodnoe_sravnenie.xlsx",
        mime=OUTPUT_MIME, use_container_width=True,
    )
    cols = st.columns(min(3, len(allocations)))
    for i, (supplier, df) in enumerate(allocations.items()):
        safe_filename = re.sub(r"[^a-zA-Zа-яА-Я0-9_-]+", "_", supplier)[:45]
        cols[i % len(cols)].download_button(
            f"📄 Заявка {supplier} ({len(df)} поз.)",
            data=supplier_excel(df, supplier),
            file_name=f"zayavka_{safe_filename}.xlsx",
            mime=OUTPUT_MIME, use_container_width=True,
            disabled=df.empty,
            key=f"snab_download_{i}",
        )
    st.caption(
        "Каждая заявка содержит только позиции конкретного поставщика — без цен конкурентов. "
        "Файлы загруженных КП и результаты не записываются в репозиторий или базу данных; "
        "при обновлении страницы результаты могут быть утрачены."
    )
else:
    st.caption("Загрузите файлы, настройте параметры и запустите анализ. Результаты появятся здесь.")
