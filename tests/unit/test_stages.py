import pytest

from call_center.graph import STAGES


@pytest.mark.parametrize("stage", STAGES, ids=lambda m: m.NAME)
def test_stage_returns_its_own_name(stage):
    result = stage.run({"source_file": "x.wav", "stages_completed": []})
    assert stage.NAME in result["stages_completed"]


def test_stages_has_seven_unique_names():
    names = [m.NAME for m in STAGES]
    assert len(names) == 7
    assert len(set(names)) == 7
