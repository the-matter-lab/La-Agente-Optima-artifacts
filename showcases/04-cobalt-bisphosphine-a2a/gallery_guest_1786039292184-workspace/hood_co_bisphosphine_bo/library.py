from __future__ import annotations

from dataclasses import asdict, dataclass
from itertools import combinations_with_replacement

LINKERS = ("ethylene", "propylene", "1,2-phenylene", "cis-1,2-cyclohexylene")
SUBSTITUENTS = (
    "Me",
    "Et",
    "iPr",
    "Cy",
    "Ph",
    "p-Tol",
    "p-Anisyl",
    "p-CF3-Ph",
)
SUBSTITUENT_FULL_NAMES = {
    "Me": "methyl",
    "Et": "ethyl",
    "iPr": "isopropyl",
    "Cy": "cyclohexyl",
    "Ph": "phenyl",
    "p-Tol": "4-methylphenyl",
    "p-Anisyl": "4-methoxyphenyl",
    "p-CF3-Ph": "4-trifluoromethylphenyl",
}

_LINKER_CODE = {
    "ethylene": "eth",
    "propylene": "prop",
    "1,2-phenylene": "ophen",
    "cis-1,2-cyclohexylene": "cchex",
}

# Compact, deterministic chemistry-inspired descriptors for BayBE custom categoricals.
_SUB_DESC = {
    "Me": (0.0, 0.0, 0.0),
    "Et": (0.2, 0.0, 0.0),
    "iPr": (0.45, 0.0, 0.0),
    "Cy": (0.70, 0.1, 0.0),
    "Ph": (0.55, 0.5, 0.0),
    "p-Tol": (0.65, 0.5, -0.1),
    "p-Anisyl": (0.68, 0.5, -0.3),
    "p-CF3-Ph": (0.82, 0.5, 0.4),
}
_LINKER_DESC = {
    "ethylene": (0.0, 0.0),
    "propylene": (0.25, 0.0),
    "1,2-phenylene": (0.55, 1.0),
    "cis-1,2-cyclohexylene": (0.45, 0.2),
}

WARM_START_CANDIDATE_IDS = (
    "eth__Me__Me",
    "prop__iPr__Ph",
    "ophen__pAnisyl__pCF3Ph",
    "cchex__Cy__pTol",
)


@dataclass(frozen=True)
class Candidate:
    candidate_id: str
    linker: str
    r1: str
    r2: str
    ligand_label: str
    ligand_description: str
    symmetric: bool

    def asdict(self) -> dict:
        return asdict(self)


def _token(text: str) -> str:
    return text.replace(",", "").replace(" ", "").replace("-", "").replace("/", "")


def build_library() -> list[Candidate]:
    candidates: list[Candidate] = []
    for linker in LINKERS:
        for r1, r2 in combinations_with_replacement(SUBSTITUENTS, 2):
            cid = f"{_LINKER_CODE[linker]}__{_token(r1)}__{_token(r2)}"
            ligand = f"{r1}2P-{linker}-P{r2}2"
            desc = (
                f"bidentate bisphosphine {ligand}; linker={linker}; "
                f"one phosphorus bears two {SUBSTITUENT_FULL_NAMES[r1]} groups and "
                f"the other phosphorus bears two {SUBSTITUENT_FULL_NAMES[r2]} groups"
            )
            candidates.append(Candidate(cid, linker, r1, r2, ligand, desc, r1 == r2))
    return candidates


def library_by_id() -> dict[str, Candidate]:
    return {c.candidate_id: c for c in build_library()}


def library_summary() -> dict:
    lib = build_library()
    ids = [c.candidate_id for c in lib]
    seen_pairs = {(c.linker, c.r1, c.r2) for c in lib}
    reverse_dupes = [c for c in lib if c.r1 != c.r2 and (c.linker, c.r2, c.r1) in seen_pairs]
    per_linker = {linker: sum(c.linker == linker for c in lib) for linker in LINKERS}
    symmetric = sum(c.symmetric for c in lib)
    return {
        "total_candidates": len(lib),
        "candidates_per_linker": per_linker,
        "symmetric_R1_eq_R2": symmetric,
        "unsymmetric_R1_neq_R2": len(lib) - symmetric,
        "duplicate_candidate_ids": len(ids) - len(set(ids)),
        "duplicate_R1_R2_permutations_remaining": len(reverse_dupes),
    }


def baybe_custom_descriptors() -> dict[str, dict[str, float]]:
    descriptors: dict[str, dict[str, float]] = {}
    for idx, cand in enumerate(build_library()):
        s1 = _SUB_DESC[cand.r1]
        s2 = _SUB_DESC[cand.r2]
        l0, l1 = _LINKER_DESC[cand.linker]
        descriptors[cand.candidate_id] = {
            "linker_size": float(l0),
            "linker_rigidity": float(l1),
            "sub_steric_mean": float((s1[0] + s2[0]) / 2.0),
            "sub_steric_delta": float(abs(s1[0] - s2[0])),
            "aryl_fraction": float((s1[1] + s2[1]) / 2.0),
            "electronic_mean": float((s1[2] + s2[2]) / 2.0),
            "electronic_delta": float(abs(s1[2] - s2[2])),
            "symmetric": 1.0 if cand.symmetric else 0.0,
            "identity_code": float(idx) / 143.0,
        }
    return descriptors
