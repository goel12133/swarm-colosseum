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
    monkeypatch.setattr(hl, "NIGHTS", tmp_path / "nights.jsonl")
    monkeypatch.setattr(hl, "ALERT", tmp_path / "ALERT.md")


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
    for needed in ("score_defender", "ROLE", "striker", "one fenced Python code block"):
        assert needed in prompt
    assert len(prompt) > 1500


@pytest.mark.parametrize("fence", ["```python\n", "```py\n", "```Python \r\n", "```\n"])
def test_code_fence_variants_are_all_extracted(fence):
    assert hl.extract_bots(f"text\n{fence}NAME = 'x'\n```\n") == ["NAME = 'x'"]


def test_cli_input_estimate_covers_the_observed_real_calls():
    """(prompt chars, actual input tokens) of real calls from the log, 2026-09-29..10-03,
    including the two that retried after a safety check. The guard must never be lower."""
    observed = [(12332, 5816), (6335, 2965), (10618, 4766), (8811, 3856), (17363, 7912),
                (17526, 15999), (17157, 15819), (17320, 7929), (20668, 9445), (18820, 8215)]
    for chars, actual in observed:
        assert hl.estimate_input_tokens("x" * chars, "cli") >= actual, (chars, actual)


def test_a_house_bot_at_the_top_is_not_recorded_as_bottom(tmp_path, monkeypatch):
    house = tmp_path / "house"
    house.mkdir()
    (house / "champ.py").write_text('NAME = "champ"\nROLE = "defender"\n')
    monkeypatch.setattr(hl, "HOUSE", house)
    lb = {"attackers": [{"name": "rush"}],
          "defenders": [{"name": "champ"}, {"name": "gun_only"}]}
    night = hl.record_night({"nights": []}, lb, "d")["nights"][0]
    assert night["defender_bottom"] is None and night["attacker_bottom"] is None


# --- personas -----------------------------------------------------------------

from colosseum import personas as P  # noqa: E402


def toy_ctx(top_def_win=1.0, top_att_win=0.5):
    lb = {"attackers": [dict(name="a_top", elo=1100, win_rate=top_att_win, mean_cer=1.0,
                             mean_score=0.6),
                        dict(name="a_low", elo=900, win_rate=0.2, mean_cer=1.0,
                             mean_score=0.4)],
          "defenders": [dict(name="d_top", elo=1200, win_rate=top_def_win, mean_cer=1.0,
                             mean_score=0.7),
                        dict(name="d_low", elo=900, win_rate=0.3, mean_cer=1.0,
                             mean_score=0.3)]}
    matrix = {"a_top": {"d_top": 0.7, "d_low": 0.1},     # d_low's worst result: 0.1
              "a_low": {"d_top": 0.9, "d_low": 0.4}}     # a_low's worst result: 0.9
    return dict(leaderboard=lb, matrix=matrix, lopsided=[], rules={})


def test_counter_meta_has_no_threshold_and_always_targets_the_number_one():
    """Decided 2026-09-29: no win-rate trigger; counter_meta is in the rotation."""
    ctx = toy_ctx(top_def_win=0.5, top_att_win=0.5)
    assert "counter_meta" in P.ROTATION
    night = next(n for n in range(4) if P.choose("attacker", ctx, n) == "counter_meta")
    assert P.target_for("counter_meta", "attacker", ctx) == "d_top"
    assert P.choose("defender", ctx, night) != "counter_meta"


def test_escalation_after_two_unbeaten_nights_takes_both_slots():
    ctx = toy_ctx()
    # d_top: every attacker scores below 0.5 against it (score_defender > 0.5) on two nights
    night = {"a_top": {"d_top": 0.7, "d_low": 0.1}, "a_low": {"d_top": 0.9, "d_low": 0.4}}
    assert P.unbeaten(night)["defender"] == ["d_top"]
    plan = P.plan_night(ctx, nights=5, last_two_matrices=[night, night])
    assert plan == [("attacker", "counter_meta", "d_top", "escalation")] * 2
    # one unbeaten night is not enough
    plan = P.plan_night(ctx, nights=5, last_two_matrices=[
        {"a_top": {"d_top": 0.3, "d_low": 0.1}, "a_low": {"d_top": 0.9, "d_low": 0.4}}, night])
    assert [p[3] for p in plan] == ["", ""] and [p[0] for p in plan] == ["attacker", "defender"]


def test_only_one_side_can_be_unbeaten_on_a_night():
    import itertools
    import random as _r
    rng = _r.Random(0)
    for _ in range(2000):
        m = {f"a{i}": {f"d{j}": rng.choice([0.2, 0.4, 0.6, 0.8]) for j in range(3)}
             for i in range(3)}
        u = P.unbeaten(m)
        assert not (u["attacker"] and u["defender"])


