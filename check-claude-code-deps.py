#!/usr/bin/env python3
"""
Parse Claude Code settings.json and verify all allowed Bash commands are installed.

Opinionated toolchain choices:
- Python: uv only (replaces pip, poetry, pdm, pipenv, pyenv, venv)
- Rust: rustup + cargo (standard)
- JavaScript: pnpm + node (use pnpm dlx instead of npx)
- Lean 4: elan + lake (standard)
- Haskell: ghcup + cabal (standard)
- Go: standard go toolchain
"""

import json
import shutil
import subprocess
import sys
import re
from pathlib import Path

RED = "\033[0;31m"
GREEN = "\033[0;32m"
YELLOW = "\033[1;33m"
CYAN = "\033[0;36m"
DIM = "\033[2m"
NC = "\033[0m"

# Opinionated toolchain: command -> (install_method, install_command, notes)
TOOLCHAIN = {
    # === Python: uv only ===
    "python": ("pacman", "python", None),
    "python3": ("pacman", "python", None),
    "uv": ("curl", "curl -LsSf https://astral.sh/uv/install.sh | sh", "replaces pip, poetry, pdm, venv, pyenv"),
    "ruff": ("uv", "uv tool install ruff", "replaces flake8, isort, black, pylint, bandit"),
    "mypy": ("uv", "uv tool install mypy", None),
    "pytest": ("uv", "uv tool install pytest", None),

    # === Rust: rustup + cargo ===
    "rustup": ("curl", "curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh", None),
    "rustc": ("rustup", "rustup default stable", "install rustup first"),
    "cargo": ("rustup", "rustup default stable", "install rustup first"),
    "rustfmt": ("rustup", "rustup component add rustfmt", None),
    "clippy-driver": ("rustup", "rustup component add clippy", None),

    # === Lean 4: elan + lake ===
    "elan": ("curl", "curl https://raw.githubusercontent.com/leanprover/elan/master/elan-init.sh -sSf | sh", None),
    "lean": ("elan", "elan default stable", "install elan first"),
    "lake": ("elan", "elan default stable", "install elan first"),

    # === Haskell: ghcup + cabal ===
    "ghcup": ("paru", "ghcup-hs-bin", None),
    "ghc": ("ghcup", "ghcup install ghc --set", "install ghcup first"),
    "ghci": ("ghcup", "ghcup install ghc --set", "install ghcup first"),
    "cabal": ("ghcup", "ghcup install cabal --set", None),
    "stack": ("ghcup", "ghcup install stack --set", None),
    "haskell-language-server-wrapper": ("ghcup", "ghcup install hls --set", "Haskell Language Server"),

    # === Go ===
    "go": ("pacman", "go", None),
    "gofmt": ("pacman", "go", "included with go"),
    "gopls": ("go", "go install golang.org/x/tools/gopls@latest", "Go Language Server"),
    "golangci-lint": ("go", "go install github.com/golangci/golangci-lint/cmd/golangci-lint@latest", "linter"),

    # === JavaScript: pnpm + node ===
    "node": ("pacman", "nodejs", None),
    "pnpm": ("corepack", "corepack enable && corepack prepare pnpm@latest --activate", "or: pacman -S pnpm"),

    # === Build tools ===
    "make": ("pacman", "make", None),
    "cmake": ("pacman", "cmake", None),
    "just": ("paru", "just", "modern task runner"),

    # === CLI utilities ===
    "cat": ("pacman", "coreutils", None),
    "ls": ("pacman", "coreutils", None),
    "head": ("pacman", "coreutils", None),
    "tail": ("pacman", "coreutils", None),
    "wc": ("pacman", "coreutils", None),
    "sort": ("pacman", "coreutils", None),
    "uniq": ("pacman", "coreutils", None),
    "mkdir": ("pacman", "coreutils", None),
    "touch": ("pacman", "coreutils", None),
    "cp": ("pacman", "coreutils", None),
    "mv": ("pacman", "coreutils", None),
    "ln": ("pacman", "coreutils", None),
    "chmod": ("pacman", "coreutils", None),
    "rm": ("pacman", "coreutils", None),
    "rmdir": ("pacman", "coreutils", None),
    "echo": ("pacman", "coreutils", None),
    "printf": ("pacman", "coreutils", None),
    "env": ("pacman", "coreutils", None),
    "date": ("pacman", "coreutils", None),
    "uname": ("pacman", "coreutils", None),
    "id": ("pacman", "coreutils", None),
    "whoami": ("pacman", "coreutils", None),
    "pwd": ("pacman", "coreutils", None),
    "realpath": ("pacman", "coreutils", None),
    "dirname": ("pacman", "coreutils", None),
    "basename": ("pacman", "coreutils", None),
    "tee": ("pacman", "coreutils", None),
    "timeout": ("pacman", "coreutils", None),
    "stat": ("pacman", "coreutils", None),
    "sha256sum": ("pacman", "coreutils", None),
    "md5sum": ("pacman", "coreutils", None),
    "b2sum": ("pacman", "coreutils", None),

    "less": ("pacman", "less", None),
    "grep": ("pacman", "grep", None),
    "sed": ("pacman", "sed", None),
    "awk": ("pacman", "gawk", None),
    "diff": ("pacman", "diffutils", None),
    "find": ("pacman", "findutils", None),
    "xargs": ("pacman", "findutils", None),
    "file": ("pacman", "file", None),
    "tree": ("pacman", "tree", None),
    "which": ("pacman", "which", None),
    "whereis": ("pacman", "util-linux", None),
    "time": ("pacman", "time", None),

    "rg": ("pacman", "ripgrep", None),
    "fd": ("pacman", "fd", None),

    "ps": ("pacman", "procps-ng", None),
    "pgrep": ("pacman", "procps-ng", None),
    "kill": ("pacman", "procps-ng", None),
    "pkill": ("pacman", "procps-ng", None),

    "curl": ("pacman", "curl", None),
    "wget": ("pacman", "wget", None),
    "jq": ("pacman", "jq", None),
    "yq": ("paru", "yq", None),

    "tar": ("pacman", "tar", None),
    "unzip": ("pacman", "unzip", None),
    "gzip": ("pacman", "gzip", None),
    "gunzip": ("pacman", "gzip", None),

    "git": ("pacman", "git", None),

    # Builtins (no install needed)
    "type": ("builtin", "bash builtin", None),
}


