"""ai._complete runs `claude -p` on the subscription login, never an API key."""
import json
import stat

import pytest

import ai


def fake_claude(tmp_path, body):
    script = tmp_path / "claude"
    script.write_text("#!/usr/bin/env python3\n" + body)
    script.chmod(script.stat().st_mode | stat.S_IEXEC)
    return str(script)


ECHO = """import json, os, sys
prompt = sys.stdin.read()
print(json.dumps({"is_error": False, "result": json.dumps({
    "argv": sys.argv[1:], "prompt": prompt,
    "api_key": os.environ.get("ANTHROPIC_API_KEY"), "cwd": os.getcwd()})}))
"""


def test_complete_passes_system_prompt_and_strips_api_key(tmp_path, monkeypatch):
    monkeypatch.setattr(ai.config, "CLAUDE_BIN", fake_claude(tmp_path, ECHO))
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-should-not-leak")
    out = json.loads(ai._complete("SYS", "hello", "sonnet"))
    argv = out["argv"]
    assert argv[:3] == ["-p", "--system-prompt", "SYS"]
    assert argv[argv.index("--tools") + 1] == ""
    assert argv[argv.index("--setting-sources") + 1] == ""
    assert argv[argv.index("--model") + 1] == "sonnet"
    assert out["prompt"] == "hello"
    assert out["api_key"] is None


def test_complete_raises_on_cli_error(tmp_path, monkeypatch):
    body = 'import json; print(json.dumps({"is_error": True, "result": "usage limit reached"}))\n'
    monkeypatch.setattr(ai.config, "CLAUDE_BIN", fake_claude(tmp_path, body))
    with pytest.raises(ai.AIError, match="usage limit"):
        ai._complete("SYS", "hello")


def test_complete_raises_on_non_json(tmp_path, monkeypatch):
    body = 'import sys; sys.stderr.write("Not logged in"); sys.exit(1)\n'
    monkeypatch.setattr(ai.config, "CLAUDE_BIN", fake_claude(tmp_path, body))
    with pytest.raises(ai.AIError, match="Not logged in"):
        ai._complete("SYS", "hello")