def test_without_a_dominant_opponent_personas_rotate_and_differ_within_a_night():
    ctx = toy_ctx(top_def_win=0.5, top_att_win=0.5)
    seen = set()
    for n in range(4):
        a, d = P.choose("attacker", ctx, n), P.choose("defender", ctx, n)
        assert a != d
        seen.add(a)
    assert seen == set(P.ROTATION)


def test_persona_override_and_bad_names():
    ctx = toy_ctx(top_def_win=1.0)
    assert P.choose("attacker", ctx, 0, "attacker=contrarian") == "contrarian"
    with pytest.raises(ValueError):
        P.choose("attacker", ctx, 0, "attacker=nonsense")


def test_persona_targets():
    ctx = toy_ctx()
    assert P.target_for("exploiter", "attacker", ctx) == "d_low"
    assert P.target_for("exploiter", "defender", ctx) == "a_low"
    assert P.target_for("generalist", "attacker", ctx) == "field"
    assert P.target_for("contrarian", "defender", ctx) == "a_top"


@pytest.mark.parametrize("persona", P.PERSONAS)
@pytest.mark.parametrize("role", ["attacker", "defender"])
def test_every_persona_builds_a_prompt_from_real_results(persona, role):
    ctx = hl.gather_context()
    prompt = hl.build_prompt(ctx, role, persona)
    target = P.target_for(persona, role, ctx)
    assert "one fenced Python code block" in prompt and f"ONE bot: " in prompt
    assert f" {role}. Return" in prompt
    if target != "field":
        assert target in prompt


def test_counter_meta_is_shown_the_targets_source_and_its_closest_calls():
    ctx = hl.gather_context()
    top = ctx["leaderboard"]["defenders"][0]["name"]
    prompt = hl.build_prompt(ctx, "attacker", "counter_meta")
    assert P.bot_path(top).read_text().strip()[:200] in prompt
    assert "closest calls" in prompt


def test_judge_scores_from_the_new_bots_side():
    lb = {"attackers": [dict(name="new", mean_score=0.6), dict(name="old", mean_score=0.5)]}
    matrix = {"new": {"d_top": 0.3, "d_low": 0.5}, "old": {"d_top": 0.8, "d_low": 0.2}}
    r = hl.judge("new", dict(role="attacker", target="d_top"), lb, matrix)
    assert r["score_vs_target"] == 0.7 and r["beat_target"] and r["rank"] == 1
    r = hl.judge("new", dict(role="attacker", target="field"), lb, matrix)
    assert r["field_mean"] == 0.6 and r["beat_target"]


ONE_ATTACKER = '''```python
NAME = "fake_att"
ROLE = "attacker"
def act(obs):
    return {"launch": [], "steer": {}}
```'''
ONE_DEFENDER = '''```python
NAME = "fake_def"
ROLE = "defender"
def act(obs):
    return {"intercept": [], "retarget": {}, "gun": None}
```'''


def test_a_night_makes_one_call_per_persona_and_writes_metadata(monkeypatch, tmp_path):
    out = tmp_path / "out"
    out.mkdir()
    for f in ("leaderboard.json", "matrix.json", "BALANCE.md"):
        (out / f).write_text((hl.DEFAULT_OUT / f).read_text())
    house = tmp_path / "house"
    for name, val in [("HOUSE", house), ("RAW", tmp_path / "raw"),
                      ("HISTORY", tmp_path / "history.json")]:
        monkeypatch.setattr(hl, name, val)
    monkeypatch.setattr(hl, "smoke_test", lambda path, role: (True, "ok (stubbed)"))
    monkeypatch.setenv("HOUSE_LEAGUE_PERSONAS", "attacker=counter_meta,defender=generalist")

    prompts = []

    def fake_call(prompt, caps, spend, dry_run):
        prompts.append(prompt)
        spend.add(caps.model, 100, 50, priced=False)
        return ONE_ATTACKER if "ONE bot: an attacker" in prompt else ONE_DEFENDER
    monkeypatch.setattr(hl, "call_model", fake_call)

    today = hl.date.today().isoformat()
    a, d = f"{today}_attacker_fake_att", f"{today}_defender_fake_def"

    def fake_tournament(seeds, out, sandbox, quiet):
        lb = json.loads((hl.DEFAULT_OUT / "leaderboard.json").read_text())
        matrix = json.loads((hl.DEFAULT_OUT / "matrix.json").read_text())["matrix"]
        matrix[a] = {k: 0.4 for k in next(iter(matrix.values()))}
        for row in matrix.values():
            row[d] = 0.6
        lb["attackers"].insert(0, dict(name=a, role="attacker", elo=1300, win_rate=0.6,
                                       mean_score=0.6))
        lb["defenders"].insert(0, dict(name=d, role="defender", elo=1300, win_rate=0.6,
                                       mean_score=0.99))
        (out / "matrix.json").write_text(json.dumps({"matrix": matrix}))
        return lb, matrix, [None] * 3
    monkeypatch.setattr(hl, "run_tournament", fake_tournament)

    summary = hl.run_night(caps=hl.Caps(), out=out)
    assert summary["status"] == "ok" and len(summary["written"]) == 2
    assert len(prompts) == 2 and summary["spend"]["calls"] == 2
    metas = {m["role"]: m for m in (json.loads(p.read_text())
                                    for p in house.glob("*.meta.json"))}
    top_defender = json.loads(
        (hl.DEFAULT_OUT / "leaderboard.json").read_text())["defenders"][0]["name"]
    assert metas["attacker"]["persona"] == "counter_meta"
    assert metas["attacker"]["target"] == top_defender
    assert metas["defender"]["persona"] == "generalist"
    assert metas["defender"]["target"] == "field"
    assert metas["attacker"]["tokens"] == {"input": 100, "output": 50}
    assert metas["attacker"]["result"]["beat_target"] is True      # 1 - 0.4 > 0.5
    assert summary["house_positions"][a]["persona"] == "counter_meta"


