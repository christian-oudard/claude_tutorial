# declpkg — a declarative, pluggable, CRDT-backed package manifest

A proof of concept for one idea: **a single declarative manifest that spans
arbitrary package ecosystems** (pip, npm, cargo, lake, cabal, …), converges
your machine to it like Nix, and **syncs across machines via a CRDT** so two
laptops editing offline merge cleanly — surfacing genuine conflicts instead
of silently picking a winner.

Zero dependencies (Python 3.11+ stdlib only). Everything below actually runs.

```bash
python -m declpkg.demo          # full narrated walkthrough
python -m pytest declpkg/tests  # 23 tests: CRDT laws, merge, reconcile
```

## The three layers

```
   manifest.toml  (what you edit)          ← concrete declarative format
        │  import
        ▼
   Replica  =  ORSWOT(members)             ← CRDT layer (crdt.py)
              + MVRegister(version)             add-wins membership,
              + LWWRegister(source, eco)         multi-value pins, LWW fields
        │
        ├── generate ──▶ requirements.txt / package.json / Cargo.toml /
        │                lakefile.toml / *.cabal   (deterministic, git-diffable)
        │
        └── reconcile ─▶ INSTALL / UPGRADE / REMOVE commands per ecosystem
```

### 1. Concrete manifest format

```toml
[packages.requests]
ecosystem = "pip"
version   = ">=2.31,<3"

[packages.mathlib]
ecosystem = "lake"
source    = "https://github.com/leanprover-community/mathlib4"
version   = "v4.7.0"
```

Every package names an `ecosystem` (which backend drives it), an optional
`version`/pin, and an optional `source` (git/flake ref). Package *presence*
means "installed".

### 2. Pluggable backends

A backend teaches declpkg one ecosystem. It does two things — emit the
imperative install/remove command, and render that ecosystem's **native
declarative file**:

| ecosystem | native file                | install command            |
|-----------|----------------------------|----------------------------|
| `pip`     | `requirements.txt`         | `pip install requests>=2.31,<3` |
| `npm`     | `package.json`             | `npm install left-pad@1.3.0` |
| `cargo`   | `Cargo.toml`               | `cargo add serde@1.0`      |
| `lake`    | `lakefile.toml`            | `lake update mathlib`      |
| `cabal`   | `declpkg-workspace.cabal`  | `cabal install --lib aeson-2.2` |

Adding a package manager = drop a `Backend` subclass in `backends/` and add
one line to `backends/registry.py`. Nothing else changes — the manifest,
reconciler, generator, and CLI are all ecosystem-agnostic.

```python
class PoetryBackend(Backend):
    ecosystem = "poetry"
    native_file = "pyproject.toml"
    def install_cmd(self, pkg): return ["poetry", "add", f"{pkg.name}@{pkg.version}"]
    def remove_cmd(self, pkg):  return ["poetry", "remove", pkg.name]
    def render_native(self, pkgs): ...
```

### 3. The CRDT (why this isn't just a config file)

The manifest is a composition of state-based CRDTs so replicas converge no
matter the sync order:

- **membership → ORSWOT (add-wins).** Concurrent install/uninstall resolves
  to *installed*; a removed package can always be re-added (no 2P-Set
  tombstone trap that would block reinstall-after-uninstall). Note add-wins
  is a property of *membership* — a concurrent version edit does **not**
  keep a package a remove is trying to drop; only a concurrent *install*
  does.
- **version/pin → MVRegister.** Concurrent edits are **both kept** and
  surfaced as a conflict you must resolve explicitly. This is the whole
  point: a LWW "latest timestamp wins" could silently downgrade a pin nobody
  meant to touch.
- **source / ecosystem → LWWRegister.** Fine for fields rarely edited
  concurrently.

Causality is tracked with dots (`replica_id` + counter) and a version-vector
context — the observed-remove discipline that makes add-wins correct.

## Declarative like Nix — two output modes

- **`generate`** renders every ecosystem's native file as a *pure function*
  of the manifest. These artifacts diff cleanly in git even though the CRDT
  log doesn't, so you commit the generated files for review and let merges
  happen in the CRDT layer.
- **`reconcile` (plan/apply)** diffs the manifest against the last applied
  state and emits the minimal INSTALL/UPGRADE/REMOVE command set. Idempotent,
  and it **refuses to apply while any version conflict is unresolved**.

## CLI

```bash
declpkg init --replica laptop
declpkg import declpkg/examples/manifest.toml
declpkg add ripgrep --eco cargo --version 14.1.0
declpkg status
declpkg generate --out ./generated     # native files for every ecosystem
declpkg plan                           # what reconcile would do
declpkg apply --execute                # actually run the commands
# sync across machines:
declpkg export --out laptop.json
declpkg merge server.json              # merges another replica; reports conflicts
declpkg resolve requests --version ">=2.32,<3"
```

## Production notes / honest limitations

- **Swap the hand-rolled CRDT for Automerge.** `crdt.py` implements ORSWOT +
  MVRegister + LWW directly so the POC has zero deps and the semantics are
  legible and unit-tested. In production, store the manifest as an Automerge
  document: it implements a JSON CRDT with these exact semantics, and its
  `getConflicts()` gives you the MVRegister multi-value surface for free.
  (Automerge specifically, not Yjs — `Y.Map` resolves concurrent scalar
  writes to a single LWW winner and won't surface the version conflict.)
- Reconciliation state (`applied.json`) here is a simple recorded snapshot,
  not read back from the live toolchains; a real implementation would query
  each ecosystem for installed state.
- Field registers are keyed by package name and survive uninstall, so a
  remove→reinstall can resurrect an old version. Fine for a POC; production
  would tie field lifetime to the membership dot.
