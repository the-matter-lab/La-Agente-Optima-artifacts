"""Campaign intake construction for the direct arylation benchmark."""

from direct_arylation_campaign.search_space import MARKER, build_parameters


def build_intake(*, campaign_label: str = "run") -> dict:
    """Return a BO-MCP campaign intake dict.

    Parameters
    ----------
    campaign_label : str
        Short label appended after the marker to distinguish campaigns
        within the same invocation (e.g. ``"run"`` or ``"resume"``).

    Design choices
    --------------
    * Categorical parameters (base, ligand, solvent) preserve exact spelling;
      discrete numeric parameters (concentration, temperature_c) are sent as
      JSON numbers to the oracle.
    * ``batch_size=1`` — sequential evaluation so each observation
      informs the next suggestion (60 evaluations is a tight budget).
    * ``initial_design_size=8`` — Sobol warmup before model-driven
      acquisition; 8 points cover the 5-dimensional space sparsely
      but sufficiently for the GP to learn rough trends.
    * ``acquisition_method="expected_improvement"`` — classic EI for
      maximization; well-suited to small-budget categorical spaces.
    * ``backend="auto"`` — let the server pick the best backend.
    * No ``max_iterations`` — the CLI budget of 60 controls the loop;
      the intake is immutable and a fossilized cap would block reopens.
    """
    return {
        "name": f"direct-arylation-{MARKER}-{campaign_label}",
        "description": (
            "Direct arylation reaction-yield optimization. "
            f"Marker: {MARKER}. Nonce: a375b9bd-ae19-499a-9006-4ecc7a3bc68d"
        ),
        "parameters": build_parameters(),
        "objectives": [
            {
                "name": "yield",
                "direction": "maximize",
                "unit": "percent",
            }
        ],
        "batch_size": 1,
        "initial_design_size": 8,
        "acquisition_method": "expected_improvement",
        "backend": "auto",
    }
