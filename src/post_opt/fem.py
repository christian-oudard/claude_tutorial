"""Euler-Bernoulli beam FEM for a variable-section cantilever column.

Two-node Hermitian-cubic elements, two DOFs per node (transverse deflection
``w`` and rotation ``theta``).  The column is fixed at the base (``z = 0``) and
free at the tip (``z = H``); planar bending is analysed because the lateral
load acts in its worst-case direction.

The module assembles three operators over a mesh with element-wise constant
properties:

* ``K``    -- elastic bending stiffness from ``EI(z) = E pi r(z)^4 / 4``
* ``K_G``  -- geometric stiffness from the compressive axial force ``N_c(z)``
              (tip load ``P`` plus self-weight above ``z``)
* the self-weight is vertical, so it enters only through ``K_G`` (P-delta).

From these it provides:

* **buckling** as the generalized eigenproblem ``K phi = lambda K_G phi``;
  the smallest positive ``lambda`` is the load multiplier at buckling.
* **second-order deflection** from ``(K - K_G) u = f`` under the lateral tip
  force, i.e. the geometrically softened stiffness.
* **bending moments** ``M(z)`` recovered from statics using the second-order
  deflection profile (robust against shape-function curvature noise).
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
from scipy.linalg import eig, solve


@dataclass
class BeamMesh:
    z_nodes: np.ndarray  # node coordinates (nnode,)
    z_mid: np.ndarray  # element midpoints (nel,)
    L: np.ndarray  # element lengths (nel,)
    EI: np.ndarray  # element flexural rigidity (nel,)
    w_line: np.ndarray  # element weight per length (nel,)


def build_mesh(
    H: float,
    radius_fn,
    E: float,
    rho_g: float,
    nel: int,
) -> BeamMesh:
    """Uniform mesh on ``[0, H]`` with midpoint-evaluated section properties."""
    z_nodes = np.linspace(0.0, H, nel + 1)
    z_mid = 0.5 * (z_nodes[:-1] + z_nodes[1:])
    L = np.diff(z_nodes)
    rm = np.asarray(radius_fn(z_mid), dtype=float)
    EI = E * math.pi * rm**4 / 4.0
    w_line = rho_g * math.pi * rm**2
    return BeamMesh(z_nodes, z_mid, L, EI, w_line)


def _bending_element(EI: float, L: float) -> np.ndarray:
    c = EI / L**3
    return c * np.array(
        [
            [12.0, 6 * L, -12.0, 6 * L],
            [6 * L, 4 * L**2, -6 * L, 2 * L**2],
            [-12.0, -6 * L, 12.0, -6 * L],
            [6 * L, 2 * L**2, -6 * L, 4 * L**2],
        ]
    )


def _geometric_element(N: float, L: float) -> np.ndarray:
    c = N / (30.0 * L)
    return c * np.array(
        [
            [36.0, 3 * L, -36.0, 3 * L],
            [3 * L, 4 * L**2, -3 * L, -L**2],
            [-36.0, -3 * L, 36.0, -3 * L],
            [3 * L, -L**2, -3 * L, 4 * L**2],
        ]
    )


def axial_compression(mesh: BeamMesh, P: float) -> np.ndarray:
    """Compressive axial force at each element midpoint: ``P + weight above``.

    Self-weight above a midpoint is the weight of the elements above it plus the
    outer half of the element itself, integrated from the profile.
    """
    seg_weight = mesh.w_line * mesh.L  # weight of each element
    # cumulative weight strictly above each element's far node
    w_above_far = np.cumsum(seg_weight[::-1])[::-1]  # includes own element
    w_above_far = np.concatenate([w_above_far[1:], [0.0]])  # above far node
    # weight above the midpoint = above far node + outer half of this element
    w_above_mid = w_above_far + 0.5 * seg_weight
    return P + w_above_mid


def assemble(mesh: BeamMesh, P: float) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Assemble ``(K, K_G, N_c)`` for the full (unconstrained) DOF set."""
    nel = len(mesh.L)
    ndof = 2 * (nel + 1)
    K = np.zeros((ndof, ndof))
    KG = np.zeros((ndof, ndof))
    Nc = axial_compression(mesh, P)
    for e in range(nel):
        ke = _bending_element(mesh.EI[e], mesh.L[e])
        kge = _geometric_element(Nc[e], mesh.L[e])
        d = [2 * e, 2 * e + 1, 2 * e + 2, 2 * e + 3]
        ix = np.ix_(d, d)
        K[ix] += ke
        KG[ix] += kge
    return K, KG, Nc


