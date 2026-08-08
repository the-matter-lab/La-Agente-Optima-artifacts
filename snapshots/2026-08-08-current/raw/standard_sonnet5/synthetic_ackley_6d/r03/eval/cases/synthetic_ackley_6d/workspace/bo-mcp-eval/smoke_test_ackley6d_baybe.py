"""Ephemeral smoke test (not part of the deliverable package).

Creates the real Ackley-6D BayBE campaign (marker-bearing name), runs a
temporarily reduced budget so only one generate/evaluate/submit round
happens, then pauses. The resulting campaign can be resumed later with
--campaign-id to continue to the full 60-evaluation budget.
"""
import logfire
from grafico.core.logfire_config import configure_logfire

configure_logfire()
logfire.instrument_requests()

from domains.bo_mcp.client import BoMcpClient

import ackley6d_baybe.campaign as camp

camp.TOTAL_EVALUATION_BUDGET = 4  # smoke-test only; real script uses 60

client = BoMcpClient.from_env()
campaign_id = camp.create_or_resume(client, None)
print("SMOKE_CAMPAIGN_ID", campaign_id)
summary = camp.run(client, campaign_id, f"artifacts/{campaign_id}", "STOP_SMOKE", 1800.0)
print("SMOKE_SUMMARY", summary)
