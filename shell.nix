# Legacy nix-shell support (for users without flakes)
{ pkgs ? import <nixpkgs> {} }:

pkgs.mkShell {
  buildInputs = with pkgs; [
    (python3.withPackages (ps: with ps; [
      requests
      prometheus-client
      pyyaml
      pytest
      pytest-mock
    ]))
    python3Packages.pip
    python3Packages.setuptools
  ];

  shellHook = ''
    echo "xmrig_exporter development environment (via shell.nix)"
    echo "Python version: $(python --version)"
    echo ""
    echo "Available commands:"
    echo "  python -m xmrig_exporter --help"
    echo "  pytest tests/"
    echo "  pip install -e ."
  '';
}
