"""Apply plan feature presets to a family."""

from app.models.models import Family, Plan


def apply_plan_features(family: Family, plan: Plan) -> None:
    preset = plan.feature_preset or {}
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
