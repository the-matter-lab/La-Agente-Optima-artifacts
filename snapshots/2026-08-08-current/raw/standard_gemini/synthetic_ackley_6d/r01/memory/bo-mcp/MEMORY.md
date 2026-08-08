# BO-MCP Campaign Script Authoring Caveats

- **Idempotency Key Generation**: `BoMcpClient.make_idempotency_key` is a static method that requires at least one positional argument `prefix` (e.g., `client.make_idempotency_key("prefix", "part1", "part2")`). Calling it without arguments will raise a `TypeError`.
- **Campaign Lifecycle Actions**: The allowed actions for `BoMcpClient.lifecycle` are `"pause"`, `"resume"`, `"terminate"`, and `"reopen"`.
- **Suggestion Status Updates**: The allowed statuses for `BoMcpClient.update_suggestion_status` are `"accepted"`, `"rejected"`, and `"expired"`.
