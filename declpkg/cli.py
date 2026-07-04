"""declpkg command-line interface.

State lives under a project-local directory (default ``.declpkg/``):
  * ``state.json``   -- the CRDT manifest for this replica
  * ``applied.json`` -- last reconciled state (for the diff)

    declpkg init [--replica NAME]
    declpkg import MANIFEST.toml
    declpkg add NAME --eco ECO [--version V] [--source S]
    declpkg remove NAME
    declpkg status
    declpkg generate [--out DIR]
    declpkg plan
    declpkg apply [--execute]
    declpkg merge OTHER_STATE.json
    declpkg resolve NAME --version V
    declpkg export [--out FILE]
"""

from __future__ import annotations

import argparse
import os
import sys

from .backends import known_ecosystems
from .generate import generate, write_generated
from .manifest import Replica, load_toml_manifest
from .reconcile import apply as do_apply
from .reconcile import plan as do_plan


def _paths(state_dir: str) -> tuple[str, str]:
    return os.path.join(state_dir, "state.json"), os.path.join(state_dir, "applied.json")


def _load(state_dir: str) -> Replica:
    state_path, _ = _paths(state_dir)
    if not os.path.exists(state_path):
        sys.exit(f"no manifest at {state_path}; run `declpkg init` first")
    return Replica.load(state_path)


def _save(replica: Replica, state_dir: str) -> None:
    state_path, _ = _paths(state_dir)
    os.makedirs(state_dir, exist_ok=True)
    replica.save(state_path)


def cmd_init(args: argparse.Namespace) -> None:
    state_path, _ = _paths(args.state_dir)
    if os.path.exists(state_path) and not args.force:
        sys.exit(f"{state_path} already exists (use --force to overwrite)")
    _save(Replica(args.replica), args.state_dir)
    print(f"initialized replica {args.replica!r} at {state_path}")


def cmd_import(args: argparse.Namespace) -> None:
    replica = _load(args.state_dir)
    load_toml_manifest(args.file, replica)
    _save(replica, args.state_dir)
    print(f"imported {args.file}")
    cmd_status(args)


def cmd_add(args: argparse.Namespace) -> None:
    replica = _load(args.state_dir)
    replica.install(args.name, args.eco, version=args.version, source=args.source)
    _save(replica, args.state_dir)
    print(f"added {args.name} ({args.eco})")


def cmd_remove(args: argparse.Namespace) -> None:
    replica = _load(args.state_dir)
    replica.uninstall(args.name)
    _save(replica, args.state_dir)
    print(f"removed {args.name}")


def cmd_resolve(args: argparse.Namespace) -> None:
    replica = _load(args.state_dir)
    replica.resolve_version(args.name, args.version)
    _save(replica, args.state_dir)
    print(f"resolved {args.name} -> {args.version}")


def cmd_status(args: argparse.Namespace) -> None:
    replica = _load(args.state_dir)
    resolved = replica.resolved()
    if not resolved:
        print("(manifest is empty)")
        return
    print(f"replica {replica.replica_id!r} -- {len(resolved)} package(s)")
    for p in resolved.values():
        if p.conflicted:
            ver = "CONFLICT[" + " | ".join(p.version_candidates) + "]"
        else:
            ver = p.version or "*"
        src = f"  source={p.source}" if p.source else ""
        print(f"  {p.name:<16} {p.ecosystem:<7} {ver}{src}")
    conflicts = replica.conflicts()
    if conflicts:
        print(f"\n{len(conflicts)} unresolved conflict(s); "
              f"run `declpkg resolve NAME --version V`")


def cmd_generate(args: argparse.Namespace) -> None:
    replica = _load(args.state_dir)
    if args.out:
        for path in write_generated(replica, args.out):
            print(f"wrote {path}")
    else:
        for filename, contents in generate(replica).items():
            print(f"===== {filename} =====")
            print(contents)


def cmd_plan(args: argparse.Namespace) -> None:
    replica = _load(args.state_dir)
    _, applied_path = _paths(args.state_dir)
    print(do_plan(replica, applied_path).render())


def cmd_apply(args: argparse.Namespace) -> None:
    replica = _load(args.state_dir)
    _, applied_path = _paths(args.state_dir)
    p = do_apply(replica, applied_path, execute=args.execute)
    print(p.render())
    if p.conflicts:
        sys.exit("aborted: resolve conflicts first")
    if not args.execute and not p.empty:
        print("\n(dry run -- re-run with --execute to run these commands)")


def cmd_merge(args: argparse.Namespace) -> None:
    replica = _load(args.state_dir)
    other = Replica.load(args.other)
    replica.merge(other)
    _save(replica, args.state_dir)
    print(f"merged {args.other} into replica {replica.replica_id!r}")
    cmd_status(args)


def cmd_export(args: argparse.Namespace) -> None:
    replica = _load(args.state_dir)
    if args.out:
        replica.save(args.out)
        print(f"exported CRDT state to {args.out}")
    else:
        import json
        print(json.dumps(replica.to_json(), indent=2, sort_keys=True))


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="declpkg", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--state-dir", default=".declpkg",
                   help="directory holding CRDT state (default: .declpkg)")
    sub = p.add_subparsers(dest="cmd", required=True)

    sp = sub.add_parser("init", help="create a new manifest replica")
    sp.add_argument("--replica", default="local", help="replica id (machine name)")
    sp.add_argument("--force", action="store_true")
    sp.set_defaults(func=cmd_init)

    sp = sub.add_parser("import", help="import a declarative manifest.toml")
    sp.add_argument("file")
    sp.set_defaults(func=cmd_import)

    sp = sub.add_parser("add", help="install/declare a package")
    sp.add_argument("name")
    sp.add_argument("--eco", required=True, choices=known_ecosystems())
    sp.add_argument("--version")
    sp.add_argument("--source")
    sp.set_defaults(func=cmd_add)

    sp = sub.add_parser("remove", help="uninstall a package")
    sp.add_argument("name")
    sp.set_defaults(func=cmd_remove)

    sp = sub.add_parser("resolve", help="resolve a version conflict")
    sp.add_argument("name")
    sp.add_argument("--version", required=True)
    sp.set_defaults(func=cmd_resolve)

    sp = sub.add_parser("status", help="show the resolved manifest")
    sp.set_defaults(func=cmd_status)

    sp = sub.add_parser("generate", help="render native ecosystem files")
    sp.add_argument("--out", help="write files into this directory")
    sp.set_defaults(func=cmd_generate)

    sp = sub.add_parser("plan", help="show reconcile actions")
    sp.set_defaults(func=cmd_plan)

    sp = sub.add_parser("apply", help="apply reconcile actions")
    sp.add_argument("--execute", action="store_true", help="actually run commands")
    sp.set_defaults(func=cmd_apply)

    sp = sub.add_parser("merge", help="merge another replica's CRDT state")
    sp.add_argument("other")
    sp.set_defaults(func=cmd_merge)

    sp = sub.add_parser("export", help="dump this replica's CRDT state")
    sp.add_argument("--out")
    sp.set_defaults(func=cmd_export)

    return p


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
