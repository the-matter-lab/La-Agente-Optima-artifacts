## BO/PySCF campaign authoring note
- For BO campaign entrypoints that must keep stdout limited to tagged monitor lines, call `configure_logfire(console=False)` before `logfire.instrument_requests()`. This preserves request instrumentation without emitting untagged HTTP request lines to stdout in this container.
