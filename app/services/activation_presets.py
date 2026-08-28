"""Hardcoded activation presets — replaced by plan_presets.py when billing (Fase D) ships."""

from typing import Literal, TypedDict

ActivationPresetKey = Literal["standard", "family"]


class ActivationPresetFeatures(TypedDict):
    is_active: bool
    rewards_enabled: bool
    mission_evidence_enabled: bool
    quiz_enabled: bool
    chat_enabled: bool
    agenda_enabled: bool
    daily_mission_limit: int | None


PRESET_LABELS: dict[ActivationPresetKey, str] = {
    "standard": "Standar",
    "family": "Family",
}

ACTIVATION_PRESETS: dict[ActivationPresetKey, ActivationPresetFeatures] = {
    "standard": {
        "is_active": True,
        "rewards_enabled": False,
        "mission_evidence_enabled": False,
        "quiz_enabled": False,
        "chat_enabled": False,
        "agenda_enabled": False,
        "daily_mission_limit": 5,
    },
    "family": {
        "is_active": True,
        "rewards_enabled": True,
        "mission_evidence_enabled": True,
        "quiz_enabled": True,
        "chat_enabled": True,
        "agenda_enabled": True,
        "daily_mission_limit": None,
    },
}


def get_preset(key: ActivationPresetKey) -> ActivationPresetFeatures:
    return ACTIVATION_PRESETS[key]
