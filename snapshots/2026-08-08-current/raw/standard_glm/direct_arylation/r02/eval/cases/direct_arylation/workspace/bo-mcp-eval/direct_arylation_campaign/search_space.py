"""Search-space definition for the direct arylation benchmark.

Three parameters (base, ligand, solvent) are declared as categorical
(string-valued) to preserve exact spelling.  Two parameters
(concentration, temperature_c) are declared as discrete numeric so
BO-MCP and the oracle both receive JSON numbers, not strings.
"""

MARKER = "akg-eval-d9613e26762c4c47a426799e86b370f2"
NONCE = "a375b9bd-ae19-499a-9006-4ecc7a3bc68d"

# Exact parameter names and values as required by the oracle.
# Categorical parameters use string lists; discrete numeric parameters
# use float lists so BO-MCP and the oracle both see JSON numbers.
CATEGORICAL_PARAMS = {
    "base": [
        "Potassium acetate",
        "Potassium pivalate",
        "Cesium acetate",
        "Cesium pivalate",
    ],
    "ligand": [
        "BrettPhos",
        "Di-tert-butylphenylphosphine",
        "(t-Bu)PhCPhos",
        "Tricyclohexylphosphine",
        "PPh3",
        "XPhos",
        "P(2-furyl)3",
        "Methyldiphenylphosphine",
        "1268824-69-6",
        "JackiePhos",
        "SCHEMBL15068049",
        "Me2PPh",
    ],
    "solvent": [
        "DMAc",
        "Butyornitrile",
        "Butyl Ester",
        "p-Xylene",
    ],
}

DISCRETE_NUMERIC_PARAMS = {
    "concentration": [0.057, 0.1, 0.153],
    "temperature_c": [90, 105, 120],
}

# Total search-space size: 4 * 12 * 4 * 3 * 3 = 1728
TOTAL_SPACE_SIZE = 1
for _v in CATEGORICAL_PARAMS.values():
    TOTAL_SPACE_SIZE *= len(_v)
for _v in DISCRETE_NUMERIC_PARAMS.values():
    TOTAL_SPACE_SIZE *= len(_v)


def build_parameters() -> list[dict]:
    """Return the BO-MCP intake ``parameters`` list.

    Categorical parameters (base, ligand, solvent) are declared as
    ``categorical`` with string categories.  Discrete numeric parameters
    (concentration, temperature_c) are declared as ``discrete`` with
    explicit float/int values so BO-MCP returns them as numbers and the
    oracle payload uses JSON numbers.
    """
    params: list[dict] = []
    for name, categories in CATEGORICAL_PARAMS.items():
        params.append(
            {
                "name": name,
                "type": "categorical",
                "categories": categories,
            }
        )
    for name, values in DISCRETE_NUMERIC_PARAMS.items():
        params.append(
            {
                "name": name,
                "type": "discrete",
                "values": values,
            }
        )
    return params