def parse_bash_commands(settings_path: Path) -> list[str]:
    """Extract command names from Bash(...) permissions."""
    with open(settings_path) as f:
        settings = json.load(f)

    allowed = settings.get("permissions", {}).get("allow", [])
    commands = []

    pattern = re.compile(r'^Bash\(([^:]+):\*\)$')

    for perm in allowed:
        match = pattern.match(perm)
        if match:
            cmd = match.group(1)
            commands.append(cmd)

    return sorted(set(commands))


def check_command_exists(cmd: str) -> tuple[bool, str | None]:
    """Check if command exists and return its path."""
    # Handle shell builtins
    if cmd in TOOLCHAIN and TOOLCHAIN[cmd][0] == "builtin":
        return (True, "builtin")
    path = shutil.which(cmd)
    return (path is not None, path)


def get_pacman_owner(path: str) -> str | None:
    """Get the pacman package that owns a file."""
    try:
        result = subprocess.run(
            ["pacman", "-Qo", path],
            capture_output=True,
            text=True
        )
        if result.returncode == 0:
            parts = result.stdout.strip().split(" is owned by ")
            if len(parts) == 2:
                return parts[1].split()[0]
    except Exception:
        pass
    return None


def get_package_source(_cmd: str, path: str | None) -> str:
    """Determine how a command was installed."""
    if path is None:
        return "not found"

    if path == "builtin":
        return "shell builtin"

    pkg = get_pacman_owner(path)
    if pkg:
        return f"pacman:{pkg}"

    if "/.cargo/bin/" in path:
        return "cargo"
    if "/.local/bin/" in path:
        return "uv/local"
    if "/.elan/" in path:
        return "elan"
    if "/.opam/" in path:
        return "opam"
    if "/node_modules/" in path or "/.npm/" in path:
        return "npm"
    if "/.rustup/" in path:
        return "rustup"
    if "/pnpm" in path:
        return "pnpm"

    return "unknown"


