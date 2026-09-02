# Logfire Message History Export

This directory contains the full `pydantic_ai.all_messages` exports for the
requested Logfire traces. The earlier summary-only attempt files were removed.

Each history is stored twice:

- `*.all_messages.json`: the raw message array from the root `agent run` span.
- `*.messages.jsonl`: one message per line with a `message_index` wrapper.

The `*.metadata.json` files and `full_message_histories_manifest.json` record
the source trace/span IDs and message counts.

Exported histories:

- `main_initial`: trace `019f1a0d9af0624a4eabdc42b555f0dc`, span `252cf34284f9cf13`, 6 messages.
- `subagent_initial_91e5a28c`: trace `019f1a0d9af0624a4eabdc42b555f0dc`, span `4c888742831071e7`, 78 messages.
- `main_continuation`: trace `019f1a3565e9304295ad313a5f458cfa`, span `e9ed6b927215bb19`, 32 messages.
- `subagent_continuation_1a74a8a8`: trace `019f1a3565e9304295ad313a5f458cfa`, span `fc07bce801151a4e`, 46 messages.

To refresh the export with a Logfire read/query token:

```bash
LOGFIRE_READ_TOKEN=... python scripts/export_logfire_message_histories.py
```
