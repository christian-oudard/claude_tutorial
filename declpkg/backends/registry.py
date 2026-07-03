"""Backend registry -- the single place ecosystems are wired in.

To add a package manager: implement a ``Backend`` subclass in this
directory and add it to ``_BACKENDS`` below. Everything else (manifest,
reconcile, generate, CLI) is ecosystem-agnostic and needs no changes.
"""

from __future__ import annotations

from .base import Backend
from .cabal import CabalBackend
from .cargo import CargoBackend
from .lake import LakeBackend
from .npm import NpmBackend
from .pip import PipBackend

_BACKENDS: dict[str, Backend] = {
    b.ecosystem: b
    for b in (PipBackend(), NpmBackend(), CargoBackend(), LakeBackend(), CabalBackend())
}


def get_backend(ecosystem: str) -> Backend:
    try:
        return _BACKENDS[ecosystem]
    except KeyError:
        raise KeyError(
            f"no backend for ecosystem {ecosystem!r}; "
            f"known: {', '.join(sorted(_BACKENDS))}"
        )


def known_ecosystems() -> list[str]:
    return sorted(_BACKENDS)
