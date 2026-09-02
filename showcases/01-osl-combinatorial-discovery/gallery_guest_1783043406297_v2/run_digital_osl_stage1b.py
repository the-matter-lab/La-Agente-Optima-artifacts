from __future__ import annotations

import sys
import warnings

import logfire
from grafico.core.logfire_config import configure_logfire

try:
    from pydantic_graph import PydanticGraphDeprecationWarning
except Exception:  # noqa: BLE001
    PydanticGraphDeprecationWarning = None
else:
    warnings.filterwarnings("ignore", category=PydanticGraphDeprecationWarning)

configure_logfire()
logfire.instrument_requests()

from digital_osl_stage1b.campaign import cli_main


if __name__ == "__main__":
    raise SystemExit(cli_main(sys.argv[1:]))
