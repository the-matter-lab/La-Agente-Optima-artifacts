#!/usr/bin/env python
# run_direct_arylation.py

import sys
from pathlib import Path

# Find the repository root dynamically by looking for 'domains' in parent directories
current_dir = Path(__file__).resolve().parent
repo_root = None
for parent in [current_dir] + list(current_dir.parents):
    if (parent / "domains" / "bo_mcp" / "client.py").exists():
        repo_root = parent
        break

if repo_root and str(repo_root) not in sys.path:
    sys.path.insert(0, str(repo_root))

import argparse
import logfire

# Configure Logfire and instrument requests
try:
    from grafico.core.logfire_config import configure_logfire
    configure_logfire()
except ImportError:
    logfire.configure()

logfire.instrument_requests()

# Ensure stdout is unbuffered for tagged lines
sys.stdout.reconfigure(line_buffering=True)

from direct_arylation.campaign import run_campaign

def main():
    parser = argparse.ArgumentParser(
        description="Direct Arylation Reaction-Yield Optimization Campaign"
    )
    parser.add_argument(
        "--campaign-id",
        type=str,
        default=None,
        help="Optional campaign ID to resume/reopen."
    )
    parser.add_argument(
        "--budget",
        type=int,
        default=60,
        help="Maximum number of attempted evaluations (default: 60)."
    )
    parser.add_argument(
        "--stop-file",
        type=str,
        default="STOP",
        help="Path to the stop file (default: STOP)."
    )
    parser.add_argument(
        "--poll-s",
        type=int,
        default=180,
        help="Polling interval in seconds (default: 180)."
    )
    parser.add_argument(
        "--heartbeat-s",
        type=int,
        default=1800,
        help="Heartbeat interval in seconds (default: 1800)."
    )
    
    args = parser.parse_args()
    
    try:
        campaign_id = run_campaign(
            campaign_id=args.campaign_id,
            budget=args.budget,
            stop_file=args.stop_file,
            poll_s=args.poll_s,
            heartbeat_s=args.heartbeat_s
        )
        
        # Print the required final line
        print(f"BO_MCP_CAMPAIGN_ID={campaign_id}")
        
    except Exception as e:
        print(f"[ALERT] Campaign execution failed: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()
