"""Apply plan feature presets to a family."""

from app.models.models import Family, Plan

BASIC_PRESET = {
    "rewards_enabled": True,
    "mission_evidence_enabled": False,
    "quiz_enabled": False,
    "chat_enabled": False,
    "agenda_enabled": False,
    "daily_mission_limit": 5,
}

STANDARD_PRESET = {
    "rewards_enabled": True,
    "mission_evidence_enabled": True,
    "quiz_enabled": True,
    "chat_enabled": False,
    "agenda_enabled": False,
    "daily_mission_limit": None,
}

FAMILY_PRESET = {
    "rewards_enabled": True,
    "mission_evidence_enabled": True,
    "quiz_enabled": True,
    "chat_enabled": True,
    "agenda_enabled": True,
    "daily_mission_limit": None,
}

PLAN_FEATURE_PRESETS = {
    "basic": BASIC_PRESET,
    "standard": STANDARD_PRESET,
    "family": FAMILY_PRESET,
}


def apply_plan_features(family: Family, plan: Plan) -> None:
    preset = plan.feature_preset or PLAN_FEATURE_PRESETS.get(plan.slug, BASIC_PRESET)
    for field in (
        "rewards_enabled",
        "mission_evidence_enabled",
        "quiz_enabled",
        "chat_enabled",
        "agenda_enabled",
    ):
        if field in preset:
            setattr(family, field, bool(preset[field]))
    if "daily_mission_limit" in preset:
        family.daily_mission_limit = preset["daily_mission_limit"]
    family.is_active = True
