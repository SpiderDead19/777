"""ИИ-Снабженец 3.0: browser dashboard for supplier quote comparison."""
from __future__ import annotations

import hmac
import os
import re
from pathlib import Path

import pandas as pd
import streamlit as st

from online_core import (
    OUTPUT_MIME,
    SELECTION_MODES,
    apply_supplier_choices,
    compare_offers,
    make_excel,
    parse_offer,
    supplier_excel,
    supplier_zip,
)


st.set_page_config(
    page_title="ИИ-Снабженец 3.0",
    page_icon="⚙️",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    """
    <style>
        .block-container {padding-top: 1.4rem; padding-bottom: 4rem; max-width: 1680px;}
        div[data-testid="stMetric"] {
            border: 1px solid #30445D;
            border-radius: 14px;
            padding: 16px;
            background: linear-gradient(145deg, rgba(23,36,59,.95), rgba(15,23,42,.95));
        }
        div[data-testid="stMetricLabel"] {font-weight: 650;}
        div[data-testid="stMetricValue"] {font-size: 1.7rem;}
        .main h1 {letter-spacing: -1.2px; margin-bottom: .1rem;}
        .main h2, .main h3 {letter-spacing: -.35px;}
        [data-testid="stSidebar"] {border-right: 1px solid #263752;}
    </style>
    """,
    unsafe_allow_html=True,
)


def local_mode() -> bool:
    return os.environ.get("SNAB_LOCAL_MODE", "").strip().lower() in {"1", "true", "yes"}


def secret_password() -> str:
    value = os.environ.get("SNAB_ACCESS_PASSWORD", "")
    if value:
        return value
    try:
        return str(st.secrets.get("SNAB_ACCESS_PASSWORD", ""))
    except Exception:
        return ""


def guard() -> str:
    """Require a cloud password while allowing the packaged local application."""
    if local_mode():
        return "local"
    configured = secret_password()
    if not configured:
        st.title("🔐 ИИ-Снабженец")
        st.error("Доступ закрыт: администратор ещё не настроил пароль в Secrets.")
        st.caption("Настройте SNAB_ACCESS_PASSWORD в параметрах облачного приложения.")
        st.stop()
    if st.session_state.get("snab_authenticated"):
        return "cloud"
    st.title("⚙️ ИИ-Снабженец")
    st.caption("Закрытый онлайн-кабинет отдела снабжения")
    st.markdown("**Введите пароль доступа к приложению:**")
    show_password = st.checkbox("Показать вводимые символы", key="snab_show_password")
    with st.form("sign_in", clear_on_submit=False):
        password = st.text_input(
            "Пароль",
            type="default" if show_password else "password",
            placeholder="Нажмите сюда и введите пароль",
            key="snab_login_password",
        )
        ok = st.form_submit_button("Войти", type="primary", use_container_width=True)
    if ok:
        if not password:
            st.warning("Сначала введите пароль.")
        elif hmac.compare_digest(password.encode(), configured.encode()):
            st.session_state["snab_authenticated"] = True
            st.rerun()
        else:
            st.error("Неверный пароль.")
    st.stop()


access_mode = guard()

with st.sidebar:
    st.title("⚙️ ИИ-Снабженец")
    st.caption("Версия 3.0 · Закупочный кабинет")
    st.divider()
    st.markdown("**Рабочий маршрут**")
    st.markdown("1. 📥 Загрузка КП")
    st.markdown("2. 🔗 Сопоставление позиций")
    st.markdown("3. 🏆 Автовыбор поставщиков")
    st.markdown("4. ✍️ Ручная корректировка")
    st.markdown("5. 📊 Сводная и заявки")
    st.divider()
    st.success("PDF / Excel · до 20 поставщиков")
    st.caption("Документы анализируются в текущей сессии и не передаются во внешний AI API.")
    if access_mode == "local":
        st.info("Локальная Windows-версия")
    elif st.button("Выйти", use_container_width=True):
        for key in ["snab_authenticated", "snab_analysis"]:
            st.session_state.pop(key, None)
        st.rerun()

