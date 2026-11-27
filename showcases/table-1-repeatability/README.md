# Repeat evaluations for Table 1

These checks support the repeat evaluations reported alongside Table 1 in *Finite-space discovery across chemistry and materials*. They compare the best seed and final candidate for emitters and Xe/Kr MOFs, and check objective values for one ligand each in the cobalt and phosphine campaigns. The [showcase index](../README.md#contents) lists the original campaign archives (02–05).

| Check | Inputs and method | Recorded results |
|---|---|---|
| Emitters | `emitters/conformers.py` starts from the two SMILES and uses RDKit and CREST/GFN2-xTB. `solve.py` evaluates the selected conformer using GPU4PySCF TD-DFT. Each molecule has three repeat folders with the initial and selected coordinates. | `emitters/results.csv` contains the six evaluations. `summarize.py` aggregates them into `summary.json`. The mean seed-minus-candidate gap was 3.576 meV. |
| Xe/Kr MOFs | `mofs/` contains the archived best seed and final candidate CIFs. Zeo++ 0.3 evaluated each structure three times at 5,000 pore-volume sampling points and once at 50,000. | `mofs/mof-verification.json` records the commands, input identifiers, sampling settings, per-run values and archived scores. |
| Cobalt methyl seed | `cobalt/optimize.py` reads `methyl/build.json` and `methyl/start.xyz`, optimizes the geometry, and scores the endpoint. Its local dependencies are `xyz.py` and the files under `reference/`. The driver imports the checkpoint parser for the methyl doublet. | Compare `cobalt/methyl/result.json` with `cobalt/reference/archived_objectives.json`. The saved optimized geometry and PySCF checkpoint are in `methyl/`. |
| Trimethylphosphine | `phosphine/trimethylphosphine.json` contains the three original P_0001 evaluation records and their archive paths. The first two are pre-search tests and the third is the campaign evaluation. | The four objective values match across all three records. |

The emitter and cobalt repeats ran on an NVIDIA RTX A4000 with PySCF 2.10.0 and GPU4PySCF 1.5.0. The cobalt optimizer also uses geomeTRIC. The emitter environment record lists the Python, RDKit, CREST, CuPy and QCElemental versions. The conformer script locates CREST and its companion executables on PATH.

For the cobalt checkpoint check, two separate Python processes read the same saved file with the archived evaluator and applied `electronic_activation_components` from `reference/descriptors.py`. Both returned an electronic activation score of −0.08263507886282095. The packaged parser retains the three checkpoint descriptors used for this score. The checkpoint SHA-256 is `ba3c790a32693cb7acbd87e0da552002f3bf80bc7a09018201071531778c9e4a`.
