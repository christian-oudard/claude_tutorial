#!/usr/bin/env python3
"""
Permission tests for Claude Code sandbox configuration.

Each test runs a claude command and checks if it succeeds or fails as expected.
"""

import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from claude_runner import run, ClaudeError

SETTINGS_FILE = Path(__file__).parent / "settings.json"
PROJECT_DIR = Path(__file__).parent


@dataclass
class TestResult:
    name: str
    expected: Literal["pass", "fail", "skip"]
    actual: Literal["pass", "fail", "skip"]
    details: str = ""

    @property
    def ok(self) -> bool:
        return self.expected == self.actual

    @property
    def skipped(self) -> bool:
        return self.expected == "skip"


DEBUG = "-d" in sys.argv or "--debug" in sys.argv


def run_claude(
    prompt: str,
    *,
    allowed_tools: list[str] | None = None,
    disallowed_tools: list[str] | None = None,
    timeout: float = 60,
    setting_sources: list[str] | None = None,
) -> tuple[bool, str]:
    """Run claude with a prompt and return (success, output)."""
    try:
        response = run(
            prompt,
            allowed_tools=allowed_tools,
            disallowed_tools=disallowed_tools,
            model="haiku",
            max_turns=2,
            timeout=timeout,
            cwd=PROJECT_DIR,
            settings_file=SETTINGS_FILE,
            setting_sources=setting_sources,
        )
        if DEBUG:
            print(f"\n  [DEBUG] raw={response.raw}")
        return True, response.result
    except ClaudeError as e:
        if DEBUG:
            print(f"\n  [DEBUG] error raw={e.raw}")
        return False, str(e)


def test_read_local_file() -> TestResult:
    """Test: Can read files in current directory."""
    success, output = run_claude(
        "Read 'test_permissions.py'. Reply 'SUCCESS' if you see its contents.",
        allowed_tools=["Read"],
    )
    passed = success and "SUCCESS" in output.upper()
    return TestResult(
        name="Read local file (./**)",
        expected="pass",
        actual="pass" if passed else "fail",
        details="" if passed else f"success={success}, output={repr(output[:500])}",
    )


def test_read_claude_config_blocked() -> TestResult:
    """Test: Cannot read ~/.claude/ directory (security)."""
    _, output = run_claude(
        "Read '/home/christian/.claude/settings.json'. Reply 'SUCCESS' if you see its contents, 'BLOCKED' if you cannot.",
        allowed_tools=["Read"],
    )
    return TestResult(
        name="Read ~/.claude/ (should fail)",
        expected="fail",
        actual="fail" if "BLOCKED" in output.upper() or "SUCCESS" not in output.upper() else "pass",
        details=output[:200],
    )


def test_read_tmp_claude() -> TestResult:
    """Test: Can read /tmp/claude/ directory."""
    os.makedirs("/tmp/claude", exist_ok=True)
    with open("/tmp/claude/test_read.txt", "w") as f:
        f.write("test content")

    success, output = run_claude(
        "Read '/tmp/claude/test_read.txt'. Reply 'SUCCESS' if you see 'test content'.",
        allowed_tools=["Read"],
    )
    return TestResult(
        name="Read /tmp/claude/",
        expected="pass",
        actual="pass" if success and "SUCCESS" in output.upper() else "fail",
        details=output[:200] if not success else "",
    )


def test_read_etc_passwd() -> TestResult:
    """Test: Cannot read /etc/passwd (outside allowlist)."""
    _, output = run_claude(
        "Read '/etc/passwd'. Reply 'SUCCESS' if you see its contents, 'BLOCKED' if you cannot.",
        allowed_tools=["Read"],
        setting_sources=[],  # Don't load user/project/local, only explicit settings file
    )
    return TestResult(
        name="Read /etc/passwd (should fail)",
        expected="fail",
        actual="fail" if "BLOCKED" in output.upper() or "SUCCESS" not in output.upper() else "pass",
        details=output[:200],
    )


def test_read_other_home() -> TestResult:
    """Test: Cannot read /root or other user directories."""
    _, output = run_claude(
        "Read '/root/.bashrc'. Reply 'SUCCESS' if you see its contents, 'BLOCKED' if you cannot.",
        allowed_tools=["Read"],
    )
    return TestResult(
        name="Read /root/.bashrc (should fail)",
        expected="fail",
        actual="fail" if "BLOCKED" in output.upper() or "SUCCESS" not in output.upper() else "pass",
        details=output[:200],
    )


