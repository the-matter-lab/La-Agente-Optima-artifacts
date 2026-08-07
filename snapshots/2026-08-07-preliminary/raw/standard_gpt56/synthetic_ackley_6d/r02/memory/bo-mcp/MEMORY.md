## BO/PySCF script execution in read-only `/app`
- In a writable shared workspace where plain `uv run` tries and fails to rebuild the editable `/app` package, use `PYTHONPATH=/app:. uv run --project /app --no-sync python ...`. This imports `domains`/`grafico` from `/app` without attempting to write `grafico.egg-info` under the read-only repository.
