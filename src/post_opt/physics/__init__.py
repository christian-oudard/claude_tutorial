"""Pure-function physics for the axisymmetric post optimizer.

Each submodule holds first-principles mechanics with no optimizer state:

* :mod:`geometry`     - section properties, volumes, weights
* :mod:`stress`       - normal / shear / torsion / punching / plate bending
* :mod:`buckling`     - Greenhill + Euler + Dunkerley, amplification factor
* :mod:`deflection`   - second-order (P-delta) tip deflection & moment
* :mod:`overturning`  - kern and partial-uplift rigid-body stability
* :mod:`bearing`      - soil pressure
"""
