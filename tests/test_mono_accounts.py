from decimal import Decimal

from app.banks.monobank import assign_mono_codes, compute_mono_debt, guess_code


def test_extra_uah_account_does_not_steal_black():
    accounts = [
        {"id": "jar1", "type": "eAid", "currencyCode": 980, "creditLimit": 0},
        {"id": "cred1", "type": "black", "currencyCode": 980, "creditLimit": 10000000},
        {"id": "w1", "type": "white", "currencyCode": 980, "creditLimit": 0},
    ]
    mapped = {code: raw["id"] for raw, code in assign_mono_codes(accounts)}
    assert mapped["black"] == "cred1"
    assert mapped["white"] == "w1"
    assert mapped["eaid_jar1"] == "jar1"


def test_black_with_limit_wins_over_black_debit():
    accounts = [
        {"id": "debit", "type": "black", "currencyCode": 980, "creditLimit": 0},
        {"id": "credit", "type": "black", "currencyCode": 980, "creditLimit": 5000000},
    ]
    mapped = {code: raw["id"] for raw, code in assign_mono_codes(accounts)}
    assert mapped["black"] == "credit"
    assert any(raw["id"] == "debit" for raw, code in assign_mono_codes(accounts) if code != "black")


def test_guess_code_white():
    assert guess_code({"type": "white", "currencyCode": 980}) == "white"


def test_compute_mono_debt():
    assert compute_mono_debt(Decimal("80000"), Decimal("100000")) == Decimal("20000.00")
    assert compute_mono_debt(Decimal("120000"), Decimal("100000")) == Decimal("0.00")
    assert compute_mono_debt(Decimal("5000"), Decimal("0")) == Decimal("0.00")


def test_should_fetch_statement_skips_jars():
    from types import SimpleNamespace

    from app.banks.monobank import should_fetch_statement

    jar = SimpleNamespace(external_id="x", code="eaid_jar1", credit_limit_uah=Decimal("0"))
    black = SimpleNamespace(external_id="x", code="black", credit_limit_uah=Decimal("0"))
    credit = SimpleNamespace(external_id="x", code="platinum_ab", credit_limit_uah=Decimal("10000"))
    empty = SimpleNamespace(external_id="", code="black", credit_limit_uah=Decimal("10000"))
    assert should_fetch_statement(jar) is False
    assert should_fetch_statement(black) is True
    assert should_fetch_statement(credit) is True
    assert should_fetch_statement(empty) is False
