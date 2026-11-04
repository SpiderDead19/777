"""Regression checks for the online procurement comparison."""
import unittest
from io import BytesIO

import pandas as pd

from online_core import (
    CATEGORIES, article_from_name, compare_offers, make_excel, parse_offer,
    supplier_excel,
)

def excel_bytes(header, rows):
    buffer = BytesIO()
    pd.DataFrame(rows, columns=header).to_excel(buffer, index=False)
    return buffer.getvalue()

class ProcurementOnlineTests(unittest.TestCase):
    def setUp(self):
        ndv_bytes = excel_bytes(
            ["Кат номер", "Описание", "Кол-во", "Цена 1 шт, Евро, с НДС 22%", "Сумма Евро, с НДС 22%", "Бренд"],
            [
                ["BN023221", "Бак расширительный BN023221 (Bell 40E)", 1, 100, 100, "АНАЛОГ"],
                [210833, "Блок клапанов 210833 (Bell)", 2, 300, 600, "ОРИГИНАЛ"],
            ],
        )
        st_bytes = excel_bytes(
            ["N", "Номенклатура", "Ед. изм.", "К-во", "Цена", "Сроки поставки", "Бренд"],
            [
                [1, "Бак расширительный BN023221 (Bell 40E)", "шт", 1, 14000, "в наличии", "оригинал"],
                [2, "Блок клапанов 210833 (Bell)", "шт", 2, 25000, "до 4 недель", "оригинал"],
                [3, "Болт AL100005 (Bell)", "шт", 4, 50, "в наличии", "Стройтехникс"],
            ],
        )
        td_bytes = excel_bytes(
            ["№ п/п", "Номенклатура", "Артикул", "Кол-во, шт.", "Цена рублей", "Сумма рублей", "Срок готовности к отгрузке", "Примечание"],
            [
                [1, "Бак расширительный BN023221 (Bell 40E)", "BN023221", 1, 10000, 10000, "25-30 дней", ""],
                [2, "Блок клапанов 210833 (Bell)", 210833, 3, 26000, 78000, "25-30 дней", ""],
            ],
        )
        self.offers = [
            ("НДВ", parse_offer(ndv_bytes, "НДВ.xlsx")),
            ("Стройтехникс", parse_offer(st_bytes, "Стройтехникс.xlsx")),
            ("ТД СК НОВОСИБ", parse_offer(td_bytes, "ТД СК НОВОСИБ.xlsx", quality_mode="original")),
        ]

    def test_parses_all_three_supplier_formats(self):
        self.assertEqual([len(df) for _, df in self.offers], [2, 3, 2])
        self.assertEqual(self.offers[0][1].iloc[0]["currency"], "EUR")
        self.assertEqual(self.offers[1][1].iloc[0]["currency"], "RUB")
        self.assertEqual(self.offers[2][1].iloc[0]["quality"], "Оригинал")
        self.assertEqual(self.offers[0][1].iloc[1]["article"], "210833")

    def test_union_and_winner_for_price_quality(self):
        comparison, allocations = compare_offers(self.offers, eur_rate=90, quality_weight=0.6)
        self.assertEqual(len(comparison), 3)
        rows = comparison.set_index("Артикул")
        self.assertEqual(rows.loc["BN023221", "Победитель"], "ТД СК НОВОСИБ")
        self.assertEqual(rows.loc["210833", "Победитель"], "Стройтехникс")
        self.assertEqual(rows.loc["AL100005", "Победитель"], "Стройтехникс")
        self.assertEqual(len(allocations["ТД СК НОВОСИБ"]), 1)
        self.assertIn("количество отличается", rows.loc["210833", "Проверка сопоставления"])

    def test_euro_rate_required_for_euro_quotes(self):
        comparison, _ = compare_offers(self.offers, eur_rate=0)
        self.assertTrue(comparison["Победитель"].ne("НДВ").all())

    def test_supplier_export_does_not_expose_competitors(self):
        comparison, allocations = compare_offers(self.offers, eur_rate=90)
        file_bytes = supplier_excel(allocations["ТД СК НОВОСИБ"], "ТД СК НОВОСИБ")
        self.assertGreater(len(file_bytes), 500)
        sheet = pd.read_excel(BytesIO(file_bytes))
        self.assertEqual(len(sheet), 1)
        self.assertNotIn("Цена · НДВ", sheet.columns)
        self.assertNotIn("Стройтехникс", " ".join(sheet.columns))

    def test_common_export_is_readable(self):
        comparison, allocations = compare_offers(self.offers, eur_rate=90)
        file_bytes = make_excel(comparison, allocations, 0.6, 90)
        sheets = pd.read_excel(BytesIO(file_bytes), sheet_name=None)
        self.assertEqual(set(sheets), {"Итоги", "Сравнение", "Требует проверки", "Методика"})
        self.assertEqual(len(sheets["Сравнение"]), 3)

    def test_article_extraction(self):
        self.assertEqual(article_from_name("Блок клапанов 210833 (Bell 30D)"), "210833")
        self.assertEqual(article_from_name("Болт AL100005 (Bell)"), "AL100005")

if __name__ == "__main__":
    unittest.main()
