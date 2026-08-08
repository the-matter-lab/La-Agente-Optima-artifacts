"""Fixed direct arylation search space. Do not expand it into a local result table."""


def build_parameters() -> list[dict]:
    return [
        {
            "name": "base",
            "type": "categorical",
            "categories": [
                "Potassium acetate",
                "Potassium pivalate",
                "Cesium acetate",
                "Cesium pivalate",
            ],
        },
        {
            "name": "ligand",
            "type": "categorical",
            "categories": [
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
        },
        {
            "name": "solvent",
            "type": "categorical",
            "categories": ["DMAc", "Butyornitrile", "Butyl Ester", "p-Xylene"],
        },
        {
            "name": "concentration",
            "type": "discrete",
            "values": [0.057, 0.1, 0.153],
        },
        {
            "name": "temperature_c",
            "type": "discrete",
            "values": [90, 105, 120],
        },
    ]