def test_write_local_file() -> TestResult:
    """Test: Can write files in current directory."""
    test_file = "test_write_output.txt"
    _, output = run_claude(
        f"Write 'hello from claude' to '{test_file}'. Reply 'SUCCESS' if done.",
        allowed_tools=["Write"],
    )
    file_exists = os.path.exists(test_file)
    if file_exists:
        os.remove(test_file)
    return TestResult(
        name="Write local file (./**)",
        expected="pass",
        actual="pass" if file_exists else "fail",
        details=output[:200] if not file_exists else "",
    )


def test_edit_local_file() -> TestResult:
    """Test: Can edit files in current directory."""
    test_file = "test_edit_target.txt"
    with open(test_file, "w") as f:
        f.write("original content")

    _, output = run_claude(
        f"Read '{test_file}', then edit it to change 'original' to 'modified'. Reply 'SUCCESS' if done.",
        allowed_tools=["Read", "Edit"],
    )

    content = ""
    if os.path.exists(test_file):
        with open(test_file) as f:
            content = f.read()
        os.remove(test_file)

    return TestResult(
        name="Edit local file (./**)",
        expected="pass",
        actual="pass" if "modified" in content else "fail",
        details=output[:200] if "modified" not in content else "",
    )


def test_write_own_settings_blocked() -> TestResult:
    """Test: Cannot write to .claude/settings.local.json."""
    _, output = run_claude(
        "Write 'test' to '.claude/settings.local.json'. Reply 'SUCCESS' if done, 'BLOCKED' if you cannot.",
        allowed_tools=["Write"],
    )
    return TestResult(
        name="Write .claude/settings.local.json (should fail)",
        expected="fail",
        actual="fail" if "BLOCKED" in output.upper() or "SUCCESS" not in output.upper() else "pass",
        details=output[:200],
    )


def test_edit_own_settings_blocked() -> TestResult:
    """Test: Cannot edit .claude/settings.local.json."""
    _, output = run_claude(
        "Read '.claude/settings.local.json', then edit it to change 'enabled' to 'disabled'. Reply 'SUCCESS' if done, 'BLOCKED' if you cannot.",
        allowed_tools=["Read", "Edit"],
    )
    return TestResult(
        name="Edit .claude/settings.local.json (should fail)",
        expected="fail",
        actual="fail" if "BLOCKED" in output.upper() or "SUCCESS" not in output.upper() else "pass",
        details=output[:200],
    )


def test_write_global_settings_blocked() -> TestResult:
    """Test: Cannot write to ~/.claude/settings.json."""
    _, output = run_claude(
        "Write 'test' to '/home/christian/.claude/settings.json'. Reply 'SUCCESS' if done, 'BLOCKED' if you cannot.",
        allowed_tools=["Write"],
    )
    return TestResult(
        name="Write ~/.claude/settings.json (should fail)",
        expected="fail",
        actual="fail" if "BLOCKED" in output.upper() or "SUCCESS" not in output.upper() else "pass",
        details=output[:200],
    )


def test_edit_global_settings_blocked() -> TestResult:
    """Test: Cannot edit ~/.claude/settings.json."""
    _, output = run_claude(
        "Read '/home/christian/.claude/settings.json', then edit it to add a comment. Reply 'SUCCESS' if done, 'BLOCKED' if you cannot.",
        allowed_tools=["Read", "Edit"],
    )
    return TestResult(
        name="Edit ~/.claude/settings.json (should fail)",
        expected="fail",
        actual="fail" if "BLOCKED" in output.upper() or "SUCCESS" not in output.upper() else "pass",
        details=output[:200],
    )


def test_bash_ls() -> TestResult:
    """Test: Can run ls command."""
    success, output = run_claude(
        "Run 'ls -la' and reply 'SUCCESS' if you see file listings.",
        allowed_tools=["Bash"],
    )
    return TestResult(
        name="Bash ls command",
        expected="pass",
        actual="pass" if success and "SUCCESS" in output.upper() else "fail",
        details=output[:200] if not success else "",
    )


def test_bash_cat_blocked() -> TestResult:
    """Test: cat command should be blocked."""
    _, output = run_claude(
        "Run 'cat test_permissions.py'. Reply 'SUCCESS' if you see the file, 'BLOCKED' if not allowed.",
        allowed_tools=["Bash"],
    )
    return TestResult(
        name="Bash cat (should be blocked)",
        expected="fail",
        actual="fail" if "BLOCKED" in output.upper() or "not allowed" in output.lower() else "pass",
        details=output[:200],
    )