st.title("ИИ-Снабженец 3.0")
st.caption("Счета и КП → единая номенклатура → оптимальная закупка → готовые Excel-заявки")

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
    st.caption("Для каждого файла проверьте поставщика, тип качества и валюту.")
    with st.container(border=True):
        for i, file in enumerate(files):
            if file.size > 15 * 1024 * 1024:
                st.error(f"{file.name}: превышен предел 15 МБ на файл.")
                st.stop()
            proposed_name = Path(file.name).stem[:80]
            c1, c2, c3, c4 = st.columns([2, 2, 1.3, 2.4])
            supplier = c1.text_input("Поставщик", proposed_name, key=f"snab_name_{i}")
            modes = ["По данным КП", "Все позиции — оригинал", "Все позиции — аналог"]
            guess_original = bool(re.search(r"тд\s*ск|новосиб", supplier.lower()))
            mode = c2.selectbox(
                "Тип качества",
                modes,
                index=1 if guess_original else 0,
                key=f"snab_quality_{i}",
            )
            currency = c3.selectbox("Валюта", ["Авто", "RUB", "EUR"], key=f"snab_currency_{i}")
            c4.caption(f"**Файл {i + 1}:** {file.name}")
            offer_settings.append((
                supplier.strip(),
                file,
                {"По данным КП": "as_file", "Все позиции — оригинал": "original", "Все позиции — аналог": "analogue"}[mode],
                {"Авто": "auto", "RUB": "RUB", "EUR": "EUR"}[currency],
            ))

st.markdown("### 2. Правила автовыбора")
p1, p2, p3, p4 = st.columns([1.25, 1, 1, 1])
mode_label = p1.selectbox(
    "Стратегия закупки",
    ["Цена и качество", "Минимальная цена", "Только оригинал"],
    help="После расчёта автоматический выбор можно изменить вручную для каждой позиции.",
)
selection_mode = {label: key for key, label in SELECTION_MODES.items()}[mode_label]
eur = p2.number_input(
    "Курс EUR → RUB",
    min_value=0.0,
    max_value=1000.0,
    value=0.0,
    step=0.1,
    help="0 — предложения в EUR не участвуют в выборе.",
)
quality_pct = p3.slider(
    "Вес качества, %",
    0,
    100,
    60,
    5,
    disabled=selection_mode != "best_value",
)
threshold = p4.slider("Совпадение названий, %", 75, 98, 85, 1)

if selection_mode == "original_only":
    st.info("Режим «Только оригинал»: аналоги останутся видны в сравнении, но не попадут в автоматический план закупки.")
else:
    st.info(
        "Класс качества определяется по маркировке КП и ориентировочной категории бренда. "
        "Оригинальность, совместимость, НДС, доставку и гарантию нужно подтвердить до заказа."
    )

if st.button(
    "🔎 Сопоставить и рассчитать закупку",
    type="primary",
    use_container_width=True,
    disabled=not bool(files),
):
    if len(offer_settings) < 2:
        st.warning("Для сравнения загрузите предложения минимум двух поставщиков.")
    elif any(not supplier for supplier, *_ in offer_settings):
        st.error("У всех поставщиков должно быть название.")
    elif len({supplier.lower() for supplier, *_ in offer_settings}) != len(offer_settings):
        st.error("Название каждого поставщика должно быть уникальным.")
    else:
        offers = []
        errors = []
        with st.spinner("Распознаю номенклатуру и формирую план закупки..."):
            for supplier, file, quality, currency in offer_settings:
                try:
                    parsed = parse_offer(file.getvalue(), file.name, currency, quality)
                    offers.append((supplier, parsed))
                except (ValueError, KeyError, TypeError, IndexError, RuntimeError) as exc:
                    errors.append(f"**{file.name}**: {exc}")
            if any("EUR" in set(df["currency"]) for _, df in offers) and eur <= 0:
                errors.append("В КП обнаружены цены в EUR. Укажите курс EUR → RUB или исключите валютное КП.")
            if errors:
                for error in errors:
                    st.error(error)
            elif len(offers) >= 2:
                comparison, allocations = compare_offers(
                    offers,
                    eur_rate=eur,
                    threshold=threshold,
                    quality_weight=quality_pct / 100,
                    selection_mode=selection_mode,
                )
                revision = int(st.session_state.get("snab_revision", 0)) + 1
                st.session_state["snab_revision"] = revision
                st.session_state["snab_analysis"] = {
                    "comparison": comparison,
                    "allocations": allocations,
                    "quality_weight": quality_pct / 100,
                    "eur_rate": eur,
                    "selection_mode": selection_mode,
                    "suppliers": [name for name, _ in offers],
                    "offer_counts": {name: len(df) for name, df in offers},
                    "revision": revision,
                }
                st.success("Анализ завершён. Ниже можно вручную изменить поставщика для любой позиции.")
            else:
                st.error("Нужны два успешно распознанных файла.")

