from typing import Any

WEIGHTS = {
    "digital": 0.25,
    "electricity": 0.20,
    "roads": 0.20,
    "public_digital": 0.15,
    "essential_services": 0.20,
}
DIMENSION_LABELS = {
    "digital": "Digital connectivity",
    "electricity": "Electricity reliability",
    "roads": "Road accessibility",
    "public_digital": "Public digital infrastructure",
    "essential_services": "Essential-service accessibility",
}
CATEGORIES = [
    {"min": 80, "max": 100, "key": "highly_reliable", "label": "Highly reliable"},
    {"min": 60, "max": 79.9999, "key": "adequate", "label": "Adequate"},
    {"min": 40, "max": 59.9999, "key": "vulnerable", "label": "Vulnerable"},
    {"min": 0, "max": 39.9999, "key": "critical", "label": "Critical"},
]
MIN_VALID_WEIGHT_COVERAGE = 0.60


def category_for(score: float | None) -> dict[str, Any]:
    if score is None:
        return {"key": "insufficient_data", "label": "Insufficient data"}
    if score >= 80:
        return {"key": "highly_reliable", "label": "Highly reliable"}
    if score >= 60:
        return {"key": "adequate", "label": "Adequate"}
    if score >= 40:
        return {"key": "vulnerable", "label": "Vulnerable"}
    return {"key": "critical", "label": "Critical"}


def calculate_score(dimensions: dict[str, Any], weights: dict[str, float] | None = None) -> dict[str, Any]:
    weights = weights or WEIGHTS
    valid_sum = 0.0
    valid_weight = 0.0
    component_scores: dict[str, float | None] = {}
    missing = []
    for key, weight in weights.items():
        item = dimensions.get(key) or {}
        score = item.get("score")
        try:
            score = float(score)
        except (TypeError, ValueError):
            score = None
        if score is None or score < 0 or score > 100:
            component_scores[key] = None
            missing.append(key)
            continue
        component_scores[key] = round(score, 2)
        valid_sum += score * weight
        valid_weight += weight
    total_weight = sum(weights.values()) or 1
    coverage = valid_weight / total_weight
    if coverage < MIN_VALID_WEIGHT_COVERAGE or valid_weight <= 0:
        score = None
    else:
        score = round(valid_sum / valid_weight, 2)
    return {
        "overall": score,
        "category": category_for(score),
        "components": component_scores,
        "coverage_percent": round(coverage * 100, 1),
        "missing_dimensions": missing,
        "weights": weights,
        "config_version": "v1",
    }


def calculate_gaps(dimensions: dict[str, Any]) -> list[dict[str, Any]]:
    gaps = []
    for key, item in dimensions.items():
        availability = item.get("availability_score")
        reliability = item.get("reliability_score", item.get("score"))
        if availability is None or reliability is None:
            continue
        try:
            availability, reliability = float(availability), float(reliability)
        except (TypeError, ValueError):
            continue
        if not (0 <= availability <= 100 and 0 <= reliability <= 100):
            continue
        gaps.append({
            "dimension": key,
            "label": item.get("label", DIMENSION_LABELS.get(key, key)),
            "availability": round(availability, 2),
            "reliability": round(reliability, 2),
            "gap_points": round(availability - reliability, 2),
            "interpretation": "availability exceeds reliability" if availability - reliability > 0 else ("reliability matches availability" if availability == reliability else "review indicator definitions"),
            "evidence_type": item.get("evidence_type", "unknown"),
        })
    return sorted(gaps, key=lambda x: x["gap_points"], reverse=True)


