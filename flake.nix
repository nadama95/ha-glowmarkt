{
  description = "Home Assistant Integration for Glowmarkt";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixpkgs-unstable";
  };

  outputs = { self, nixpkgs }:
    let
      system = "x86_64-linux";
      pkgs = nixpkgs.legacyPackages.${system};
    in
    {

      devShells.${system}.default = pkgs.mkShell {
        packages = with pkgs; [
          python3
          uv
        ];

        shellHook = ''
          source .venv/bin/activate
        '';

      };
    };
}
