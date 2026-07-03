"""declpkg -- a declarative, pluggable, CRDT-backed cross-ecosystem package manifest.

See README-declpkg.md for the design rationale.
"""

from .manifest import Replica, ResolvedPackage, load_toml_manifest

__all__ = ["Replica", "ResolvedPackage", "load_toml_manifest"]
__version__ = "0.1.0"
