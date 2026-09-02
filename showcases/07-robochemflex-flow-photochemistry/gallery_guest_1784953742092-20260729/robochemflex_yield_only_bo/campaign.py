from __future__ import annotations

import argparse

from .continuation import run as run_continuation
from .recreate import run as run_recreation


def run(args: argparse.Namespace) -> None:
    if getattr(args, "mode", "recreate") == "continue":
        run_continuation(args)
    else:
        run_recreation(args)