def main():
    settings_paths = [
        Path("settings.json"),
        Path.home() / ".claude" / "settings.json",
        Path(".claude") / "settings.json",
    ]

    settings_path = None
    for p in settings_paths:
        if p.exists():
            settings_path = p
            break

    if settings_path is None:
        if len(sys.argv) > 1:
            settings_path = Path(sys.argv[1])
        else:
            print(f"{RED}Error: settings.json not found{NC}")
            print("Usage: ./check-claude-code-deps.py [path/to/settings.json]")
            sys.exit(1)

    if not settings_path.exists():
        print(f"{RED}Error: {settings_path} does not exist{NC}")
        sys.exit(1)

    print(f"{CYAN}╔══════════════════════════════════════════════════════════════╗{NC}")
    print(f"{CYAN}║       Claude Code Dev Environment - Dependency Check         ║{NC}")
    print(f"{CYAN}╚══════════════════════════════════════════════════════════════╝{NC}")
    print(f"\nSettings: {settings_path}\n")

    commands = parse_bash_commands(settings_path)

    # Group by category
    categories = {
        "Python (uv)": ["python", "python3", "uv", "ruff", "mypy", "pytest"],
        "Rust (rustup)": ["rustup", "rustc", "cargo", "rustfmt", "clippy-driver"],
        "Lean 4 (elan)": ["elan", "lean", "lake"],
        "Haskell (ghcup)": ["ghcup", "ghc", "ghci", "cabal", "stack", "haskell-language-server-wrapper"],
        "Go": ["go", "gofmt", "gopls", "golangci-lint"],
        "JavaScript (pnpm)": ["node", "pnpm"],
        "Build Tools": ["make", "cmake", "just"],
        "Search/Find": ["grep", "rg", "fd", "find"],
        "File Operations": ["cat", "ls", "head", "tail", "less", "wc", "tree", "file", "stat", 
                           "mkdir", "touch", "cp", "mv", "ln", "chmod", "rm", "rmdir"],
        "Text Processing": ["sed", "awk", "sort", "uniq", "diff", "xargs", "tee"],
        "System Info": ["echo", "printf", "env", "which", "whereis", "type", "date", 
                       "uname", "id", "whoami", "pwd", "realpath", "dirname", "basename"],
        "Process Management": ["ps", "pgrep", "kill", "pkill", "time", "timeout"],
        "Network": ["curl", "wget"],
        "Data/Archive": ["jq", "yq", "tar", "unzip", "gzip", "gunzip"],
        "Checksums": ["sha256sum", "md5sum", "b2sum"],
        "Version Control": ["git"],
    }

    missing = []
    installed_count = 0
    total_count = len(commands)

    for category, cmds in categories.items():
        relevant = [c for c in cmds if c in commands]
        if not relevant:
            continue

        print(f"{CYAN}── {category} ──{NC}")
        for cmd in relevant:
            exists, path = check_command_exists(cmd)
            source = get_package_source(cmd, path)
            info = TOOLCHAIN.get(cmd, (None, None, None))
            note = info[2] if info else None

            if exists:
                note_str = f" {DIM}({note}){NC}" if note else ""
                print(f"  {GREEN}✓{NC} {cmd:18} {DIM}{source}{NC}{note_str}")
                installed_count += 1
            else:
                print(f"  {RED}✗{NC} {cmd:18} NOT FOUND")
                missing.append(cmd)
        print()

    # Check for uncategorized commands
    categorized = set()
    for cmds in categories.values():
        categorized.update(cmds)
    uncategorized = [c for c in commands if c not in categorized]
    if uncategorized:
        print(f"{CYAN}── Other ──{NC}")
        for cmd in uncategorized:
            exists, path = check_command_exists(cmd)
            source = get_package_source(cmd, path)
            if exists:
                print(f"  {GREEN}✓{NC} {cmd:18} {DIM}{source}{NC}")
                installed_count += 1
            else:
                print(f"  {RED}✗{NC} {cmd:18} NOT FOUND")
                missing.append(cmd)
        print()

    # Summary
    print(f"{CYAN}╔══════════════════════════════════════════════════════════════╗{NC}")
    print(f"{CYAN}║                          Summary                             ║{NC}")
    print(f"{CYAN}╚══════════════════════════════════════════════════════════════╝{NC}")
    print(f"\n{GREEN}Installed:{NC} {installed_count}/{total_count}")

    if missing:
        print(f"{RED}Missing:{NC}   {len(missing)}\n")
        print_install_instructions(missing)
        # Generate install script
        script_path = Path("install-deps.sh")
        generate_install_script(missing, script_path)
    else:
        print(f"\n{GREEN}All tools installed!{NC}")

    # Sandbox check
    print(f"\n{CYAN}── Sandbox (bubblewrap) ──{NC}")
    bwrap_exists, _ = check_command_exists("bwrap")
    if bwrap_exists:
        print(f"  {GREEN}✓{NC} bubblewrap installed")
        print(f"  {DIM}Run /sandbox in Claude Code to enable filesystem isolation{NC}")
    else:
        print(f"  {RED}✗{NC} bubblewrap NOT FOUND")
        print(f"  {YELLOW}sudo pacman -S bubblewrap{NC}")

    # Toolchain notes
    print(f"\n{CYAN}── Toolchain Notes ──{NC}")
    print(f"""
  {YELLOW}Python:{NC}  Use 'uv' for everything (venv, install, run, tool)
           {DIM}uv venv && uv pip install -r requirements.txt
           uv run python script.py
           uv tool install ruff{NC}

  {YELLOW}JS/TS:{NC}   Use 'pnpm' instead of npm/yarn
           {DIM}pnpm install
           pnpm dlx prettier --write .   # instead of npx
           pnpm exec tsc                 # project-local{NC}

  {YELLOW}Rust:{NC}    Standard rustup toolchain
           {DIM}cargo build, cargo test, cargo clippy{NC}

  {YELLOW}Lean 4:{NC}  Use 'lake' for project management
           {DIM}lake new myproject && cd myproject && lake build{NC}

  {YELLOW}Haskell:{NC} Use 'ghcup' + 'cabal' (or stack)
           {DIM}ghcup install ghc cabal hls
           cabal init && cabal build{NC}

  {YELLOW}Go:{NC}      Standard go toolchain
           {DIM}go mod init myproject
           go build && go test{NC}
""")


