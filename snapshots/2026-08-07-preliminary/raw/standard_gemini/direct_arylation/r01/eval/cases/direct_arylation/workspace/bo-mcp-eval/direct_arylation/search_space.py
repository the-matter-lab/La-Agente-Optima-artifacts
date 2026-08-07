# Search space definition for direct arylation campaign

def get_parameters() -> list[dict]:
    """Return the list of input parameters for the direct arylation campaign."""
    return [
        {
            "name": "base",
            "type": "categorical",
            "categories": [
                "Potassium acetate",
                "Potassium pivalate",
                "Cesium acetate",
                "Cesium pivalate"
            ]
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
                "Me2PPh"
            ]
        },
        {
            "name": "solvent",
            "type": "categorical",
            "categories": [
                "DMAc",
                "Butyornitrile",
                "Butyl Ester",
                "p-Xylene"
            ]
        },
        {
            "name": "concentration",
            "type": "discrete",
            "values": [0.057, 0.1, 0.153]
        },
        {
            "name": "temperature_c",
            "type": "discrete",
            "values": [90.0, 105.0, 120.0]
        }
    ]
