from decimal import Decimal
from pathlib import Path

from app.services import catalogue

FIXTURE = Path(__file__).parent / "fixtures" / "price_list.csv"


def test_parse_price_formats():
    assert catalogue.parse_price("$12.50") == (Decimal("12.50"), "USD")
    assert catalogue.parse_price("€1.234,50") == (Decimal("1234.50"), "EUR")
    assert catalogue.parse_price("1,234.50 GBP") == (Decimal("1234.50"), "GBP")
    assert catalogue.parse_price("28,40") == (Decimal("28.40"), None)
    assert catalogue.parse_price("1,200") == (Decimal("1200"), None)
    assert catalogue.parse_price(9.5) == (Decimal("9.5"), None)
    assert catalogue.parse_price("on request") == (None, None)


def test_spreadsheet_skips_title_row_and_guesses_mapping():
    sheet = catalogue.parse_spreadsheet(FIXTURE.read_bytes(), FIXTURE.name)
    assert sheet.columns[0] == "Item No."
    assert len(sheet.rows) == 5  # blank row dropped
    mapping = catalogue.guess_mapping(sheet.columns)
    assert mapping["sku"] == "Item No."
    assert mapping["name"] == "Product Name"
    assert mapping["category"] == "Category"
    assert mapping["material"] == "Material"
    assert mapping["unit_price"] == "FOB Price (USD)"
    assert mapping["moq"] == "MOQ"
    assert mapping["hs_code"] == "HS Code"
    assert mapping["description"] is None


def test_apply_mapping_flags_problems():
    sheet = catalogue.parse_spreadsheet(FIXTURE.read_bytes(), FIXTURE.name)
    rows, errors = catalogue.apply_mapping(
        sheet.rows, catalogue.guess_mapping(sheet.columns), "EUR"
    )
    first = rows[0]
    assert first["unit_price"] == "12.50" and first["currency"] == "USD"
    assert first["moq"] == 500
    assert first["attributes"] == {"Finish": "Pre-seasoned"}
    assert rows[3]["_skip"] is True  # duplicate SKU
    by_row = {e["row"]: e["problems"] for e in errors}
    assert any("duplicate SKU" in p for p in by_row[4])
    assert any("not a number" in p for p in by_row[5])
    assert rows[4]["_skip"] is False and rows[4]["unit_price"] is None


def test_xlsx(tmp_path):
    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    ws.append(["SKU", "Name", "Price", "Currency"])
    ws.append([1001, "Towel", 3.2, "eur"])
    path = tmp_path / "list.xlsx"
    wb.save(path)
    sheet = catalogue.parse_spreadsheet(path.read_bytes(), "list.xlsx")
    rows, errors = catalogue.apply_mapping(sheet.rows, catalogue.guess_mapping(sheet.columns), None)
    assert rows[0]["sku"] == "1001"
    assert rows[0]["currency"] == "EUR"
    assert errors == []


def test_chunk_text_splits_on_pages():
    text = "\n\n".join(f"--- page {i} ---\n" + "x" * 100 for i in range(1, 11))
    chunks = catalogue.chunk_text(text, max_chars=350)
    assert len(chunks) > 1
    assert all(c.startswith("--- page") for c in chunks)
    assert "".join(chunks) == text