def print_install_instructions(missing: list[str]):
    """Print install commands grouped by method."""
    pacman_pkgs = set()
    paru_pkgs = set()
    other = []

    for cmd in missing:
        if cmd not in TOOLCHAIN:
            other.append((cmd, "unknown", "check manually"))
            continue

        method, install_cmd, _note = TOOLCHAIN[cmd]

        if method == "pacman":
            pacman_pkgs.add(install_cmd)
        elif method == "paru":
            paru_pkgs.add(install_cmd)
        elif method == "builtin":
            pass
        else:
            other.append((cmd, method, install_cmd))

    print(f"{YELLOW}Install commands:{NC}\n")

    if pacman_pkgs:
        print(f"  {GREEN}# Core packages (pacman){NC}")
        print(f"  sudo pacman -S {' '.join(sorted(pacman_pkgs))}\n")

    if paru_pkgs:
        print(f"  {GREEN}# AUR packages (paru){NC}")
        print(f"  paru -S {' '.join(sorted(paru_pkgs))}\n")

    # Group other by method
    by_method = {}
    for cmd, method, install_cmd in other:
        if method not in by_method:
            by_method[method] = []
        by_method[method].append((cmd, install_cmd))

    method_order = ["curl", "rustup", "elan", "ghcup", "go", "uv", "corepack", "pnpm"]
    for method in method_order:
        if method not in by_method:
            continue
        items = by_method.pop(method)
        print(f"  {GREEN}# {method}{NC}")
        for cmd, install_cmd in items:
            print(f"  {install_cmd}  # {cmd}")
        print()

    for method, items in by_method.items():
        print(f"  {GREEN}# {method}{NC}")
        for cmd, install_cmd in items:
            print(f"  {install_cmd}  # {cmd}")
        print()


