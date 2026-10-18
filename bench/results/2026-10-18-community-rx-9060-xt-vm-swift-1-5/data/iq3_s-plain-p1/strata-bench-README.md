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
- Context: 131072 tokens; parallel slots: 1
- Settings: the install's own configuration, unchanged; thinking off for the suite; temperature 0

## Method

Run by `python tools/strata_bench.py --long` against the HTTP API of a Strata server (already running); model loading is not timed. One warm-up chat and a 1K prompt are discarded first. Every prompt starts with a unique tag, so the conversation cache cannot help the fresh-prompt tests.

- short chat: the three questions of `tools/ab_engine.py`, up to 100 new tokens, 3 runs
- 4K / 16K prompts: generated word lists sized by a calibration request, 24 new tokens, 3 fresh prompts each
- agent session: system prompt and four tools, then 5 turns that each add about 1500 words of a project file and continue from the model's own earlier answers (the way agent clients resend a conversation), 64 new tokens per turn, 3 sessions; the cache numbers come from the answer's usage (`cached_tokens`) and timings (`prompt_n`)
- concurrency (when run): N requests sent at the same moment, total tokens over the wall time of the burst, latency over all requests

## Results

| Configuration | Actual prompt tokens | Reused tokens | Generated tokens | Runs | Prompt tok/s median and range | Decode tok/s median and range | TTFT seconds median and range |
| --- | ---: | ---: | ---: | ---: | --- | --- | --- |
| short chat | 46 (43-51) | 0 | 100 (100-100) | 9 | not measured | 36.8 (33.1-43.2) | 0.82 (0.70-0.93) |
| 4K prompt, fresh | 4019 (4019-4019) | 0 (0-0) | 24 cap | 3 | 907.6 (837.3-909.7) | not measured | 4.46 (4.46-4.84) |
| 16K prompt, fresh | 16058 (16058-16058) | 0 (0-0) | 24 cap | 3 | 978.4 (956.3-979.7) | not measured | 16.45 (16.43-16.83) |
| 32K prompt, fresh | 32049 (32049-32049) | 0 (0-0) | 24 cap | 3 | 901.8 (864.2-903.2) | not measured | 35.59 (35.54-37.14) |
| agent session, follow-up turns | 14582 (14551-14588) at the last turn | see below | up to 64 | 3 | see below | 38.0 (34.5-46.8) | 4.09 (2.81-5.08) |

Ranges are the lowest and highest of the runs; `Runs` counts requests that returned a token.

### Agent session (conversation cache)

Cache hit over the follow-up turns: 68.6 % (68.4-68.6); earlier-turn tokens read again per session: 74 (73-144) (earlier turns that the cache did not hold; the 13718 (13718-13720) new tokens of the files are read once); first turn (nothing cached) first token: 2.00 s (1.98-2.02).

| Turn (run 1) | Prompt tokens | Reused | Read | Prompt tok/s | First token (s) | Decode tok/s |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 0 | 609 | 0 | 609 | 307.9 | 2.015 | 27.4 |
| 1 | 3744 | 622 | 3122 | 689.2 | 4.57 | 36.8 |
| 2 | 5277 | 3737 | 1540 | 481.8 | 3.236 | 36.5 |
| 3 | 8710 | 5270 | 3440 | 682.3 | 5.082 | 34.5 |
| 4 | 11636 | 8773 | 2863 | 636.2 | 4.541 | 46.8 |
| 5 | 14551 | 11652 | 2899 | 664.3 | 4.405 | 43.7 |

Per-request data: `results.json`. Engine log lines from the start: `engine-log-excerpt.txt` (when this run started the server).

## Correctness and limitations

Not measured: this is a speed suite. The conversation uses the model's own replies, so token counts differ a little between runs. Machine details come from the server, `nvidia-smi`/`rocm-smi` and the OS; background load and power limits are not recorded. Total time of the suite: 307 s.
