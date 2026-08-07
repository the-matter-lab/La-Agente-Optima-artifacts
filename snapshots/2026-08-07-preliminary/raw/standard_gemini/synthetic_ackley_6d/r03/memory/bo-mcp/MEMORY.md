# BO-MCP Campaign Script Authoring Caveats

- **Python Environment**: The virtual environment `.venv` in `/app` may contain broken symlinks pointing to host-specific paths. Always use the system python `/opt/venv/bin/python3` or `python3` with `PYTHONPATH=/app` to run scripts.
- **Campaign Ownership**: Every campaign created, resumed, or reported must include the ownership marker `akg-eval-43dcff3d628d4a86ba717e0455386a93` in its name.
- **Graceful Shutdown**: Implement stop-file checks (e.g., checking for `STOP` in the current working directory) at the top of each loop iteration. If detected, delete the file, pause the campaign on the server using `client.lifecycle(campaign_id, action="pause")`, and exit gracefully.
- **Idempotency**: Use `client.make_idempotency_key` to generate stable keys for campaign creation and result submission to prevent duplicate operations.