if "snab_analysis" not in st.session_state:
    st.caption("Загрузите файлы, задайте правила и запустите анализ. Результаты появятся здесь.")
    st.stop()

analysis = st.session_state["snab_analysis"]
base_comparison: pd.DataFrame = analysis["comparison"]
suppliers: list[str] = analysis["suppliers"]

st.markdown("### 3. Финальный план закупки")
reset_col, note_col = st.columns([1, 4])
if reset_col.button("↩️ Сбросить ручной выбор", use_container_width=True):
    analysis["revision"] = int(analysis.get("revision", 0)) + 1
    st.session_state["snab_analysis"] = analysis
    st.rerun()
note_col.caption("Изменяйте только колонку «Выбранный поставщик». Поставщик без цены для конкретной позиции будет отклонён.")

editor_columns = [
    "№",
    "Артикул",
    "Наименование",
    "Кол-во",
    "Автовыбор",
    "Победитель",
    "Лучшая цена ₽",
    "Сумма ₽",
    "Проверки",
]
editor_frame = base_comparison[editor_columns].rename(columns={"Победитель": "Выбранный поставщик"})
edited_plan = st.data_editor(
    editor_frame,
    use_container_width=True,
    hide_index=True,
    disabled=[column for column in editor_frame.columns if column != "Выбранный поставщик"],
    column_config={
        "Выбранный поставщик": st.column_config.SelectboxColumn(
            options=suppliers + ["Нет цены"],
            required=True,
            width="medium",
        ),
        "Лучшая цена ₽": st.column_config.NumberColumn(format="%.2f ₽"),
        "Сумма ₽": st.column_config.NumberColumn(format="%.2f ₽"),
    },
    key=f"snab_plan_editor_{analysis.get('revision', 1)}",
)
choices = {
    int(row["№"]): str(row["Выбранный поставщик"])
    for _, row in edited_plan.iterrows()
}
comparison, allocations, choice_warnings = apply_supplier_choices(base_comparison, choices)
for warning in choice_warnings:
    st.warning(warning)

total = float(pd.to_numeric(comparison["Сумма ₽"], errors="coerce").sum())
saving = float(pd.to_numeric(comparison["Экономия ₽"], errors="coerce").sum())
selected = comparison["Победитель"].ne("Нет цены")
risks = comparison["Проверки"].fillna("").ne("")
manual = selected & comparison["Победитель"].ne(comparison["Автовыбор"])
m1, m2, m3, m4, m5 = st.columns(5)
m1.metric("Позиций", f"{len(comparison):,}".replace(",", " "))
m2.metric("Закрыто", f"{int(selected.sum())} из {len(comparison)}")
m3.metric("Плановая закупка", f"{total:,.0f} ₽".replace(",", " "))
m4.metric("Экономия", f"{saving:,.0f} ₽".replace(",", " "))
m5.metric("Ручных решений", int(manual.sum()))

tab_plan, tab_compare, tab_suppliers, tab_risks = st.tabs([
    "🛒 План закупки",
    "📋 Полное сравнение",
    "🏷️ Поставщики",
    "⚠️ Контроль",
])

with tab_plan:
    final_plan = comparison[[
        "№",
        "Артикул",
        "Наименование",
        "Кол-во",
        "Победитель",
        "Выбранный класс",
        "Лучшая цена ₽",
        "Сумма ₽",
        "Экономия ₽",
        "Причина",
        "Проверки",
    ]]
    st.dataframe(
        final_plan,
        use_container_width=True,
        hide_index=True,
        column_config={
            "Лучшая цена ₽": st.column_config.NumberColumn(format="%.2f ₽"),
            "Сумма ₽": st.column_config.NumberColumn(format="%.2f ₽"),
            "Экономия ₽": st.column_config.NumberColumn(format="%.2f ₽"),
        },
    )

