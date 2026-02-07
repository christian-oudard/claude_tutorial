# Unix Permissions for CLI Agent Containment

A guide to running AI coding agents under a dedicated non-privileged Unix user, using traditional permissions, ACLs, and resource limits.

## Why Unix Permissions?

Unix multi-user security was designed for untrusted users on shared mainframes. An AI agent is essentially an "untrusted automated user" - the permission model fits naturally.

**What we're using:**
- Dedicated user account
- File permissions and ACLs
- Disk quotas
- systemd resource limits

**What we're NOT using:**
- Containers (Docker, Podman)
- Namespace sandboxing (bubblewrap, firejail)
- Mandatory Access Control (SELinux, AppArmor)

Standard Unix isolation is sufficient for this threat model.

---

## Threat Model

| Threat | Mitigation |
|--------|------------|
| Accidental file damage | Agent can only write to its own home |
| Reading secrets (.ssh, .env) | Human's home is 700, no ACL grants |
| Privilege escalation | No sudo, not in wheel group |
| Disk exhaustion | Filesystem quotas |
| CPU/memory exhaustion | systemd slice limits |

---

## Setup Guide

### Step 1: Create Agent User

```bash
# Create user with home directory
sudo useradd -m -s /bin/bash agent-claude

# Add to nixbld group for Nix package builds
sudo usermod -aG nixbld agent-claude

# Make agent's home readable by human (for reviewing work, pulling git repos)
sudo chmod 755 /home/agent-claude
```

### Step 2: Secure Human's Home Directory

```bash
# Ensure agent cannot read human's files
chmod 700 /home/christian
```

### Step 3: Configure Agent's Environment with Nix

Use home-manager to declaratively configure the agent's environment.

**Create `/home/agent-claude/.config/home-manager/home.nix`:**

```nix
{ config, pkgs, ... }:

{
  home.username = "agent-claude";
  home.homeDirectory = "/home/agent-claude";
  home.stateVersion = "24.05";

  # Let home-manager manage itself
  programs.home-manager.enable = true;

  # Packages available to the agent
  home.packages = with pkgs; [
    # Core tools
    git
    curl
    jq
    ripgrep
    fd
    tree

    # Languages/runtimes
    nodejs_22
    python313
    uv

    # Claude Code
    # claude-code  # if packaged, or install via npm
  ];

  # Git configuration
  programs.git = {
    enable = true;
    userName = "agent-claude";
    userEmail = "agent@localhost";
    extraConfig = {
      init.defaultBranch = "main";
      safe.directory = "*";  # Allow operations in any directory
    };
  };

  # Shell configuration
  programs.bash = {
    enable = true;
    shellAliases = {
      ll = "ls -la";
      projects = "cd ~/projects && ls";
    };
    initExtra = ''
      # Start in home directory
      cd ~

      # npm global prefix (no sudo needed)
      export NPM_CONFIG_PREFIX="$HOME/.npm-global"
      export PATH="$HOME/.npm-global/bin:$PATH"

      # Project helper
      proj() {
        cd ~/projects/"$1"
      }
    '';
  };

  # Direnv for per-project environments
  programs.direnv = {
    enable = true;
    nix-direnv.enable = true;
  };

  # Create directory structure
  home.file.".keep-projects".text = "";
  home.activation.createDirs = config.lib.dag.entryAfter ["writeBoundary"] ''
    mkdir -p $HOME/projects
    mkdir -p $HOME/.npm-global
  '';
}
```

**Apply the configuration:**

```bash
# As agent-claude
sudo -u agent-claude -i
nix-channel --add https://github.com/nix-community/home-manager/archive/master.tar.gz home-manager
nix-channel --update
nix-shell '<home-manager>' -A install

# Then apply
home-manager switch
```

### Step 4: Per-Project Environments with shell.nix

Each project can have a `shell.nix` that defines its specific dependencies. When the agent enters the project directory, direnv automatically loads the environment.

**Example project `shell.nix`:**

```nix
{ pkgs ? import <nixpkgs> {} }:

pkgs.mkShell {
  buildInputs = with pkgs; [
    # Project-specific dependencies
    nodejs_22
    nodePackages.typescript
    nodePackages.prettier

    # Python for scripts
    python313
    uv
  ];

  shellHook = ''
    echo "Entered project environment"

    # Install node dependencies if needed
    if [ -f package.json ] && [ ! -d node_modules ]; then
      echo "Installing npm dependencies..."
      npm install
    fi
  '';
}
```

**Project `.envrc`:**

```bash
use nix
```

The agent's direnv (configured in home.nix) automatically loads this when entering the project.

### Step 5: Grant Project Access via ACL

For each project the agent should access:

```bash
# Grant read access to human's project
sudo setfacl -R -m u:agent-claude:rX /home/christian/projects/myrepo

# For new files created in the directory (default ACL)
sudo setfacl -R -d -m u:agent-claude:rX /home/christian/projects/myrepo
```

### Step 6: Set Up Git Workflow

