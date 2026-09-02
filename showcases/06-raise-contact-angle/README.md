# 06 — Closed-loop contact-angle matching on RAISE

Reported in the main text, *Results → Closed-loop formulation optimization with
RAISE*, and in SI `si:raise`.

A complete closed-loop optimization session on the RAISE self-driving laboratory
platform: find an ethanol / sodium dodecyl sulfate aqueous mixture whose static
contact angle on the RAISE substrate matches 65°, stopping when a measurement
falls inside [64°, 66°]. Initial search space: ethanol 0–60 v/v %, SDS
0–1 w/v %. Two warm-start formulations were derived from a literature web
search, and the campaign proceeded in small, explicitly approved increments.

Division of labour: the *bo-raise-specialist* subagent authored and revised the
Python campaign package, entry point, and runbook — inspecting the BO-MCP
OpenAPI description for the current service contract before each change, and
validating with compile, CLI, dry-run and disposable-campaign smoke tests —
while Óptima executed the operator-approved increments against a BayBE-backed
BO-MCP campaign. The archived trace spans 11 operator turns.

## Contents

`gallery_guest_1784132581189/` — chat and workspace archived as one directory.

- `conversation_019f6697_full.json` — the full conversation export
  (`019f6697-3d52-749e-a1db-2c8a22764ad1`, Logfire trace
  `019f67265cae1faf70ab95ff86276e24`, 2026-07-15). At 4.1 MB this is the largest
  file in `showcases/`.
- `run_ethanol_sds_contact_angle_65.py`, `continue_…py`,
  `HOW_TO_EXECUTE_CAMPAIGN.md` — the specialist-authored campaign package and
  runbook.
- `campaign_manifest.json`, `ethanol_sds_contact_angle_65/` — campaign
  definition and package.
- `artifacts/ethanol_sds_contact_angle_65/<timestamp>__<hash>/` — one directory
  per approved increment, holding the BO-MCP campaign export and run logs, plus
  `analysis/` and `logs/`.

The SI states that the orchestrator and all five bo-raise-specialist subagent
runs were exported as pydantic-ai message histories; what survives in this
archive is the single combined conversation export above.
