# Community benchmark on AMD Radeon

Measured on 2026-10-17 with `tools/strata_bench.py` (suite 1, 3 runs per test, medians with ranges). Speeds are the engine's own timings; first-token times are measured by the client over HTTP. Speed only: no correctness check was run.

## Hardware and software

- GPU and VRAM: AMD Radeon, 16 GiB VRAM
- CPU: AMD Ryzen 5 3600 6-Core Processor (12 cores, 12 threads); installed RAM: 86.3 GiB; storage: not measured
- OS: Linux 6.12.111+deb13-amd64; GPU driver: not read; CUDA: not read
- Strata: project 0.1.45, commit 477ac13c; engine 0.1.45
- Background workloads and power limits: not recorded

## Model and configuration

- Model and quantization: swift-1.5-iq2_xs
- Context: 131072 tokens; parallel slots: 2
- Settings: the install's own configuration, unchanged; thinking off for the suite; temperature 0

## Method

Run by `python tools/strata_bench.py --clients 2 --long` against the HTTP API of a Strata server (already running); model loading is not timed. One warm-up chat and a 1K prompt are discarded first. Every prompt starts with a unique tag, so the conversation cache cannot help the fresh-prompt tests.

- short chat: the three questions of `tools/ab_engine.py`, up to 100 new tokens, 3 runs
- 4K / 16K prompts: generated word lists sized by a calibration request, 24 new tokens, 3 fresh prompts each
- agent session: system prompt and four tools, then 5 turns that each add about 1500 words of a project file and continue from the model's own earlier answers (the way agent clients resend a conversation), 64 new tokens per turn, 3 sessions; the cache numbers come from the answer's usage (`cached_tokens`) and timings (`prompt_n`)
- concurrency (when run): N requests sent at the same moment, total tokens over the wall time of the burst, latency over all requests

## Results

| Configuration | Actual prompt tokens | Reused tokens | Generated tokens | Runs | Prompt tok/s median and range | Decode tok/s median and range | TTFT seconds median and range |
| --- | ---: | ---: | ---: | ---: | --- | --- | --- |
| short chat | 46 (43-51) | 0 | 100 (100-100) | 9 | not measured | 38.5 (36.2-50.7) | 0.65 (0.59-0.74) |
| 4K prompt, fresh | 4019 (4019-4019) | 0 (0-0) | 24 cap | 3 | 809.9 (809.5-811.7) | not measured | 5.00 (4.99-5.00) |
| 16K prompt, fresh | 16058 (16058-16058) | 0 (0-0) | 24 cap | 3 | 1211.7 (1210.7-1212.5) | not measured | 13.29 (13.28-13.30) |
| 32K prompt, fresh | 32049 (32049-32049) | 0 (0-0) | 24 cap | 3 | 1198.8 (1198.8-1199.5) | not measured | 26.79 (26.77-26.80) |
| agent session, follow-up turns | 14534 (14530-14564) at the last turn | see below | up to 64 | 3 | see below | 41.9 (26.8-49.5) | 3.62 (2.26-5.42) |

Ranges are the lowest and highest of the runs; `Runs` counts requests that returned a token.

### Agent session (conversation cache)

Cache hit over the follow-up turns: 68.7 % (68.5-68.8); earlier-turn tokens read again per session: 4 (4-75) (earlier turns that the cache did not hold; the 13719 (13718-13719) new tokens of the files are read once); first turn (nothing cached) first token: 2.56 s (1.56-2.58).

| Turn (run 1) | Prompt tokens | Reused | Read | Prompt tok/s | First token (s) | Decode tok/s |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 0 | 609 | 0 | 609 | 241.3 | 2.559 | 38.1 |
| 1 | 3744 | 623 | 3121 | 685.2 | 4.592 | 37.6 |
| 2 | 5277 | 3807 | 1470 | 417.5 | 3.556 | 39.0 |
| 3 | 8710 | 5340 | 3370 | 691.4 | 4.912 | 44.7 |
| 4 | 11610 | 8748 | 2862 | 632.4 | 4.563 | 39.2 |
| 5 | 14534 | 11635 | 2899 | 870.6 | 3.366 | 26.8 |

### Concurrency: 2 clients

Total 35.0 tok/s (32.9-35.1); first token p50 1.481 s, p95 2.034 s; request latency p50 7.298 s, p95 7.774 s; errors 0. Server parallel slots: 2 (requests beyond that wait their turn).

Per-request data: `results.json`. Engine log lines from the start: `engine-log-excerpt.txt` (when this run started the server).

## Correctness and limitations

Not measured: this is a speed suite. The conversation uses the model's own replies, so token counts differ a little between runs. Machine details come from the server, `nvidia-smi`/`rocm-smi` and the OS; background load and power limits are not recorded. Total time of the suite: 284 s.
