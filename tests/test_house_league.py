"""House league tests: the caps, the backends, the validator, the retirement rule."""
import json
import subprocess
from pathlib import Path

import pytest

from colosseum import house_league as hl

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(autouse=True)
def private_log(tmp_path, monkeypatch):
    """Tests must not write into the real out/house_league.log."""
    monkeypatch.setattr(hl, "LOG", tmp_path / "house_league.log")


# --- spend caps ---------------------------------------------------------------

def test_a_call_that_would_exceed_the_dollar_cap_aborts_before_spending():
    caps = hl.Caps(max_usd=0.001, max_tokens=10_000_000, max_calls=99, backend="api")
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
    caps = hl.Caps(max_tokens=100)
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


def test_the_cli_backend_has_no_dollar_cap():
    """Subscription calls cost nothing per call, so only tokens and calls are capped."""
    caps = hl.Caps(max_usd=0.0, max_tokens=10_000_000, max_calls=99, backend="cli")
    hl.check_caps(caps, hl.Spend(), "a prompt")


def test_cli_is_the_default_backend_and_api_is_behind_a_flag():
    assert hl.Caps.from_env({}).backend == "cli"
    assert hl.Caps.from_env({}).model == hl.DEFAULT_CLI_MODEL
    api = hl.Caps.from_env({}, backend="api")
    assert api.backend == "api" and api.model == hl.DEFAULT_MODEL
    assert hl.Caps.from_env({"HOUSE_LEAGUE_BACKEND": "api"}).backend == "api"
    with pytest.raises(ValueError):
        hl.Caps.from_env({"HOUSE_LEAGUE_BACKEND": "nonsense"})


# --- cli backend --------------------------------------------------------------

CLI_OK = json.dumps({"type": "result", "is_error": False, "result": hl.CANNED_RESPONSE,
                     "usage": {"input_tokens": 9000, "cache_creation_input_tokens": 0,
                               "cache_read_input_tokens": 0, "output_tokens": 7000},
                     "modelUsage": {"claude-opus-5-5": {}}, "duration_ms": 1000,
                     "total_cost_usd": 0.22})
CLI_LOGGED_OUT = json.dumps({"type": "result", "is_error": True,
                             "result": "Not logged in · Please run /login",
                             "usage": {"input_tokens": 0, "output_tokens": 0}})


def fake_cli(monkeypatch, stdout="", returncode=0, stderr="", raises=None):
    seen = {}

    def run(cmd, prompt, env, timeout):
        seen.update(cmd=cmd, prompt=prompt, env=env)
        if raises:
            raise raises
        return subprocess.CompletedProcess(cmd, returncode, stdout, stderr)
    monkeypatch.setattr(hl, "find_claude", lambda env=None: "/fake/claude")
    monkeypatch.setattr(hl, "run_cli", run)
    return seen


def test_cli_call_returns_the_text_and_counts_tokens_unpriced(monkeypatch):
    seen = fake_cli(monkeypatch, stdout=CLI_OK)
    spend = hl.Spend()
    text = hl.call_model("the prompt", hl.Caps(), spend, dry_run=False)
    assert text == hl.CANNED_RESPONSE
    assert (spend.calls, spend.input_tokens, spend.output_tokens, spend.usd) == \
           (1, 9000, 7000, 0.0)
    assert seen["prompt"] == "the prompt"


def test_cli_child_gets_no_api_key_and_no_parent_session(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-should-not-leak")
    monkeypatch.setenv("CLAUDECODE", "1")
    seen = fake_cli(monkeypatch, stdout=CLI_OK)
    hl.call_model("p", hl.Caps(), hl.Spend(), dry_run=False)
    assert "ANTHROPIC_API_KEY" not in seen["env"] and "CLAUDECODE" not in seen["env"]
    assert seen["env"]["CLAUDE_CODE_MAX_OUTPUT_TOKENS"] == str(hl.MAX_OUTPUT_TOKENS)


def test_cli_command_is_headless_with_no_tools_or_settings():
    cmd = hl.cli_command("claude", hl.Caps())
    assert cmd[:2] == ["claude", "-p"]
    assert cmd[cmd.index("--tools") + 1] == ""
    assert cmd[cmd.index("--setting-sources") + 1] == ""
    for flag in ("--strict-mcp-config", "--no-session-persistence", "--disable-slash-commands"):
        assert flag in cmd
    assert "--bare" not in cmd          # --bare refuses the subscription login


@pytest.mark.parametrize("kwargs, match", [
    (dict(stdout=CLI_LOGGED_OUT, returncode=1), "Not logged in"),
    (dict(stdout="", returncode=1, stderr="boom"), "boom"),
    (dict(stdout="not json", returncode=0), "did not return JSON"),
    (dict(raises=subprocess.TimeoutExpired("claude", 900)), "timed out"),
    (dict(raises=FileNotFoundError("claude")), "not runnable"),
])
def test_cli_failures_raise_backend_error(monkeypatch, kwargs, match):
    fake_cli(monkeypatch, **kwargs)
    with pytest.raises(hl.BackendError, match=match):
        hl.call_model("p", hl.Caps(), hl.Spend(), dry_run=False)


def test_a_missing_cli_binary_is_a_backend_error(tmp_path):
    with pytest.raises(hl.BackendError, match="not found"):
        hl.find_claude({"HOME": str(tmp_path), "PATH": str(tmp_path)})


def test_a_backend_failure_ends_the_night_cleanly(monkeypatch, tmp_path):
    """Logged out at 03:30: a log line, status error, nothing written, no tournament."""
    fake_cli(monkeypatch, stdout=CLI_LOGGED_OUT, returncode=1)
    monkeypatch.setattr(hl, "HOUSE", tmp_path / "house")
    monkeypatch.setattr(hl, "run_tournament",
                        lambda **kw: pytest.fail("tournament must not run"))
    summary = hl.run_night(caps=hl.Caps())
    assert summary["status"] == "error" and "Not logged in" in summary["reason"]
    assert not (tmp_path / "house").exists()
    assert "ABORT" in hl.LOG.read_text()


def test_main_exits_2_on_a_backend_failure(monkeypatch):
    fake_cli(monkeypatch, stdout=CLI_LOGGED_OUT, returncode=1)
    monkeypatch.setattr("sys.argv", ["house_league", "--once"])
    assert hl.main() == 2


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


@pytest.mark.parametrize("fence", ["```python\n", "```py\n", "```Python \r\n", "```\n"])
def test_code_fence_variants_are_all_extracted(fence):
    assert hl.extract_bots(f"text\n{fence}NAME = 'x'\n```\n") == ["NAME = 'x'"]


def test_cli_input_estimate_covers_the_observed_real_calls():
    """Real nights on 2026-09-28 used 2,929 and 5,927 input tokens; the guard must not be lower."""
    prompt = hl.build_prompt(hl.gather_context())
    assert hl.estimate_input_tokens(prompt, "cli") >= 5927


def test_a_house_bot_at_the_top_is_not_recorded_as_bottom(tmp_path, monkeypatch):
    house = tmp_path / "house"
    house.mkdir()
    (house / "champ.py").write_text('NAME = "champ"\nROLE = "defender"\n')
    monkeypatch.setattr(hl, "HOUSE", house)
    lb = {"attackers": [{"name": "rush"}],
          "defenders": [{"name": "champ"}, {"name": "gun_only"}]}
    night = hl.record_night({"nights": []}, lb, "d")["nights"][0]
    assert night["defender_bottom"] is None and night["attacker_bottom"] is None