def generate_install_script(missing: list[str], output_path: Path) -> None:
    """Generate a shell script to install missing dependencies."""
    pacman_pkgs = set()
    paru_pkgs = set()
    uv_tools = []
    ghcup_cmds = []
    other_cmds = []

    for cmd in missing:
        if cmd not in TOOLCHAIN:
            continue

        method, install_cmd, _ = TOOLCHAIN[cmd]

        if method == "pacman":
            pacman_pkgs.add(install_cmd)
        elif method == "paru":
            paru_pkgs.add(install_cmd)
        elif method == "uv":
            uv_tools.append(install_cmd)
        elif method == "ghcup":
            ghcup_cmds.append((cmd, install_cmd))
        elif method == "builtin":
            pass
        else:
            other_cmds.append((cmd, method, install_cmd))

    lines = [
        "#!/bin/bash",
        "set -e",
        "",
        'echo "=== Installing missing dependencies ==="',
        "",
    ]

    # Helper function to run commands with display
    lines.append("run() {")
    lines.append('    echo ">> $*"')
    lines.append('    "$@"')
    lines.append("}")
    lines.append("")

    # uv tools first (no sudo needed)
    if uv_tools:
        lines.append('echo ""')
        lines.append('echo "--- Installing Python tools via uv ---"')
        for tool_cmd in uv_tools:
            lines.append(f"run {tool_cmd}")
        lines.append("")

    # pacman packages
    if pacman_pkgs:
        pkg_list = ' '.join(sorted(pacman_pkgs))
        lines.append('echo ""')
        lines.append('echo "--- Installing pacman packages ---"')
        lines.append(f'echo ">> sudo pacman -S --needed --noconfirm {pkg_list}"')
        lines.append(f"sudo pacman -S --needed --noconfirm {pkg_list}")
        lines.append("")

    # paru packages
    if paru_pkgs:
        pkg_list = ' '.join(sorted(paru_pkgs))
        lines.append('echo ""')
        lines.append('echo "--- Installing AUR packages ---"')
        lines.append(f'echo ">> paru -S --needed --noconfirm {pkg_list}"')
        lines.append(f"paru -S --needed --noconfirm {pkg_list}")
        lines.append("")

    # ghcup setup
    if ghcup_cmds:
        lines.append('echo ""')
        lines.append('echo "--- Setting up Haskell toolchain ---"')
        lines.append("if command -v ghcup &> /dev/null; then")
        # Deduplicate ghcup commands
        seen = set()
        for _, install_cmd in ghcup_cmds:
            if install_cmd not in seen:
                seen.add(install_cmd)
                lines.append(f"    run {install_cmd}")
        lines.append("else")
        lines.append('    echo "ERROR: ghcup not found. Install AUR packages first."')
        lines.append("    exit 1")
        lines.append("fi")
        lines.append("")

    # Other commands
    for cmd, method, install_cmd in other_cmds:
        lines.append(f'echo "--- Installing {cmd} via {method} ---"')
        lines.append(f"run {install_cmd}")
        lines.append("")

    lines.append('echo ""')
    lines.append('echo "=== Done! ==="')

    # Write the script
    output_path.write_text("\n".join(lines) + "\n")
    output_path.chmod(0o755)
    print(f"\n{GREEN}Install script written to:{NC} {output_path}")
    print(f"Run: {CYAN}./{output_path.name}{NC}")


if __name__ == "__main__":
    main()