def calculate_priority(village: dict[str, Any], overall_score: float | None) -> dict[str, Any]:
    # Priority factors are decision-support heuristics, not official weights or validated predictions.
    deficit = 100 - overall_score if overall_score is not None else 100
    pop = village.get("population") or {}
    pop_value = pop.get("value", 0) if isinstance(pop, dict) else pop
    try:
        pop_value = max(0, float(pop_value))
    except (TypeError, ValueError):
        pop_value = 0
    population_factor = min(100.0, pop_value / 10000 * 100)
    try:
        criticality = min(100.0, max(0.0, float(village.get("criticality", 50))))
    except (TypeError, ValueError):
        criticality = 50.0
    try:
        alternative_access = min(100.0, max(0.0, float(village.get("alternative_access", 50))))
    except (TypeError, ValueError):
        alternative_access = 50.0
    lack_alternatives = 100 - alternative_access
    parts = {
        "infrastructure_deficit": round(deficit, 2),
        "population_impact": round(population_factor, 2),
        "service_criticality": round(criticality, 2),
        "lack_of_alternatives": round(lack_alternatives, 2),
    }
    score = deficit * 0.35 + population_factor * 0.25 + criticality * 0.25 + lack_alternatives * 0.15
    label = "Critical" if score >= 70 else "High" if score >= 55 else "Medium" if score >= 40 else "Low"
    reasons = sorted(parts.items(), key=lambda pair: pair[1], reverse=True)
    return {
        "score": round(score, 2), "label": label, "factors": parts,
        "weights": {"infrastructure_deficit": 0.35, "population_impact": 0.25, "service_criticality": 0.25, "lack_of_alternatives": 0.15},
        "top_reasons": [k for k, _ in reasons[:3]],
        "methodology_note": "Configurable prototype heuristic; not an official allocation rule or validated forecast.",
    }


def enrich_village(village: dict[str, Any]) -> dict[str, Any]:
    result = dict(village)
    dimensions = result.get("dimensions", {})
    score = calculate_score(dimensions)
    result["score"] = score
    result["gaps"] = calculate_gaps(dimensions)
    result["priority"] = calculate_priority(result, score["overall"])
    result["is_simulated"] = result.get("evidence_type") == "simulated" or any(
        (d or {}).get("evidence_type") == "simulated" for d in dimensions.values()
    )
    return result


def simulate(village: dict[str, Any], overrides: dict[str, float], cost: float | None = None, assumptions: str = "") -> dict[str, Any]:
    unknown = set(overrides) - set(WEIGHTS)
    if unknown:
        raise ValueError(f"Unknown dimension(s): {', '.join(sorted(unknown))}")
    cleaned = {}
    for key, value in overrides.items():
        value = float(value)
        if not 0 <= value <= 100:
            raise ValueError(f"{key} score must be between 0 and 100")
        cleaned[key] = round(value, 2)
    baseline = enrich_village(village)
    copied = {**village, "dimensions": {k: dict(v) for k, v in village.get("dimensions", {}).items()}}
    for key, value in cleaned.items():
        copied["dimensions"].setdefault(key, {"label": DIMENSION_LABELS[key]})["score"] = value
        if key == "digital" and "reliability_score" in copied["dimensions"][key]:
            copied["dimensions"][key]["reliability_score"] = value
    scenario = enrich_village(copied)
    base_score, scenario_score = baseline["score"]["overall"], scenario["score"]["overall"]
    delta = None if base_score is None or scenario_score is None else round(scenario_score - base_score, 2)
    cost_value = None if cost is None else float(cost)
    efficiency = None
    if cost_value is not None and cost_value > 0 and delta is not None:
        efficiency = round(delta / cost_value, 6)
    return {
        "village_id": village["id"], "village_name": village["name"],
        "baseline": {"score": base_score, "category": baseline["score"]["category"], "priority": baseline["priority"]},
        "scenario": {"score": scenario_score, "category": scenario["score"]["category"], "priority": scenario["priority"]},
        "delta_points": delta, "overrides": cleaned, "estimated_cost": cost_value,
        "improvement_per_cost_unit": efficiency, "assumptions": assumptions,
        "notice": "Scenario estimate based on user-supplied assumptions. It is not a causal forecast or funding recommendation.",
    }
