{
  description = "xmrig_exporter development environment";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
    flake-utils.url = "github:numtide/flake-utils";
  };

  outputs = { self, nixpkgs, flake-utils }:
    flake-utils.lib.eachDefaultSystem (system:
      let
        pkgs = nixpkgs.legacyPackages.${system};
        pythonEnv = pkgs.python3.withPackages (ps: with ps; [
          requests
          prometheus-client
          pyyaml
          pytest
          pytest-mock
        ]);
      in
      {
        devShells.default = pkgs.mkShell {
          buildInputs = [
            pythonEnv
            pkgs.python3Packages.pip
            pkgs.python3Packages.setuptools
          ];

          shellHook = ''
            echo "xmrig_exporter development environment"
            echo "Python version: $(python --version)"
            echo ""
            echo "Available commands:"
            echo "  python -m xmrig_exporter --help"
            echo "  pytest tests/"
            echo "  pip install -e ."
          '';
        };
      }
    );
}