def test_python_execution() -> TestResult:
    """Test: Can run Python code."""
    success, output = run_claude(
        "Run 'python3 -c \"print(2+2)\"' and reply 'SUCCESS' if you see '4'.",
        allowed_tools=["Bash"],
    )
    return TestResult(
        name="Python execution",
        expected="pass",
        actual="pass" if success and "SUCCESS" in output.upper() else "fail",
        details=output[:200] if not success else "",
    )


def test_uv_available() -> TestResult:
    """Test: Can use uv package manager."""
    success, output = run_claude(
        "Run 'uv --version' and reply 'SUCCESS' if you see a version number.",
        allowed_tools=["Bash"],
    )
    return TestResult(
        name="uv package manager",
        expected="pass",
        actual="pass" if success and "SUCCESS" in output.upper() else "fail",
        details=output[:200] if not success else "",
    )


def test_pip_blocked() -> TestResult:
    """Test: pip should be blocked."""
    _, output = run_claude(
        "Run 'pip --version'. Reply 'SUCCESS' if it works, 'BLOCKED' if not allowed.",
        allowed_tools=["Bash"],
    )
    return TestResult(
        name="pip (should be blocked)",
        expected="fail",
        actual="fail" if "BLOCKED" in output.upper() or "not allowed" in output.lower() or "denied" in output.lower() else "pass",
        details=output[:200],
    )


def test_npm_blocked() -> TestResult:
    """Test: npm should be blocked."""
    _, output = run_claude(
        "Run 'npm --version'. Reply 'SUCCESS' if it works, 'BLOCKED' if not allowed.",
        allowed_tools=["Bash"],
    )
    return TestResult(
        name="npm (should be blocked)",
        expected="fail",
        actual="fail" if "BLOCKED" in output.upper() or "not allowed" in output.lower() or "denied" in output.lower() else "pass",
        details=output[:200],
    )


def test_cargo_available() -> TestResult:
    """Test: Can use cargo."""
    success, output = run_claude(
        "Run 'cargo --version' and reply 'SUCCESS' if you see a version number.",
        allowed_tools=["Bash"],
    )
    return TestResult(
        name="cargo (Rust)",
        expected="pass",
        actual="pass" if success and "SUCCESS" in output.upper() else "fail",
        details=output[:200] if not success else "",
    )


def test_git_status() -> TestResult:
    """Test: Can run git status."""
    success, output = run_claude(
        "Run 'git status' and reply 'SUCCESS' if you see git output.",
        allowed_tools=["Bash"],
    )
    return TestResult(
        name="git status",
        expected="pass",
        actual="pass" if success and "SUCCESS" in output.upper() else "fail",
        details=output[:200] if not success else "",
    )


def test_git_commit_dry() -> TestResult:
    """Test: Can run git commit (dry-run style check)."""
    _, output = run_claude(
        "Run 'git commit --dry-run -m \"test\"'. Reply 'SUCCESS' if allowed (even if nothing to commit), 'BLOCKED' if denied.",
        allowed_tools=["Bash"],
    )
    return TestResult(
        name="git commit (allowed)",
        expected="pass",
        actual="pass" if "BLOCKED" not in output.upper() else "fail",
        details=output[:200],
    )


def test_git_push_blocked() -> TestResult:
    """Test: git push should not be in the allowlist."""
    _, output = run_claude(
        "Check if you can run 'git push'. Reply 'ALLOWED' if permitted, 'BLOCKED' if not.",
        allowed_tools=["Bash"],
    )
    return TestResult(
        name="git push (should be blocked)",
        expected="fail",
        actual="fail" if "BLOCKED" in output.upper() else "pass",
        details=output[:200],
    )


def test_web_fetch_allowed() -> TestResult:
    """Test: Can fetch from allowed domains."""
    success, output = run_claude(
        "Fetch 'https://docs.python.org/3/' and reply 'SUCCESS' if you can access it.",
        allowed_tools=["WebFetch"],
    )
    return TestResult(
        name="WebFetch allowed domain",
        expected="pass",
        actual="pass" if success and "SUCCESS" in output.upper() else "fail",
        details=output[:200] if not success else "",
    )


