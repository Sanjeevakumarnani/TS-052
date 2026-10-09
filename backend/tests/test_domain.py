import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.domain import calculate_score, calculate_gaps, calculate_priority, simulate


def test_weighted_score_known_demo():
    dims={"digital":{"score":52},"electricity":{"score":71},"roads":{"score":39},"public_digital":{"score":48},"essential_services":{"score":44}}
    result=calculate_score(dims)
    assert result["overall"] == 51.0
    assert result["coverage_percent"] == 100.0
    assert result["category"]["key"] == "vulnerable"


def test_missing_data_reports_coverage_and_does_not_treat_as_zero():
    dims={"digital":{"score":50},"electricity":{"score":None},"roads":{"score":None},"public_digital":{"score":None},"essential_services":{"score":None}}
    result=calculate_score(dims)
    assert result["overall"] is None
    assert result["coverage_percent"] == 25.0


def test_gap_is_only_reported_for_comparable_numeric_values():
    result=calculate_gaps({"digital":{"label":"Digital","availability_score":95,"reliability_score":52}})
    assert result[0]["gap_points"] == 43
    assert calculate_gaps({"digital":{"availability_score":None,"reliability_score":52}}) == []


def test_priority_is_explainable_and_bounded():
    v={"population":{"value":5000},"criticality":80,"alternative_access":20}
    p=calculate_priority(v, 40)
    assert 0 <= p["score"] <= 100
    assert len(p["top_reasons"]) == 3
    assert "infrastructure_deficit" in p["factors"]


def test_scenario_does_not_mutate_baseline():
    dims={"digital":{"score":50,"availability_score":80,"reliability_score":50},"electricity":{"score":50},"roads":{"score":50},"public_digital":{"score":50},"essential_services":{"score":50}}
    v={"id":"x","name":"Demo X","population":{"value":1000},"dimensions":dims,"criticality":50,"alternative_access":50}
    result=simulate(v,{"roads":70},100,"test")
    assert result["baseline"]["score"] == 50.0
    assert result["scenario"]["score"] == 54.0
    assert v["dimensions"]["roads"]["score"] == 50


def test_invalid_scenario_value_raises():
    v={"id":"x","name":"Demo X","population":{"value":1000},"dimensions":{"digital":{"score":50},"electricity":{"score":50},"roads":{"score":50},"public_digital":{"score":50},"essential_services":{"score":50}}}
    try:
        simulate(v,{"roads":101})
    except ValueError:
        return
    assert False, "out of range scenario must fail"
