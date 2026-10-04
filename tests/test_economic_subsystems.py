from dss.core.models import Business, Citizen
from dss.systems.economy import Economy
from dss.systems.education import Course, EducationSystem
from dss.systems.housing import House, HousingSystem
from dss.systems.labor import LaborMarket


def test_purchase_and_ledger_conserve_money():
    e = Economy()
    c = Citizen("c", 30, "hh", savings=100)
    b = Business("b", "shop", "market", inventory={"food": 2}, cash=10)
    assert e.purchase(c, b, "food", 1, 1)
    assert c.savings == 95
    assert b.cash == 15
    assert e.ledger.entries[-1].reason == "purchase"


def test_labor_weights_and_hire_are_inspectable():
    e = Economy()
    c = Citizen("c", 30, "hh")
    b = Business("b", "shop", "market")
    market = LaborMarket(e)
    p = market.open_position(b, "worker", 20, {"general": .4})
    weights = market.decision_weights(c, p)
    assert 0 <= weights["total"] <= 1
    assert market.apply(c, p)
    assert market.hire(p, c)


def test_housing_rent_and_education_service():
    e = Economy()
    c = Citizen("c", 30, "hh", savings=100)
    house = House("h", 2, 10)
    homes = HousingSystem(e, [house])
    assert homes.move(c, house)
    assert homes.collect_rent(30)
    school = EducationSystem(e, [Course("math", "math", 5, duration_days=1)])
    course = school.courses[0]
    assert school.enroll(c, course, 31)
    assert school.study(c, course, 32)
    assert c.skills["math"] > 0

