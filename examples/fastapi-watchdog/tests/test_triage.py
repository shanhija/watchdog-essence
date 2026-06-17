"""Triage prompt assembly + model-output validation (ESSENCE §6.1, Appendix C)."""
from watchdog.models import ActiveIncident, Candidate
from watchdog.triage import build_user_message, parse_and_validate


def _cand(i, text="boom"):
    return Candidate(id=i, line_fingerprint=f"fp{i}", text=text, labels={"service": "kvstore"}, occurrences=1)


def test_prompt_wraps_data_in_delimiters():
    msg = build_user_message([_cand(101, "KeyError 'x'")], [
        ActiveIncident(id=12, slug="s", severity="high", summary="sum", samples=["a", "b"])
    ])
    assert "<LOG_DATA>" in msg and "</LOG_DATA>" in msg
    assert "<ACTIVE_INCIDENTS>" in msg and "</ACTIVE_INCIDENTS>" in msg
    assert "[id=101]" in msg
    assert "[id=12]" in msg


def test_prompt_truncates_long_lines():
    msg = build_user_message([_cand(1, "x" * 1000)], [], per_line_char_cap=50)
    assert "x" * 1000 not in msg
    assert "x" * 50 in msg


def test_validation_drops_unknown_line_id():
    groupings, dropped = parse_and_validate(
        [{"line_ids": [999], "existing_incident_id": None, "slug": "s",
          "severity": "high", "confidence": "high"}],
        valid_line_ids={1, 2}, valid_incident_ids=set(),
    )
    assert groupings == []
    assert dropped["unknown_line_id"] == 1


def test_validation_drops_unknown_incident_id():
    groupings, dropped = parse_and_validate(
        [{"line_ids": [1], "existing_incident_id": 777}],
        valid_line_ids={1}, valid_incident_ids={12},
    )
    assert groupings == []
    assert dropped["unknown_incident_id"] == 1


def test_validation_keeps_partial_output():
    groupings, dropped = parse_and_validate(
        [
            {"line_ids": [1], "existing_incident_id": None, "slug": "good",
             "severity": "high", "confidence": "high"},
            {"line_ids": [999], "existing_incident_id": None, "slug": "bad",
             "severity": "high", "confidence": "high"},
        ],
        valid_line_ids={1}, valid_incident_ids=set(),
    )
    assert len(groupings) == 1
    assert groupings[0].slug == "good"
    assert dropped["unknown_line_id"] == 1


def test_validation_drops_empty_line_ids():
    groupings, dropped = parse_and_validate(
        [{"line_ids": [], "existing_incident_id": None}],
        valid_line_ids={1}, valid_incident_ids=set(),
    )
    assert groupings == []
    assert dropped["empty_line_ids"] == 1


def test_link_grouping_recognized():
    groupings, _ = parse_and_validate(
        [{"line_ids": [1], "existing_incident_id": 12}],
        valid_line_ids={1}, valid_incident_ids={12},
    )
    assert groupings[0].is_link
    assert groupings[0].existing_incident_id == 12
