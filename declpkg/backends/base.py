"""Backend plugin protocol.

A backend teaches ``declpkg`` how one ecosystem is driven. It has two jobs:

  1. **Imperative** -- emit the concrete shell command to install / remove a
     single package (used by the reconciler).
  2. **Declarative** -- render that ecosystem's *native* spec file from the
     full set of packages (used by ``generate``), so a single manifest
     produces ``requirements.txt`` + ``package.json`` + ``Cargo.toml`` + ...
     deterministically -- the Nix-like "one declaration, whole world"
     property.

Adding a new package manager is just dropping a new subclass in this
directory and registering it in ``registry.py``. Nothing else changes.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Package:
    name: str
    ecosystem: str
    version: str | None = None
    source: str | None = None


class Backend:
    #: ecosystem key used in the manifest (e.g. "pip")
    ecosystem: str = ""
    #: native declarative artifact this backend generates (e.g. "requirements.txt")
    native_file: str = ""

    def install_cmd(self, pkg: Package) -> list[str]:
        raise NotImplementedError

    def remove_cmd(self, pkg: Package) -> list[str]:
        raise NotImplementedError

    def render_native(self, pkgs: list[Package]) -> str:
        """Return the full text of ``native_file`` for these packages."""
        raise NotImplementedError

    # convenience shared by several backends
    @staticmethod
    def _sorted(pkgs: list[Package]) -> list[Package]:
        return sorted(pkgs, key=lambda p: p.name)
