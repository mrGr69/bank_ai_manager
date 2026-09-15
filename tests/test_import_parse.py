from pathlib import Path

from app.importers.mono import parse_mono_statement
from app.importers.privat import parse_privat_statement


ROOT = Path(__file__).resolve().parents[1]


def test_parse_mono_black_if_present():
    path = ROOT / "report_13-09-26_17-08-24.xls"
    if not path.exists():
        return
    parsed = parse_mono_statement(path)
    assert parsed["meta"]["debt"] is not None
    assert len(parsed["items"]) > 50
    assert parsed["items"][0]["description"]


def test_parse_privat_if_present():
    files = list(ROOT.glob("*.xlsx"))
    if not files:
        return
    parsed = parse_privat_statement(files[0])
    assert any("БЛЮБЕРД" in i["description"] or "блюберд" in i["description"].lower() for i in parsed["items"])
