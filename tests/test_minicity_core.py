import json

from dss.core.engine import SimulationEngine, build_minicity
from dss.core import ScenarioEditor, ScenarioSpec
from dss.experiments import ExperimentConfig, HeadlessRunner, compare_policies


def test_minicity_shape_and_world_zones():
    sim = build_minicity(11)
    assert len(sim.citizens) == 100
    assert len(sim.businesses) == 20
    assert len(sim.houses) == 30
    assert {loc.kind for loc in sim.map.locations.values()} >= {
        "Residential", "Commercial", "Industry", "School", "Hospital",
        "Government", "Park", "Transport", "Market",
    }


def test_365_day_stability_and_money_conservation():
    sim = build_minicity(11)
    sim.run(365)
    assert sim.day == 365
    assert all(report.ok for report in sim.health_reports)
    assert len(sim.transactions) > 1000
    assert abs(sim.metrics()["money_conservation_error"]) < 1e-4
    assert sim.metrics()["business_survival"] > 0


def test_save_load_continuation_is_deterministic(tmp_path):
    path = tmp_path / "state.json"
    left = build_minicity(17)
    left.run(14)
    left.save(path)
    right = SimulationEngine.load(path)
    left.step()
    right.step()
    assert left.to_dict() == right.to_dict()


def test_same_seed_policy_comparison_changes_metrics():
    cfg = ExperimentConfig(days=45, seeds=1, seed_start=9, snapshot_interval=0,
                           include_final_state=False)
    result = compare_policies(build_minicity,
                              {"Tax 5%": {"tax_rate": .05}, "Tax 15%": {"tax_rate": .15}}, cfg)
    assert "Tax 5%" in result.summary and "Tax 15%" in result.summary
    assert "Tax 15%" in result.deltas
    assert result.summary["Tax 5%"] != result.summary["Tax 15%"]


def test_scenario_editor_builds_custom_world(tmp_path):
    editor = ScenarioEditor(ScenarioSpec(seed=4))
    editor.set("population", 12).set("businesses", 4).set("houses", 6)
    editor.set_rule("tax_rate", .15).set_resource("food", 20)
    path = tmp_path / "scenario.json"
    editor.save(path)
    loaded = ScenarioSpec.load(path)
    sim = ScenarioEditor(loaded).build()
    assert len(sim.citizens) == 12 and len(sim.businesses) == 4 and len(sim.houses) == 6
    assert sim.rules.tax_rate == .15