with tab_compare:
    st.caption("В общей Excel-выгрузке выбранные цены подсвечиваются зелёным.")
    st.dataframe(
        comparison,
        use_container_width=True,
        hide_index=True,
        column_config={
            "Мин. цена ₽": st.column_config.NumberColumn(format="%.2f ₽"),
            "Макс. цена ₽": st.column_config.NumberColumn(format="%.2f ₽"),
            "Лучшая цена ₽": st.column_config.NumberColumn(format="%.2f ₽"),
            "Сумма ₽": st.column_config.NumberColumn(format="%.2f ₽"),
            "Экономия ₽": st.column_config.NumberColumn(format="%.2f ₽"),
        },
    )

with tab_suppliers:
    summary = []
    for supplier, dataframe in allocations.items():
        selected_rows = comparison[comparison["Победитель"] == supplier]
        summary.append({
            "Поставщик": supplier,
            "Позиций": len(dataframe),
            "Сумма, ₽": float(pd.to_numeric(selected_rows["Сумма ₽"], errors="coerce").sum()),
        })
    st.dataframe(
        pd.DataFrame(summary),
        use_container_width=True,
        hide_index=True,
        column_config={"Сумма, ₽": st.column_config.NumberColumn(format="%.2f ₽")},
    )
    for supplier, dataframe in allocations.items():
        with st.expander(f"{supplier} — {len(dataframe)} позиций", expanded=False):
            if dataframe.empty:
                st.caption("В финальном плане этому поставщику позиции не назначены.")
            else:
                st.dataframe(dataframe, use_container_width=True, hide_index=True)

with tab_risks:
    flagged = comparison[risks]
    if flagged.empty:
        st.success("Автоматические предупреждения не обнаружены.")
    else:
        st.dataframe(
            flagged[["Артикул", "Наименование", "Победитель", "Проверка сопоставления", "Проверки"]],
            use_container_width=True,
            hide_index=True,
        )
    st.warning("Совпадения по названию, аналоги и оригинальность нужно проверить по каталогу техники до оформления заказа.")

st.markdown("### 4. Скачать готовые файлы")
excel = make_excel(
    comparison,
    allocations,
    analysis["quality_weight"],
    analysis["eur_rate"],
    analysis["selection_mode"],
)
download_col1, download_col2 = st.columns(2)
download_col1.download_button(
    "📊 Общая сводная таблица Excel",
    data=excel,
    file_name="ИИ-Снабженец_сводное_сравнение.xlsx",
    mime=OUTPUT_MIME,
    use_container_width=True,
)
has_orders = any(not dataframe.empty for dataframe in allocations.values())
download_col2.download_button(
    "📦 Все заявки поставщикам одним ZIP",
    data=supplier_zip(allocations),
    file_name="ИИ-Снабженец_заявки_поставщикам.zip",
    mime="application/zip",
    use_container_width=True,
    disabled=not has_orders,
)

button_columns = st.columns(min(3, max(1, len(allocations))))
for i, (supplier, dataframe) in enumerate(allocations.items()):
    safe_filename = re.sub(r"[^a-zA-Zа-яА-Я0-9_-]+", "_", supplier)[:45]
    button_columns[i % len(button_columns)].download_button(
        f"📄 Заявка {supplier} ({len(dataframe)} поз.)",
        data=supplier_excel(dataframe, supplier),
        file_name=f"zayavka_{safe_filename}.xlsx",
        mime=OUTPUT_MIME,
        use_container_width=True,
        disabled=dataframe.empty,
        key=f"snab_download_{analysis.get('revision', 1)}_{i}",
    )

st.caption(
    "Каждая отдельная заявка содержит только позиции выбранного поставщика — без цен конкурентов. "
    "Загруженные КП и расчёты не записываются в репозиторий или постоянную базу данных."
)
