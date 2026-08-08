## BO/PySCF script execution caveat
- In read-only `/app` evaluation workspaces, plain `uv run` may try to rebuild the editable `grafico` package and fail while creating `grafico.egg-info`. The observed working invocation is `PYTHONPATH=/app uv run --no-sync python ...`, which uses the active environment without attempting the editable rebuild.
