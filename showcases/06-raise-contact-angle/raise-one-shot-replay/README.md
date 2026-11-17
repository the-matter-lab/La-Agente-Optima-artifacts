# RAISE one-shot selection replay

Ten separate requests were made with `gpt-5.5` via the LiteLLM OpenAI Responses endpoint, using Pydantic AI 1.97.0 and Python 3.13. No sampling seed or temperature was specified. Runs 1–5 and 6–10 were collected in two batches. Each request used the same prior main-agent messages and prompt.

`metadata.json` records the prompt, the SHA-256 hash of the canonicalized input history, and model settings. `run-01.json` through `run-10.json` preserve the complete returned text and token usage. Agent already suggested high-ethanol candidates, including (45, 0.75) and (50, 0.75) in its prior message history before the final request for a one-shot suggestion (and therefore the replay of ten separate requests). 

| Runs | Ethanol (v/v%) | SDS (w/v%) |
|---|---:|---:|
| 1 | 49 | 0.75 |
| 2–4, 6, 8–10 | 50 | 0.75 |
| 5, 7 | 45 | 0.75 |
