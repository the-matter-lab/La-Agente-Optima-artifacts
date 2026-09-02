# Phosphine electronic-tuning BO report

## Multi-objective strategy
Finite discrete `candidate_id` categorical campaign using BO-MCP with Pareto scalarization and hypervolume-improvement acquisition where supported. The evaluator submits raw transformed objectives, so post-warm-start proposals are based on measured HOMO-target error, gap-target error, steric excess, and heavy-atom count rather than LLM chemical judgement.

Successful evaluations in this artifact: 3; failed evaluations: 0.
Observed Pareto-front size: 3.
BO-discovered Pareto members after warm start: 1. Initial-design Pareto members still present: 2.

## Representative trade-off ligands (up to 10)
- P_0002 Me/Me/Ph pareto=True HOMO=-5.735 eV gap=4.823 eV P_charge=0.064 volume=143.1 A^3 heavy=9
- P_0003 Me/Ph/Ph pareto=True HOMO=-5.893 eV gap=5.074 eV P_charge=0.092 volume=197.7 A^3 heavy=14
- P_0001 Me/Me/Me pareto=True HOMO=-5.577 eV gap=4.573 eV P_charge=0.036 volume=88.2 A^3 heavy=4

## Failed candidates
- None recorded in this artifact.

## Initial-design improvement check
BO improved the observed front/trade-off set if at least one `phase=bo` row is marked Pareto or representative in `report.csv`; inspect the CSV for the definitive row-level status.

## Substituent trend summary near the current trade-off set
Representative substituent counts: Me:6, Ph:3. Interpret phosphorus charge together with HOMO: less negative HOMO values and less positive/more negative P charges both indicate stronger donor character, but no standalone P-charge target was imposed.
