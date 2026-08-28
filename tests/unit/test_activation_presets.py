from app.services.activation_presets import ACTIVATION_PRESETS, get_preset


def test_standard_preset_minimal_features():
    preset = get_preset("standard")
    assert preset["rewards_enabled"] is False
    assert preset["mission_evidence_enabled"] is False
    assert preset["daily_mission_limit"] == 5


def test_family_preset_full_features():
    preset = get_preset("family")
    assert preset["rewards_enabled"] is True
    assert preset["quiz_enabled"] is True
    assert preset["daily_mission_limit"] is None


def test_both_presets_active():
    for key in ("standard", "family"):
        assert ACTIVATION_PRESETS[key]["is_active"] is True
