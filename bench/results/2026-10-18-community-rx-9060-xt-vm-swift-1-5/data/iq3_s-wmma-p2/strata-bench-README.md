# Community benchmark on AMD Radeon

Measured on 2026-10-17 with `tools/strata_bench.py` (suite 1, 3 runs per test, medians with ranges). Speeds are the engine's own timings; first-token times are measured by the client over HTTP. Speed only: no correctness check was run.

## Hardware and software

- GPU and VRAM: AMD Radeon, 16 GiB VRAM
- CPU: AMD Ryzen 5 3600 6-Core Processor (12 cores, 12 threads); installed RAM: 86.3 GiB; storage: not measured
- OS: Linux 6.12.111+deb13-amd64; GPU driver: not read; CUDA: not read
- Strata: project 0.1.45, commit 477ac13c; engine 0.1.45
- Background workloads and power limits: not recorded

## Model and configuration

- Model and quantization: swift-1.5-iq3_s
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
| short chat | 46 (43-51) | 0 | 100 (100-100) | 9 | not measured | 30.5 (25.7-37.8) | 0.94 (0.82-1.12) |
| 4K prompt, fresh | 4019 (4019-4019) | 0 (0-0) | 24 cap | 3 | 1098.5 (1018.1-1106.4) | not measured | 3.70 (3.67-4.00) |
| 16K prompt, fresh | 16058 (16058-16058) | 0 (0-0) | 24 cap | 3 | 1510.2 (1456.0-1510.2) | not measured | 10.68 (10.68-11.08) |
| 32K prompt, fresh | 32049 (32049-32049) | 0 (0-0) | 24 cap | 3 | 1482.5 (1482.1-1483.3) | not measured | 21.69 (21.67-21.70) |
| agent session, follow-up turns | 14563 (14546-14611) at the last turn | see below | up to 64 | 3 | see below | 32.7 (12.7-43.6) | 3.31 (2.47-5.45) |

Ranges are the lowest and highest of the runs; `Runs` counts requests that returned a token.

### Agent session (conversation cache)

Cache hit over the follow-up turns: 68.7 % (68.6-68.8); earlier-turn tokens read again per session: 4 (1-72) (earlier turns that the cache did not hold; the 13720 (13719-13721) new tokens of the files are read once); first turn (nothing cached) first token: 1.95 s (1.95-1.99).

| Turn (run 1) | Prompt tokens | Reused | Read | Prompt tok/s | First token (s) | Decode tok/s |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 0 | 609 | 0 | 609 | 313.9 | 1.985 | 21.5 |
| 1 | 3744 | 622 | 3122 | 812.4 | 3.885 | 23.2 |
| 2 | 5277 | 3807 | 1470 | 535.9 | 5.451 | 12.7 |
| 3 | 8710 | 5340 | 3370 | 851.2 | 4.002 | 31.8 |
| 4 | 11618 | 8756 | 2862 | 768.1 | 3.77 | 43.6 |
| 5 | 14546 | 11647 | 2899 | 813.9 | 3.604 | 32.7 |

### Concurrency: 2 clients

Total 24.1 tok/s (21.5-24.7); first token p50 2.532 s, p95 3.556 s; request latency p50 10.586 s, p95 11.882 s; errors 0. Server parallel slots: 2 (requests beyond that wait their turn).

Per-request data: `results.json`. Engine log lines from the start: `engine-log-excerpt.txt` (when this run started the server).

## Correctness and limitations

Not measured: this is a speed suite. The conversation uses the model's own replies, so token counts differ a little between runs. Machine details come from the server, `nvidia-smi`/`rocm-smi` and the OS; background load and power limits are not recorded. Total time of the suite: 279 s.