# --- night ledger and phases ----------------------------------------------------

def test_every_real_night_is_recorded_even_when_it_fails(monkeypatch):
    fake_cli(monkeypatch, stdout=CLI_LOGGED_OUT, returncode=1)
    hl.run_night(caps=hl.Caps())
    rows = [json.loads(l) for l in hl.NIGHTS.read_text().splitlines()]
    assert len(rows) == 1 and rows[0]["status"] == "error"
    assert "Not logged in" in rows[0]["reason"]
    assert "generation" in rows[0]["phases"]


def test_an_unexpected_crash_is_a_logged_failure_not_a_traceback(monkeypatch):
    def boom(out=None):
        raise KeyError("leaderboard missing a field")
    monkeypatch.setattr(hl, "gather_context", boom)
    summary = hl.run_night(caps=hl.Caps())
    assert summary["status"] == "error" and "KeyError" in summary["reason"]
    assert "ABORT: unexpected KeyError" in hl.LOG.read_text()
    assert json.loads(hl.NIGHTS.read_text())["status"] == "error"


def test_phases_accumulate():
    p = hl.Phases()
    with p("smoke"):
        pass
    with p("smoke"):
        pass
    assert set(p.seconds) == {"smoke"} and p.seconds["smoke"] >= 0


def test_snapshot_keeps_the_nights_ladder(tmp_path):
    for name in hl.SNAPSHOT_FILES:
        (tmp_path / name).write_text("{}")
    hl.snapshot(tmp_path, "2026-10-01")
    assert sorted(p.name for p in (tmp_path / "history" / "2026-10-01").iterdir()) == \
        sorted(hl.SNAPSHOT_FILES)


# --- coverage-aware retirement ---------------------------------------------------

def three_bottom_nights(name, key="attacker_bottom"):
    return {"nights": [{"date": f"d{i}", key: name,
                        ("defender_bottom" if key == "attacker_bottom" else "attacker_bottom"):
                        None} for i in range(3)]}


def house_with(tmp_path, monkeypatch, name, role):
    house = tmp_path / "house"
    house.mkdir(exist_ok=True)
    (house / f"{name}.py").write_text(f'NAME = "{name}"\nROLE = "{role}"\n')
    monkeypatch.setattr(hl, "HOUSE", house)
    monkeypatch.setattr(hl, "SUBMITTED", tmp_path / "submitted")
    return house


def test_a_bottom_bot_that_uniquely_breaches_someone_is_exempt(tmp_path, monkeypatch):
    house = house_with(tmp_path, monkeypatch, "weird", "attacker")
    breaches = {"seeds": 10, "breaches": {
        "weird": {"fortress": 1, "layered": 0},      # the only one through the fortress
        "rush": {"fortress": 0, "layered": 4},
        "flanker": {"fortress": 0, "layered": 9}}}
    assert hl.unique_coverage("weird", "attacker", breaches) == ["fortress"]
    assert hl.apply_retirement(three_bottom_nights("weird"), breaches=breaches) == []
    assert (house / "weird.py").exists()
    assert "exempt weird from retirement" in hl.LOG.read_text()
    assert "breaches fortress" in hl.LOG.read_text()


def test_a_bottom_bot_whose_coverage_is_shared_is_retired(tmp_path, monkeypatch):
    house = house_with(tmp_path, monkeypatch, "weird", "attacker")
    breaches = {"seeds": 10, "breaches": {
        "weird": {"fortress": 1, "layered": 0},
        "rush": {"fortress": 2, "layered": 4},       # rush gets through the fortress too
        "flanker": {"fortress": 0, "layered": 9}}}
    assert hl.unique_coverage("weird", "attacker", breaches) == []
    assert hl.apply_retirement(three_bottom_nights("weird"), breaches=breaches) == ["weird"]
    assert (house / "RETIRED" / "weird.py").exists()


