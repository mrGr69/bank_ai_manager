from datetime import datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

from app.classify.rules import classify_rules

KYIV = ZoneInfo("Europe/Kyiv")


def _c(desc, amount, mcc=""):
    return classify_rules(
        description=desc,
        mcc=mcc,
        amount=Decimal(str(amount)),
        bank_category="",
    )


def test_silpo_is_groceries():
    r = _c("Сільпо", -245.50, "5411")
    assert r.category == "GROCERIES_HOME"
    assert r.clarification_needed is False
    assert r.is_internal is False


def test_google_dating():
    r = _c("Google", -42.99, "5817")
    assert r.category == "DATING_ROMANCE"


def test_google_other_is_subscription():
    r = _c("Google", -448.31, "7399")
    assert r.category == "SUBSCRIPTIONS_WORK"


def test_jet_scooter():
    r = _c("JET.UA", -16.53, "7999")
    assert r.category == "TRANSIT_URBAN"


def test_stanislava_housing():
    r = _c("Станіслава К.", -12637.22, "4829")
    assert r.category == "HOUSING_FIXED"
    assert r.is_essential is True


def test_bluebird_salary():
    r = _c("Зарплата, 'БЛЮБЕРД ТЕХ'. Zarobitna plata za II polovynu serpnia", 10486.66)
    assert r.category == "INCOME_SALARY"
    assert r.is_internal is False


def test_self_hop_small_is_internal():
    r = _c("Від: Zacheshyhryva Bohdan", 1000, "6012")
    assert r.is_internal is True


def test_self_hop_salary():
    r = _c("Від: Zacheshyhryva Bohdan", 17838, "4829")
    assert r.category == "INCOME_SALARY"
    assert r.is_internal is False


def test_own_card_hidden():
    r = _c("Зі своєї картки *6993", 1000)
    assert r.is_internal is True
    assert r.exclude_from_budget is True


def test_liubchyk_clarifies():
    r = _c("LIUBCHYK, KYIV", -3146, "5812")
    assert r.category == "DINING_LEISURE"
    assert r.clarification_needed is True


def test_bolt_food_not_taxi():
    r = _c("Bolt Food", -540.7, "5811")
    assert r.category == "DINING_LEISURE"


def test_tuition_excluded():
    r = _c("ЧНУ ім. Б. Хмельницького. Oplata za navchannia", -19101)
    assert r.category == "ONE_OFF"
    assert r.exclude_from_budget is True
