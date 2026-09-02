from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd
from rdkit import Chem
from rdkit.Chem import AllChem


SUZUKI_COUPLING_SMARTS = "[#6:1][B:2].[Br:3][c,C:4]>>[#6:1][c,C:4].[B:2].[Br:3]"
TRANS_ALKENE_SMARTS = "[#6:1][c,C:2]=[c,C:3][#6:4]>>[#6:1]/[C:2]=[C:3]/[#6:4]"
CIS_ALKENE_SMARTS = "[#6:1][c,C:2]=[c,C:3][#6:4]>>[#6:1]/[C:2]=[C:3]\\[#6:4]"

TRANS_BRIDGES = {"B001", "B003", "B027", "B058", "B065"}
CIS_BRIDGES = {"B030", "B066"}


def parse_candidate_identifier(identifier: str) -> tuple[str, str, str]:
    if len(identifier) != 12:
        raise ValueError("Expected identifier shaped like A001B003C001")

    cap_id = identifier[:4]
    bridge_id = identifier[4:8]
    core_id = identifier[8:12]
    if cap_id[0] != "A" or bridge_id[0] != "B" or core_id[0] != "C":
        raise ValueError("Expected identifier shaped like A001B003C001")

    return cap_id, bridge_id, core_id


class DigitalOslProductSmiles:
    def __init__(self, fragments: dict[str, str]):
        self._fragments = fragments
        self._suzuki_coupling = AllChem.ReactionFromSmarts(SUZUKI_COUPLING_SMARTS)
        self._trans_alkene = AllChem.ReactionFromSmarts(TRANS_ALKENE_SMARTS)
        self._cis_alkene = AllChem.ReactionFromSmarts(CIS_ALKENE_SMARTS)

    @classmethod
    def from_default_catalogs(
        cls, catalog_dir: Path | str | None = None
    ) -> "DigitalOslProductSmiles":
        if catalog_dir is None:
            catalog_dir = Path(__file__).resolve().parent
        catalog_dir = Path(catalog_dir)

        fragments: dict[str, str] = {}
        for filename in (
            "adk9227_data_s1.csv",
            "adk9227_data_s2.csv",
            "adk9227_data_s3.csv",
        ):
            data = pd.read_csv(catalog_dir / filename)
            fragments.update(dict(zip(data["hid"], data["smiles"], strict=True)))

        return cls(fragments)

    def generate_from_identifier(self, identifier: str) -> str:
        cap_id, bridge_id, core_id = parse_candidate_identifier(identifier)
        return self.generate(cap_id, bridge_id, core_id)

    def generate(self, cap_id: str, bridge_id: str, core_id: str) -> str:
        cap_bridge = self._couple(
            self._mol_from_hid(cap_id), self._mol_from_hid(bridge_id)
        )
        cap_bridge_core = self._couple(cap_bridge, self._mol_from_hid(core_id))
        pentamer = self._couple(cap_bridge, cap_bridge_core)
        pentamer = self._apply_bridge_stereochemistry(pentamer, bridge_id)
        return Chem.MolToSmiles(pentamer)

    def _mol_from_hid(self, hid: str) -> Chem.Mol:
        smiles = self._fragments[hid].replace("I", "Br")
        mol = Chem.MolFromSmiles(smiles)
        if mol is None:
            raise ValueError(f"Invalid SMILES for {hid}: {smiles}")
        return mol

    def _couple(self, boron_reactant: Chem.Mol, bromide_reactant: Chem.Mol) -> Chem.Mol:
        products = self._suzuki_coupling.RunReactants(
            (boron_reactant, bromide_reactant)
        )
        if not products:
            raise ValueError("Suzuki coupling produced no products")
        return products[0][0]

    def _apply_bridge_stereochemistry(
        self, product: Chem.Mol, bridge_id: str
    ) -> Chem.Mol:
        if bridge_id in TRANS_BRIDGES:
            return self._apply_alkene_reaction_twice(product, self._trans_alkene)
        if bridge_id in CIS_BRIDGES:
            return self._apply_alkene_reaction_twice(product, self._cis_alkene)
        return product

    def _apply_alkene_reaction_twice(
        self, product: Chem.Mol, reaction: AllChem.ChemicalReaction
    ) -> Chem.Mol:
        # The pentamer has two bridge-derived alkene sites; canonicalizing between
        # reaction passes keeps RDKit's product atom state consistent.
        for _ in range(2):
            products = reaction.RunReactants((product,))
            if not products:
                raise ValueError("Alkene stereochemistry reaction produced no products")
            product = Chem.MolFromSmiles(Chem.MolToSmiles(products[0][0]))
            if product is None:
                raise ValueError("RDKit could not sanitize stereochemical product")
        return product


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate the A-B-C-B-A product SMILES for a digital OSL candidate.",
    )
    parser.add_argument(
        "identifier", nargs="?", help="Candidate identifier, for example A001B003C001"
    )
    parser.add_argument("--cap", help="Cap building block id, for example A001")
    parser.add_argument("--bridge", help="Bridge building block id, for example B003")
    parser.add_argument("--core", help="Core building block id, for example C001")
    parser.add_argument(
        "--catalog-dir",
        type=Path,
        default=Path(__file__).resolve().parent,
        help="Directory containing adk9227_data_s1/s2/s3.csv",
    )
    args = parser.parse_args()

    generator = DigitalOslProductSmiles.from_default_catalogs(args.catalog_dir)
    if args.identifier:
        print(generator.generate_from_identifier(args.identifier))
        return

    if args.cap is None or args.bridge is None or args.core is None:
        parser.error("provide either an identifier or --cap, --bridge, and --core")
    print(generator.generate(args.cap, args.bridge, args.core))


if __name__ == "__main__":
    main()