def test_a_defender_that_uniquely_stops_someone_is_exempt(tmp_path, monkeypatch):
    house = house_with(tmp_path, monkeypatch, "wall", "defender")
    breaches = {"seeds": 10, "breaches": {
        "rush": {"wall": 9, "layered": 10, "gun_only": 10},   # only wall ever holds rush
        "flanker": {"wall": 10, "layered": 3, "gun_only": 10}}}
    assert hl.unique_coverage("wall", "defender", breaches) == ["rush"]
    assert hl.apply_retirement(three_bottom_nights("wall", "defender_bottom"),
                               breaches=breaches) == []
    assert "the only live bot that stops rush" in hl.LOG.read_text()


def test_a_failed_night_writes_alert_and_a_good_night_clears_it(monkeypatch, tmp_path):
    fake_cli(monkeypatch, stdout=CLI_LOGGED_OUT, returncode=1)
    hl.run_night(caps=hl.Caps())
    alert = hl.ALERT.read_text()
    assert "Not logged in" in alert and "Last 30 log lines" in alert
    monkeypatch.setattr(hl, "_run_night", lambda *a: dict(status="ok", spend={}))
    hl.run_night(caps=hl.Caps())
    assert not hl.ALERT.exists()


def test_a_dry_run_never_touches_the_alert(monkeypatch):
    hl.ALERT.write_text("from a real failure")
    monkeypatch.setattr(hl, "_run_night", lambda *a: dict(status="ok", spend={}))
    hl.run_night(caps=hl.Caps(), dry_run=True)
    assert hl.ALERT.read_text() == "from a real failure"


# --- evidence budgets (charter 3.2) ----------------------------------------------

@pytest.mark.parametrize("persona", P.PERSONAS)
@pytest.mark.parametrize("role", ["attacker", "defender"])
def test_evidence_stays_inside_the_persona_budget(persona, role):
    from colosseum.prompts import generator as G
    ctx = hl.gather_context()
    target = P.target_for(persona, role, ctx)
    text, info = P.evidence_with_budget(persona, role, target, ctx, hl.DEFAULT_OUT)
    budget, order = G.BUDGETS[persona]
    assert info["budget"] == budget and info["used"] <= budget
    assert info["included"], "the most informative item always goes in"
    assert info["included"][0].split(" ")[0] == next(
        n for n in order if not (target == "field" and n in ("source", "closest", "row",
                                                             "target_doc")))


def test_counter_meta_gets_the_source_first_and_two_closest_calls():
    ctx = hl.gather_context()
    target = ctx["leaderboard"]["defenders"][0]["name"]
    text, info = P.evidence_with_budget("counter_meta", "attacker", target, ctx,
                                        hl.DEFAULT_OUT)
    assert info["included"][:2] == ["source", "closest"]
    assert P.bot_path(target).read_text().strip()[:200] in text


def test_standings_are_capped_but_keep_the_target():
    lb = {"attackers": [dict(name=f"a{i}", elo=1000 - i, win_rate=0.5, mean_cer=1.0)
                        for i in range(9)],
          "defenders": [dict(name="d0", elo=1, win_rate=0.5, mean_cer=1.0)]}
    s = P.standings(lb, keep=("a8",))
    assert "a4" in s and "a5" not in s and "a8" in s and "... and 3 more" in s


def test_the_budget_is_recorded_in_bot_metadata(monkeypatch, tmp_path):
    out = tmp_path / "out"
    out.mkdir()
    for f in ("leaderboard.json", "matrix.json", "BALANCE.md"):
        (out / f).write_text((hl.DEFAULT_OUT / f).read_text())
    for name, val in [("HOUSE", tmp_path / "house"), ("RAW", tmp_path / "raw"),
                      ("HISTORY", tmp_path / "history.json")]:
        monkeypatch.setattr(hl, name, val)
    monkeypatch.setattr(hl, "smoke_test", lambda path, role: (True, "ok"))
    monkeypatch.setattr(hl, "call_model", lambda *a: ONE_ATTACKER)
    monkeypatch.setattr(hl, "run_tournament", lambda **kw: pytest.skip("not needed"))
    monkeypatch.setenv("HOUSE_LEAGUE_PERSONAS", "attacker=counter_meta,defender=generalist")
    try:
        hl.run_night(caps=hl.Caps(bots_per_night=1), out=out)
    except pytest.skip.Exception:
        pass
    meta = json.loads(next((tmp_path / "house").glob("*.meta.json")).read_text())
    assert meta["evidence"]["budget"] == 4000 and meta["prompt_version"] == "2026-10-03.1"
