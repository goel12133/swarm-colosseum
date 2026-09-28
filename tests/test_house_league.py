"""House league tests: the caps, the validator, the retirement rule, and the dry run."""
import json
from pathlib import Path

import pytest

from colosseum import house_league as hl

ROOT = Path(__file__).resolve().parents[1]


# --- spend caps ---------------------------------------------------------------

def test_a_call_that_would_exceed_the_dollar_cap_aborts_before_spending():
    caps = hl.Caps(max_usd=0.001, max_tokens=10_000_000, max_calls=99)
    with pytest.raises(hl.CapExceeded, match="dollar cap"):
        hl.check_caps(caps, hl.Spend(), "a prompt")


def test_a_call_that_would_exceed_the_token_cap_aborts_before_spending():
    caps = hl.Caps(max_usd=1000.0, max_tokens=100, max_calls=99)
    with pytest.raises(hl.CapExceeded, match="token cap"):
        hl.check_caps(caps, hl.Spend(), "a prompt")


def test_the_call_cap_counts_calls_already_made():
    caps = hl.Caps(max_usd=1000.0, max_tokens=10_000_000, max_calls=1)
    spend = hl.Spend(calls=1)
    with pytest.raises(hl.CapExceeded, match="call cap"):
        hl.check_caps(caps, spend, "a prompt")


def test_dry_run_still_respects_the_caps(monkeypatch):
    """A cap that would be exceeded aborts even when no API call would happen."""
    caps = hl.Caps(max_usd=0.0001)
    with pytest.raises(hl.CapExceeded):
        hl.call_model("prompt", caps, hl.Spend(), dry_run=True)


def test_spend_accounting_uses_the_price_table():
    spend = hl.Spend()
    spend.add("claude-opus-5", 1_000_000, 1_000_000)
    assert spend.usd == pytest.approx(5.0 + 25.0)
    assert spend.calls == 1 and spend.tokens == 2_000_000


def test_caps_come_from_the_environment():
    caps = hl.Caps.from_env({"HOUSE_LEAGUE_MAX_USD": "0.5",
                             "HOUSE_LEAGUE_MAX_TOKENS": "1234",
                             "HOUSE_LEAGUE_MAX_CALLS": "2",
                             "HOUSE_LEAGUE_BOTS": "1"})
    assert (caps.max_usd, caps.max_tokens, caps.max_calls, caps.bots_per_night) == \
           (0.5, 1234, 2, 1)


# --- validation ---------------------------------------------------------------

def test_a_bot_with_a_syntax_error_is_rejected():
    ok, _, reason = hl.validate_bot('NAME = "x"\nROLE = "attacker"\ndef act(obs)\n  pass',
                                    "attacker")
    assert not ok and "syntax error" in reason


def test_a_bot_missing_act_is_rejected():
    ok, _, reason = hl.validate_bot('NAME = "x"\nROLE = "attacker"\n', "attacker")
    assert not ok and "act()" in reason


def test_a_bot_with_the_wrong_role_is_rejected():
    ok, _, reason = hl.validate_bot('NAME = "x"\nROLE = "defender"\ndef act(obs):\n    return {}',
                                    "attacker")
    assert not ok and "ROLE" in reason


def test_a_bot_that_imports_a_banned_module_is_rejected():
    src = 'import socket\nNAME = "x"\nROLE = "attacker"\ndef act(obs):\n    return {}'
    ok, _, reason = hl.validate_bot(src, "attacker")
    assert not ok and "socket" in reason


def test_a_good_bot_passes_validation():
    src = 'NAME = "good"\nROLE = "attacker"\ndef act(obs):\n    return {"launch": []}'
    ok, name, reason = hl.validate_bot(src, "attacker")
    assert ok and name == "good" and reason == ""


def test_validation_does_not_execute_the_bot(tmp_path):
    """The host must never run submitted code -- only the container does."""
    marker = tmp_path / "executed"
    src = (f'open({str(marker)!r}, "w").write("x")\n'
           'NAME = "evil"\nROLE = "attacker"\ndef act(obs):\n    return {}')
    hl.validate_bot(src, "attacker")
    assert not marker.exists()


def test_the_canned_response_parses_into_two_valid_bots():
    blocks = hl.extract_bots(hl.CANNED_RESPONSE)
    assert len(blocks) == 2
    assert hl.validate_bot(blocks[0], "attacker")[0]
    assert hl.validate_bot(blocks[1], "defender")[0]


# --- retirement ---------------------------------------------------------------

def test_retirement_fires_after_three_bottom_finishes(tmp_path, monkeypatch):
    house = tmp_path / "house"
    house.mkdir()
    doomed = house / "2026-09-01_attacker_loser.py"
    doomed.write_text('NAME = "2026-09-01_attacker_loser"\nROLE = "attacker"\n'
                      'def act(obs):\n    return {}\n')
    monkeypatch.setattr(hl, "HOUSE", house)
    monkeypatch.setattr(hl, "RETIRED", house / "RETIRED")

    history = {"nights": [
        {"date": "2026-09-01", "attacker_bottom": "2026-09-01_attacker_loser",
         "defender_bottom": "someone_else"},
        {"date": "2026-09-02", "attacker_bottom": "2026-09-01_attacker_loser",
         "defender_bottom": "someone_else"},
        {"date": "2026-09-03", "attacker_bottom": "2026-09-01_attacker_loser",
         "defender_bottom": "another"},
    ]}
    retired = hl.apply_retirement(history)
    assert retired == ["2026-09-01_attacker_loser"]
    assert not doomed.exists()
    assert (house / "RETIRED" / doomed.name).exists()


def test_retirement_does_not_fire_on_two_nights(tmp_path, monkeypatch):
    house = tmp_path / "house"
    house.mkdir()
    bot = house / "b.py"
    bot.write_text('NAME = "b"\nROLE = "attacker"\ndef act(obs):\n    return {}\n')
    monkeypatch.setattr(hl, "HOUSE", house)
    monkeypatch.setattr(hl, "RETIRED", house / "RETIRED")
    history = {"nights": [
        {"date": "d1", "attacker_bottom": "b", "defender_bottom": None},
        {"date": "d2", "attacker_bottom": "b", "defender_bottom": None},
        {"date": "d3", "attacker_bottom": "other", "defender_bottom": None},
    ]}
    assert hl.apply_retirement(history) == []
    assert bot.exists()


# --- context ------------------------------------------------------------------

def test_context_and_prompt_are_built_from_real_results():
    ctx = hl.gather_context()
    assert ctx["leaderboard"]["attackers"] and ctx["matrix"]
    prompt = hl.build_prompt(ctx)
    for needed in ("score_defender", "ROLE", "striker", "fenced Python code blocks"):
        assert needed in prompt
    assert len(prompt) > 1500