def _free_dofs(nel: int) -> np.ndarray:
    """All DOFs except the clamped base node (w0, theta0)."""
    return np.arange(2, 2 * (nel + 1))


def buckling_factor(K: np.ndarray, KG: np.ndarray, nel: int) -> float:
    """Smallest positive ``lambda`` solving ``K phi = lambda K_G phi``.

    Solved as ``K_G phi = mu K phi`` (``mu = 1/lambda``); the largest positive
    ``mu`` gives the smallest positive ``lambda``.  Returns ``+inf`` when the
    geometric stiffness cannot destabilise the column.
    """
    f = _free_dofs(nel)
    Kff = K[np.ix_(f, f)]
    KGff = KG[np.ix_(f, f)]
    mu = eig(KGff, Kff, right=False)
    mu = mu[np.isfinite(mu)].real
    mu = mu[mu > 1e-12]
    if mu.size == 0:
        return math.inf
    return 1.0 / float(mu.max())


def deflection(
    K: np.ndarray, KG: np.ndarray, mesh: BeamMesh, F: float
) -> np.ndarray | None:
    """Second-order nodal deflection under lateral tip force ``F``.

    Solves ``(K - K_G) u = f`` on the free DOFs.  Returns the transverse
    deflection at every node, or ``None`` if the softened stiffness is singular
    / indefinite (i.e. at or beyond buckling).
    """
    nel = len(mesh.L)
    f = _free_dofs(nel)
    Keff = (K - KG)[np.ix_(f, f)]
    rhs = np.zeros(f.size)
    tip_transverse = 2 * nel - 2  # index of tip w-DOF within the free set
    rhs[tip_transverse] = F
    try:
        uf = solve(Keff, rhs, assume_a="sym")
    except Exception:
        return None
    # reject non-physical (negative-stiffness) solutions
    if not np.all(np.isfinite(uf)):
        return None
    u = np.zeros(2 * (nel + 1))
    u[f] = uf
    w = u[0::2]  # transverse deflection at each node
    if w[-1] * F < 0:  # deflection opposing the load -> past buckling
        return None
    return w


def bending_moment(
    mesh: BeamMesh, w_nodes: np.ndarray, F: float, P: float
) -> np.ndarray:
    """Second-order bending moment at each node, recovered from statics.

    ``M(z) = F (H - z) + P (w_tip - w(z)) + integral over the self-weight of the
    horizontal offsets (w(s) - w(z))``.  With ``w = 0`` (first-order request)
    this reduces to the tip-load cantilever moment ``F (H - z)``.
    """
    z = mesh.z_nodes
    H = z[-1]
    M_first = F * (H - z)  # tip-load cantilever moment
    if not np.any(w_nodes):  # first-order request (w == 0): short-circuit
        return M_first

    w_tip = w_nodes[-1]
    seg_weight = mesh.w_line * mesh.L  # (nel,)
    w_cent = 0.5 * (w_nodes[:-1] + w_nodes[1:])  # element centroid deflection
    # sum over elements above each node i of seg_weight[e] * w_cent[e]
    sw = seg_weight * w_cent
    # suffix sums: contrib_above[i] = sum_{e>=i} sw[e], W_above[i] = sum_{e>=i} seg_weight[e]
    contrib_above = np.concatenate([np.cumsum(sw[::-1])[::-1], [0.0]])
    W_above = np.concatenate([np.cumsum(seg_weight[::-1])[::-1], [0.0]])
    M = M_first + P * (w_tip - w_nodes) + contrib_above - W_above * w_nodes
    return M
