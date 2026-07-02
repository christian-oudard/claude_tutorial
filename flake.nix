{
  description = "Axisymmetric post optimizer (post-opt)";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-24.11";
    flake-utils.url = "github:numtide/flake-utils";
  };

  outputs = { self, nixpkgs, flake-utils }:
    flake-utils.lib.eachDefaultSystem (system:
      let
        pkgs = import nixpkgs { inherit system; };
        python = pkgs.python312;
        pyEnv = python.withPackages (ps: with ps; [ numpy scipy pytest ]);

        post-opt = python.pkgs.buildPythonPackage {
          pname = "post-opt";
          version = "0.1.0";
          src = ./.;
          format = "pyproject";
          nativeBuildInputs = [ python.pkgs.hatchling ];
          propagatedBuildInputs = with python.pkgs; [ numpy scipy ];
          nativeCheckInputs = [ python.pkgs.pytest ];
          checkPhase = ''
            runHook preCheck
            PYTHONPATH=$PWD/src pytest -q
            runHook postCheck
          '';
        };
      in
      {
        packages.default = post-opt;

        devShells.default = pkgs.mkShell {
          packages = [ pyEnv pkgs.uv ];
          shellHook = ''
            export PYTHONPATH=$PWD/src:$PYTHONPATH
            echo "post-opt dev shell — run: pytest"
          '';
        };

        # `nix flake check` runs the package build + its pytest checkPhase.
        checks.default = post-opt;
      });
}