The agent works with local git only. Human pulls changes when ready.

**As agent:**
```bash
# Clone from human's local repo
git clone /home/christian/projects/myrepo ~/projects/myrepo

# Work and commit normally
cd ~/projects/myrepo
# ... make changes ...
git commit -m "feat: add feature"
```

**As human:**
```bash
cd /home/christian/projects/myrepo

# Add agent's repo as remote (one-time)
git remote add agent /home/agent-claude/projects/myrepo

# Pull agent's changes when ready to review
git pull agent main

# Review, then push to origin
git push origin main
```

### Step 7: Set Disk Quota

```bash
# Enable quotas on /home filesystem (may require fstab edit + remount)
sudo mount -o remount,usrquota /home

# Set 50GB soft limit, 60GB hard limit
sudo setquota -u agent-claude 50G 60G 0 0 /home

# Verify
sudo quota -u agent-claude
```

### Step 8: Set CPU/Memory Limits (systemd slice)

Create `/etc/systemd/system/agent-claude.slice`:

```ini
[Slice]
CPUQuota=200%
MemoryMax=8G
TasksMax=1000
IOWeight=50
```

Reload and run commands under the slice:

```bash
sudo systemctl daemon-reload

# Run a command under the slice
systemd-run --slice=agent-claude.slice --uid=agent-claude -- claude
```

---

## Running Claude Code as Agent

Claude starts in the agent's home directory and can cd into projects as needed.

```bash
# Switch to agent user (starts in /home/agent-claude)
sudo -u agent-claude -i

# Start claude with no internal restrictions (OS provides containment)
claude --dangerously-skip-permissions

# Claude can then cd into projects:
#   cd ~/projects/myrepo
#   or use the proj helper: proj myrepo
```

**Why `--dangerously-skip-permissions` is safe here:**

The flag disables Claude Code's internal permission prompts. Normally this would be risky, but with OS-level containment:
- Agent can only write to `/home/agent-claude` (Unix permissions)
- Agent can only read ACL-granted paths (ACLs)
- Agent cannot exhaust disk (quotas)
- Agent cannot exhaust CPU/memory (systemd slice)
- Agent cannot sudo (not in wheel group)

The "danger" is fully contained by the OS. Claude can work autonomously without interruptions.

**With resource limits:**

```bash
systemd-run --slice=agent-claude.slice --uid=agent-claude --pty -- bash -c 'cd ~ && claude --dangerously-skip-permissions'
```

**Workflow:**
1. Claude starts in `/home/agent-claude`
2. Claude can `cd ~/projects/foo` to enter a project
3. Direnv automatically loads the project's `shell.nix` environment
4. Claude works on the project
5. Claude commits changes to its local repo
6. Human pulls from agent's repo when ready to review

---

## Verification Checklist

Test these after setup:

**File Access:**
```bash
# As agent-claude, these should FAIL:
cat /home/christian/.ssh/id_rsa
cat /home/christian/.env
ls /home/christian/

# These should SUCCEED:
cat /home/christian/projects/myrepo/README.md  # if ACL granted
echo "test" > ~/test.txt
```

**Git Workflow:**
```bash
# As agent: clone and commit
sudo -u agent-claude git clone /home/christian/projects/myrepo /home/agent-claude/projects/myrepo
sudo -u agent-claude git -C /home/agent-claude/projects/myrepo commit --allow-empty -m "test"

# As human: pull from agent
git -C /home/christian/projects/myrepo remote add agent /home/agent-claude/projects/myrepo
git -C /home/christian/projects/myrepo fetch agent
```

**Resource Limits:**
```bash
# Check quota
sudo quota -u agent-claude

# Check slice limits
systemctl show agent-claude.slice | grep -E "(CPU|Memory|Tasks)"
```

---

## Security Properties

| Property | How It's Enforced |
|----------|-------------------|
| Agent cannot read human's files | Human's home is 700 |
| Agent cannot write outside home | Owns only /home/agent-claude |
| Agent cannot access secrets | No group membership, no ACL grants |
| Agent cannot escalate privileges | No sudo, not in wheel group |
| Agent cannot exhaust CPU/memory | systemd slice limits |
| Agent cannot exhaust disk | Filesystem quotas |
| Human can read agent's files | Agent's home is 755 |

---

## Notes

### Nix Store Sharing

The Nix store at `/nix/store` is world-readable by design. The agent can use any packages already installed without reinstalling. New packages require `nixbld` group membership (already configured in Step 1).

### Network Access

This guide does not restrict network access. For future hardening, consider:
- nftables rules filtering by UID (`meta skuid agent-claude`)
- DNS filtering proxy (squid with domain allowlist)

### Escape Vectors to Consider

- Symlinks pointing outside allowed paths (ACLs follow symlinks)
- Hardlinks to sensitive files (requires write access to target dir)
- `/proc/*/environ` of other users' processes (readable if world-readable, which is default)
- Shared /tmp (use private tmp via systemd or per-user tmp)

For stronger isolation against these, consider adding bubblewrap or containers.