def test_web_search() -> TestResult:
    """Test: Can use web search."""
    success, output = run_claude(
        "Search for 'python programming' and reply 'SUCCESS' if you get results.",
        allowed_tools=["WebSearch"],
    )
    return TestResult(
        name="WebSearch",
        expected="pass",
        actual="pass" if success and "SUCCESS" in output.upper() else "fail",
        details=output[:200] if not success else "",
    )


def test_mcp_crawl4ai() -> TestResult:
    """Test: Can use crawl4ai MCP tools."""
    success, output = run_claude(
        "Use mcp__c4ai-sse__md to fetch 'https://docs.python.org/3/' and reply 'SUCCESS' if you get markdown.",
        allowed_tools=["mcp__c4ai-sse__md"],
    )
    return TestResult(
        name="Crawl4AI MCP",
        expected="pass",
        actual="pass" if success and "SUCCESS" in output.upper() else "fail",
        details=output[:200] if not success else "",
    )


def test_sudo_blocked() -> TestResult:
    """Test: sudo should be blocked."""
    _, output = run_claude(
        "Run 'sudo ls'. Reply 'SUCCESS' if it works, 'BLOCKED' if not allowed.",
        allowed_tools=["Bash"],
    )
    return TestResult(
        name="sudo (should be blocked)",
        expected="fail",
        actual="fail" if "BLOCKED" in output.upper() or "not allowed" in output.lower() or "denied" in output.lower() else "pass",
        details=output[:200],
    )


def main():
    fail_fast = "-x" in sys.argv or "--fail-fast" in sys.argv

    print("=" * 60)
    print("Claude Code Permission Tests")
    print("=" * 60)
    print()

    tests = [
        ("READ PERMISSIONS", [
            test_read_etc_passwd,
            test_read_other_home,
            test_read_claude_config_blocked,
            test_read_local_file,
            test_read_tmp_claude,
        ]),
        ("WRITE/EDIT PERMISSIONS", [
            test_write_own_settings_blocked,
            test_edit_own_settings_blocked,
            test_write_global_settings_blocked,
            test_edit_global_settings_blocked,
            test_write_local_file,
            test_edit_local_file,
        ]),
        ("BASH COMMANDS", [
            test_bash_cat_blocked,
            test_sudo_blocked,
            test_bash_ls,
        ]),
        ("DEVELOPMENT TOOLS", [
            test_python_execution,
            test_cargo_available,
        ]),
        ("PACKAGE MANAGERS", [
            test_pip_blocked,
            test_npm_blocked,
            test_uv_available,
        ]),
        ("GIT OPERATIONS", [
            test_git_push_blocked,
            test_git_status,
            test_git_commit_dry,
        ]),
        ("WEB ACCESS", [
            test_web_fetch_allowed,
            test_web_search,
            test_mcp_crawl4ai,
        ]),
    ]

    all_results = []

    for category, test_funcs in tests:
        print(f"\n{category}")
        print("-" * 40)

        for test_func in test_funcs:
            print(f"  Running: {test_func.__doc__}", end=" ", flush=True)
            try:
                result = test_func()
                all_results.append(result)

                if result.skipped:
                    print(f"\r  ○ SKIP: {result.name}")
                    if result.details:
                        print(f"    Reason: {result.details[:100]}")
                elif result.ok:
                    print(f"\r  ✓ PASS: {result.name}")
                else:
                    expected_str = f"(expected: {result.expected}, got: {result.actual})"
                    print(f"\r  ✗ FAIL: {result.name} {expected_str}")
                    if result.details:
                        print(f"    Details: {result.details[:100]}...")
                    if fail_fast:
                        print("\n--fail-fast: stopping on first failure")
                        return 1
            except Exception as e:
                print(f"\r  ✗ ERROR: {test_func.__name__}: {e}")
                all_results.append(TestResult(
                    name=test_func.__name__,
                    expected="pass",
                    actual="fail",
                    details=str(e)
                ))
                if fail_fast:
                    print("\n--fail-fast: stopping on first failure")
                    return 1

    print("\n" + "=" * 60)
    passed = sum(1 for r in all_results if r.ok and not r.skipped)
    skipped = sum(1 for r in all_results if r.skipped)
    failed = sum(1 for r in all_results if not r.ok and not r.skipped)
    total = len(all_results)
    print(f"SUMMARY: {passed} passed, {skipped} skipped, {failed} failed (total: {total})")

    if failed > 0:
        print("\nFailed tests:")
        for r in all_results:
            if not r.ok and not r.skipped:
                print(f"  - {r.name}: expected {r.expected}, got {r.actual}")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
