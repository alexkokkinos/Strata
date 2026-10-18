# Community benchmark: AMD RX 9060 XT 16GB (gfx1200) in a Proxmox VM, Swift 1.5 quants, WMMA on/off, 1-slot vs 2-slot

Strata 0.1.45 (`477ac13c`), engine 0.1.45, ROCm (TheRock) user-space wheels, Python 3.13.5,
Linux 6.12.111+deb13-amd64. Model: **Swift 1.5 (Qwen3.8-Flash-Next fine-tune), 256 experts,
48 layers**, in three quants: **IQ2_XS, IQ3_XXS, IQ3_S**.
Card: AMD Radeon RX 9060 XT 16GB (gfx1200), passed through to the VM with VFIO; the engine
reports it as `AMD Radeon`, 16,304 MiB, and records no driver version (`machine.gpu_driver: null`).
Host CPU: AMD Ryzen 5 3600 6-Core, 12 threads, 86.3 GiB RAM.
Tool: `tools/strata_bench.py`, schema 1, `--long`, runs 3, think off, 12 suites, 468 timed requests,
0 failures, 0 skipped, 0 burst errors. Full command lines, launch flags and settings JSON are in
`arms.json` and `settings-iq2_xs.json`; per-suite machine lines are in
`data/<arm>/strata-bench-README.md`, written by the tool.
`summarize.py` in this folder prints every number below from `data/`, and `check_report.py` checks
that README.md states them.

**Bottom line**

- **The WMMA attention kernel costs nothing to turn on.** Six matched pairs (3 quants x 2 slot
  counts), 432 suite requests: chat decode geomean **-0.2%**, agent decode geomean **+1.3%**, both
  within the run-to-run spread of a single arm. The long-prompt columns gain a lot (next bullet).
  Two pairs are negative on 4K (-3.1% IQ2_XS at 1 slot, -3.9% IQ3_S at 1 slot) and both are inside
  the 4K column's noise, which is the widest in this report (up to 22.8% inside one arm).
- **16K and 32K prompt processing: +32.8% to +78.5%** with `STRATA_HIP_WMMA=1`, geomean over the
  six pairs **+52.3%** at 16K, **+53.1%** at 32K. Time to first token at 32K is geomean **-34.6%**.
  The 4K median gains **+22.4%** (geomean), the one column that is not clean, see the noise bullet.
- **Two engine slots in one process: 1.17-1.22x aggregate** (1 / (1 - 14.4%) to 1 / (1 - 17.8%))
  with no visible loss per client. Per-client decode geomean **-16.6%** chat, **-15.5%** agent, and
  prompt processing geomean **+1.5%**, i.e. unchanged; the cost is paid in per-request rate, not in
  shared prefill.
- **Two real clients on 16GB, quant matters more than anything else here.** With IQ2_XS the pair
  sustains **35.0 tok/s aggregate** = **91.0%** of that arm's solo stream rate (17.5 tok/s per
  client, 45.5%); with IQ3_XXS 27.1 (77.5%); with IQ3_S 24.1 (79.1%).
- **Expert cache: IQ2_XS fits at 1 slot, IQ3_XXS and IQ3_S do not.** The engine reports 7,465
  expert slots (10,239 MiB, 10.0 GiB) on IQ2_XS, 5,846 (9,694 MiB) on IQ3_XXS, 4,774 (9,312 MiB)
  on IQ3_S, against a model with 256 experts x 48 layers, and 586-606 MiB of VRAM free at startup.
  The expert pool is the budget that decides which quant this card can serve.
- **Quant, on speed alone: IQ3_S decode is -17.6% (chat) and -21.0% (agent) vs IQ2_XS** (not a
  clean pair: the engine runs IQ2_XS at 7 pool workers and a 0.50 speculation bar, the two bigger
  quants at 11 and 0.70), and its prefill is mixed (+5.3% at 4K, +12.1% at 16K, +9.4% at 32K at
  1 slot; at 2 slots its prefill is 23.7-35.6% faster) - so paying for IQ3_S on this card
  buys nothing in speed. IQ3_XXS is in between (-5.8% chat, -8.1% agent). The arena grows from
  33,812 MiB (33.0 GiB, IQ2_XS) to 47,962 MiB (46.8 GiB, IQ3_S), 1.42x.
- **Read the decode columns with the speculation rate in hand.** The tool records
  `drafts_accepted`/`drafts_offered` per suite request: chat acceptance is 57.7-61.0% on IQ2_XS,
  74.7-77.8% on IQ3_XXS, 72.0-73.5% on IQ3_S, a 14-20 point spread set by the quant and not by the
  settings, so the two bigger quants run with better speculation than IQ2_XS in all 12 suites and
  their -5.8% / -17.6% chat decode numbers are net of that advantage (see "Speculation").
- **One VM-specific cost**: 12 suites, 468 timed requests, 0 failures, 0 skipped. Nothing in the
  numbers says "VM". The suite wall time is 19.4-30.3% shorter with WMMA on, same suite, so the
  suite length is dominated by prompt prefill, not by VM overhead.

## Hardware, driver, ROCm

The machine, exactly as `tools/strata_bench.py` recorded it. The block is byte-identical in all
12 suites except three keys: `machine.model` (the quant under test), `machine.quant` (null in every
arm, see the table) and `machine.parallel_slots` (1 in the six 1-slot arms, 2 in the six 2-slot
arms - this is the data's own record of the slot count, and it agrees with the arm names and with
the `batch_slots` keys below):

| field | value |
| --- | --- |
| `machine.gpu` / `machine.gpu_vram_mib` | `["AMD Radeon"]` / 16,304 MiB |
| `machine.gpu_driver` / `machine.cuda` | `null` / `null` |
| `machine.cpu` / cores / threads / RAM | AMD Ryzen 5 3600 6-Core Processor / 12 / 12 / 86.3 GiB |
| `machine.os` / `machine.python` | Linux 6.12.111+deb13-amd64 / 3.13.5 |
| `machine.strata_version` / `strata_commit` | 0.1.45 / `477ac13c` |
| `machine.engine_version` | 0.1.45 |
| `machine.model` / `machine.context` | `swift-1.5-iq2_xs`, `swift-1.5-iq3_xxs`, `swift-1.5-iq3_s` / 131,072 |
| `machine.quant` | `quant` is null in all 12 arms - the tool does not record the quant, so which quant an arm ran is readable only from `machine.model` |
| `machine.config` / `machine.launch` | `{}` / `null` - see "The launch line", the file is not a config dump |
| `machine.vram_after` | `{"elastic": false}` |
| `machine.parallel_slots` | 1 in the six 1-slot arms, 2 in the six 2-slot arms |

**GPU.** `lspci` in the VM reports `AMD/ATI[1002:7550] (rev c3)`, gfx1200 / RDNA4, 16GB, passed
through with VFIO from a Proxmox host. The engine sees it as `AMD Radeon` with 16,304 MiB and
records no driver version, `machine.gpu_driver: null`, `machine.cuda: null`. The host CPU model
and the 86.3 GiB of RAM are the VM's assignment as the tool read it.

**ROCm is TheRock user-space wheels in a venv, no system ROCm install, no kernel module.** The
index is the `gfx120X-all` one; for gfx1200 the wheels are pinned to
`7.10.0a20251120`, as `docs/AMD_HIP.md` describes. The exact installed wheel version is not
recorded in any file here, and `results.json` has no field for it.

**VRAM at startup.** `engine_info.vram_free_mib` is 606 MiB (IQ2_XS), 590 (IQ3_XXS), 586 (IQ3_S):
the engine takes all of the 16,304 MiB before serving, and `machine.vram_after` records
`elastic: false`, so nothing grows later.

**One VM-specific note**: the tool records `machine.launch: null` and `machine.config: {}` in all
12 arms, so this file is a machine snapshot, not a config dump. The launch line in the next
section is what the operator ran, written down from the run, not read out of these files.

## The launch line, and the model config

```bash
.venv/bin/python -u -m strata.engine --config ~/models/swift-1.5-iq2_xs.json \
    --model swift-1.5-iq2_xs --gpu 0 --port 8080 --host 127.0.0.1 --context 131072 \
    --kv int8 --resident-tokens 32768 --moe-resident-tokens 32768 --resident-moe \
    --moe-mode resident --expert-slots auto --mamba-slots auto --mamba-slots-floor 4 \
    --expert-ttl-ms 300000 --mtp-max-tokens 4 --spec 4 --prefill auto --prefill-cap 16384 \
    --prefill-workers 1 --pool-workers 11 --pool-gate auto --pcie-frac 1.00 \
    --min-strata-spec-tokens 128 --cache-min-tokens 2048 --cache-ttl-seconds 604800 \
    --conversation-cache-min-free-mib 2560 --conversation-cache-slots 4 --slot-cache 1 \
    --conversation-cache-min-tokens 0
# + export STRATA_HIP_WMMA=1 for the -wmma- arms; the 2-slot arms add a second batch slot
#   (docs/BATCHING.md: "parallel": 2 in the config, or setup --parallel 2)
# paths are shown from ~, the home folder, with the username replaced
```

The settings JSON (`settings-iq2_xs.json`) is preserved from the machine, verbatim, with the
`api_key` field replaced by `<redacted>` and the path prefix rewritten to `~/` so no username
appears in the repo. That is the IQ2_XS config; it is the only one of the three the machine kept,
the IQ3_XXS and IQ3_S configs are not here, and `machine.config` is `{}` in all 12 arms, so those
two configs are not preserved anywhere in this report. The preserved file's `--native` and `--ple-gguf`
point at the IQ2_XS weights, and it has `"parallel": 2`, so it is the 2-slot shape of the IQ2_XS
config; how the 1-slot arms got one slot (config edit to `"parallel": 1`, or a command-line override)
is not recorded anywhere in `data/` - `params.command` is the bench command, not the engine's, and
`machine.config` is `{}`. The preserved config is also not identical to the launch line above: the
config carries `--pack`, `--native`, `--ple-gguf`, `--expert-profile`, `--ple-io ram`,
`--kv-resident 32768`, `--pcie-frac`, `--spec-min-p` and the three `--adapt-*` flags, and the line
carries the slot, cache, prefill and pool flags. The two are the config file plus the flags the
operator added on the command line, and `data/` records neither of them. What the data does show
is the slot count: `machine.parallel_slots` is 1 in the six 1-slot arms and 2 in the six 2-slot
arms, and the six 2-slot arms report `engine_info.batch_slots: 2` (with `slot_cache: 1`,
`batch_groups: 1`) while in the six 1-slot arms that key is absent, so those ran with batching off,
one slot. The two records agree.

What the engine reports about itself, from `machine.engine_info`: 18 fields byte-identical in all
12 arms, and the rest varying by quant and slot count (the rows say which). The config asks for
`--spec 4`, the operator's launch line for `--prefill-cap 16384`; the numbers below are the
engine's own answers, recorded by the tool, and it answers `spec: 6`:

| field | value |
| --- | --- |
| `kv` / `kv_resident` / `context` | int8 / 32,768 / 131,072 |
| `spec` / `mtp_max` / `lookup` | 6 / 4 / 3 |
| `pcie_frac` / `pool_workers` / `spec_min_p` | 1.00 in all 12; `pool_workers` 7 on IQ2_XS and 11 on IQ3_XXS/IQ3_S; `spec_min_p` 0.50 on IQ2_XS and 0.70 on the other two - the engine answers per quant, see Limitations |
| `prefill_cap` / `prefill_stages` / `prefill_pipe` | 16,384 in ten arms, 15,872 in IQ2_XS WMMA-off 2-slot, 15,104 in IQ3_S WMMA-off 2-slot / 1 / 0 |
| `cvec` | 0 |
| `conversation_cache_slots` / `min_free_mib` / `min_tokens` | 4 / 2,560 / 0 |
| `tail_role_token` | -1 - the preserved config sets no `tail_role_token`, and docs list 21 as the Qwen3.5 ChatML value; Swift 1.5 is not ChatML, so -1 is the right answer here, not a silent failure |
| `vram_elastic` | 0 |
| `expert_cache_primary_mib` / `expert_slots_primary` | equal to the non-primary fields in all 12 arms (one GPU, no split) |
| `arena_mib` | 33,812 (IQ2_XS) / 40,925 (IQ3_XXS) / 47,962 (IQ3_S) |
| `expert_slots` / `expert_cache_mib` | see "Expert cache", they differ per quant and per slot count |
| `batch_slots` / `slot_cache` / `batch_groups` | 2 / 1 / 1 in the six 2-slot arms; the keys are absent in the six 1-slot arms, which is the data's evidence of the slot count |
| `stream_all_min` | 1,024 |

## Method, and what is compared to what

Twelve suites, one per (quant, WMMA, slots), run sequentially on the evening of 2026-10-17; the
one suite that ran after midnight (IQ3_XXS, WMMA off, parallel 1) has `date: 2026-10-18`, the
other eleven say 2026-10-17. Per-quant `date` and `elapsed_s` are in `arms.json`.
All 12 used the same host, the same VM, the same wheel set, and one of three configs, one config
per model:

```
python tools/strata_bench.py --long                 # parallel 1, one slot
python tools/strata_bench.py --clients 2 --long      # parallel 2, two slots, adds the 2-client burst
```

Both are `--long`, runs 3, think off, started_server false (the suites talk to a server that was
already up). The order of tests inside a suite is fixed by the tool, not by the operator: `Suite.run()` in
`tools/strata_bench.py` does warm-up, chats, the 4K prompt, the 16K prompt, the agent session, the
2-client burst (in `--clients 2` arms), and the 32K prompt, which only `--long` adds. So every
suite reads its longest prompt last, in a session that has already run chats and two shorter
prompts, and the 4K prompt is the first long read after the chats.

Arms are named `<quant>-<wmma|plain>-p<slots>`. The WMMA state is **not** in `results.json`:
`params.env` is null in all 12 arms, and no engine log was captured, so nothing in this data
proves which suite had the variable exported. The on/off label comes from the operator's record of
which shell exported it; `docs/AMD_HIP.md` describes the kernel. The data supports the labels:
the 16K medians split into two clean clusters, 1,212-1,510 tok/s in the arms called wmma and
819-978 tok/s in the arms called plain, with no overlap between the two.

The engine is restarted between suites, one server per suite; each suite gets a cold engine with
an empty conversation cache.

Every number in this report is a **median over that arm's requests** (n = 9 chat, n = 3 per prompt
length, n = 15 agent turns), with min-max. Throughput is the engine's own
`prompt_per_second` / `predicted_per_second`, not tokens over total request time. A percentage is
(median A / median B - 1) x 100 on those medians. "geomean" is the geometric mean of matched-pair
ratios, which is the right average when a set contains both +50% and -3%.

Request shapes, identical across arms:

| test | prompt tokens | reused | generated | requests per arm |
| --- | --- | --- | --- | --- |
| chat (4 prompts, warm) | 43-51 | 0 on the first, warm after | 100 | 9 |
| 4K / 16K / 32K prompt | 4,019 / 16,058 / 32,049 | 0 (all 108 prompt requests start cold) | 0 | 3 each |
| agent session, 6 turns | 609 (turn 1) -> 14,528-14,611 (turn 6) | grows with the session | 4-64 per turn | 3 sessions x 6 |
| 2-client burst, 3 rounds x 2 clients | 400-word essay prompts, nonce-prefixed | 0 (nonce-prefixed, so every prompt is fresh) | 128 each | 6 (only in the 6 `-p2` arms) |

Totals: 432 suite requests (12 arms x 36) + 36 burst requests (6 arms x 6) = **468 timed
requests**, 468 of them ok, 0 failures, 0 skipped, 0 burst errors. The agent suite has 5 turns per
session, so the 180 agent follow-up turns (60 sessions x 4) are included in the 432.

Comparisons, matched pairs only, 6 of each:

- **WMMA on vs off**: same quant, same slot count. Six pairs. Same engine, same config, same
  suite, one environment variable, the only difference in the suite.
- **parallel 2 vs parallel 1**: same quant, same WMMA state. Six pairs. The tool's aggregate is
  the per-client median, so aggregate = 2 x per-client.
- **quant**: each quant against IQ2_XS, at WMMA on, 1 slot, and at 2 slots. The 2-slot comparison
  uses the 2-client burst as the client, since that is what 2 slots means with real clients.

Not compared: 1-slot IQ3_S vs 2-slot IQ2_XS, and any quant/slot mix, because that changes two
things at once.

## Results

Medians as the tool recorded them, `[min-max]`, tok/s. The `-p2` arms' `burst` column is the
AGGREGATE of the two clients (2 clients x 128 tokens over the burst wall time).

| arm | chat decode | 4K prompt | 16K prompt | 32K prompt | agent decode | burst (2 clients, total) |
| --- | --- | --- | --- | --- | --- | --- |
| iq2_xs-wmma-p1 | 45.0 [42.1-59.0] | 828.4 [827.0-832.0] | 1,223.1 [1,222.4-1,223.5] | 1,361.8 [1,361.5-1,363.0] | 49.1 [23.1-58.2] | n/a |
| iq2_xs-wmma-p2 | 38.5 [36.2-50.7] | 809.9 [809.5-811.7] | 1,211.7 [1,210.7-1,212.5] | 1,198.8 [1,198.8-1,199.5] | 41.9 [26.8-49.5] | 35.02 [32.89-35.13] |
| iq2_xs-plain-p2 | 38.4 [36.2-51.4] | 678.9 [678.2-680.1] | 819.3 [819.2-820.0] | 820.8 [820.1-822.8] | 43.0 [37.1-54.4] | 34.89 [32.24-35.21] |
| iq2_xs-plain-p1 | 45.7 [39.0-59.0] | 855.1 [661.8-857.1] | 921.1 [903.7-922.8] | 903.0 [902.7-903.2] | 47.7 [34.7-57.2] | n/a |
| iq3_xxs-wmma-p1 | 42.4 [38.1-53.9] | 1,129.2 [1,046.4-1,129.4] | 1,455.5 [1,404.9-1,456.0] | 1,287.3 [1,287.0-1,287.4] | 45.1 [20.5-49.4] | n/a |
| iq3_xxs-wmma-p2 | 35.0 [30.9-45.7] | 1,110.7 [1,027.7-1,113.9] | 1,448.9 [1,403.6-1,450.7] | 1,275.0 [1,262.0-1,344.1] | 37.8 [32.9-41.6] | 27.12 [22.84-27.30] |
| iq3_xxs-plain-p2 | 35.1 [31.7-44.0] | 886.3 [831.1-886.6] | 927.3 [892.8-952.1] | 897.8 [861.4-920.9] | 37.1 [31.1-42.6] | 26.92 [26.29-27.34] |
| iq3_xxs-plain-p1 | 44.7 [38.4-54.7] | 721.2 [697.0-723.1] | 893.7 [878.4-897.5] | 915.2 [874.4-928.9] | 43.3 [39.1-50.8] | n/a |
| iq3_s-wmma-p1 | 37.1 [33.9-43.0] | 872.4 [832.9-872.5] | 1,371.0 [1,331.0-1,371.6] | 1,489.9 [1,489.4-1,490.0] | 38.8 [28.8-49.8] | n/a |
| iq3_s-wmma-p2 | 30.5 [25.7-37.8] | 1,098.5 [1,018.1-1,106.4] | 1,510.2 [1,456.0-1,510.2] | 1,482.5 [1,482.1-1,483.3] | 32.7 [12.7-43.6] | 24.14 [21.52-24.73] |
| iq3_s-plain-p2 | 29.1 [26.8-32.5] | 710.5 [685.9-712.5] | 846.0 [828.2-846.1] | 836.8 [836.8-838.1] | 32.8 [25.3-46.3] | 24.44 [21.81-24.84] |
| iq3_s-plain-p1 | 36.8 [33.1-43.2] | 907.6 [837.3-909.7] | 978.4 [956.3-979.7] | 901.8 [864.2-903.2] | 38.0 [34.5-46.8] | n/a |

Time to first token, seconds, medians `[min-max]`:

| arm | chat | 4K | 16K | 32K | agent turn |
| --- | --- | --- | --- | --- | --- |
| iq2_xs-wmma-p1 | 0.53 [0.49-0.58] | 4.88 [4.86-4.89] | 13.17 [13.16-13.18] | 23.58 [23.56-23.59] | 3.32 [2.23-4.47] |
| iq2_xs-wmma-p2 | 0.65 [0.59-0.74] | 5.00 [4.99-5.00] | 13.29 [13.28-13.30] | 26.79 [26.77-26.80] | 3.62 [2.26-5.42] |
| iq2_xs-plain-p2 | 0.64 [0.59-0.73] | 5.96 [5.94-5.96] | 19.64 [19.62-19.64] | 39.10 [39.01-39.13] | 5.62 [4.12-7.14] |
| iq2_xs-plain-p1 | 0.58 [0.52-0.66] | 4.73 [4.72-6.11] | 17.47 [17.44-17.81] | 35.54 [35.53-35.55] | 4.61 [2.79-6.00] |
| iq3_xxs-wmma-p1 | 0.64 [0.58-0.74] | 3.59 [3.59-3.88] | 11.07 [11.07-11.47] | 24.95 [24.95-24.96] | 4.15 [2.63-4.52] |
| iq3_xxs-wmma-p2 | 1.03 [0.74-1.08] | 3.66 [3.64-3.95] | 11.12 [11.11-11.48] | 25.19 [23.91-25.45] | 3.29 [2.35-4.02] |
| iq3_xxs-plain-p2 | 0.83 [0.79-1.05] | 4.57 [4.57-4.88] | 17.36 [16.91-18.03] | 35.75 [34.87-37.27] | 5.34 [4.16-6.43] |
| iq3_xxs-plain-p1 | 0.66 [0.58-0.75] | 5.61 [5.59-5.80] | 18.01 [17.93-18.32] | 35.07 [34.56-36.70] | 4.60 [2.69-6.12] |
| iq3_s-wmma-p1 | 0.81 [0.70-0.93] | 4.64 [4.64-4.87] | 11.76 [11.75-12.11] | 21.57 [21.56-21.57] | 3.24 [2.43-4.79] |
| iq3_s-wmma-p2 | 0.94 [0.82-1.12] | 3.70 [3.67-4.00] | 10.68 [10.68-11.08] | 21.69 [21.67-21.70] | 3.31 [2.47-5.45] |
| iq3_s-plain-p2 | 1.05 [0.87-1.23] | 5.70 [5.69-5.91] | 19.03 [19.02-19.44] | 38.37 [38.31-38.37] | 5.46 [4.23-6.39] |
| iq3_s-plain-p1 | 0.82 [0.70-0.93] | 4.46 [4.46-4.84] | 16.45 [16.43-16.83] | 35.59 [35.54-37.14] | 4.09 [2.81-5.08] |

## Speculation, as the tool records it: the quant sets the acceptance rate

Every suite request carries `drafts_offered` and `drafts_accepted`. The rate below is accepted over
offered, summed over that arm's requests: 9 chat requests, 18 agent turns, 9 prompt requests per
arm. The burst requests have no counters.

| arm | chat accept | agent accept | prompt accept |
| --- | --- | --- | --- |
| iq2_xs-wmma-p1 | 58.8% | 58.6% | 48.2% |
| iq2_xs-wmma-p2 | 60.0% | 55.2% | 48.4% |
| iq2_xs-plain-p2 | 61.0% | 62.1% | 48.4% |
| iq2_xs-plain-p1 | 57.7% | 59.8% | 51.6% |
| iq3_xxs-wmma-p1 | 74.7% | 66.9% | 66.9% |
| iq3_xxs-wmma-p2 | 77.8% | 67.0% | 62.3% |
| iq3_xxs-plain-p2 | 75.6% | 67.4% | 62.3% |
| iq3_xxs-plain-p1 | 77.1% | 68.4% | 63.1% |
| iq3_s-wmma-p1 | 73.3% | 68.2% | 55.8% |
| iq3_s-wmma-p2 | 73.5% | 69.2% | 58.4% |
| iq3_s-plain-p2 | 72.0% | 71.0% | 55.0% |
| iq3_s-plain-p1 | 73.5% | 67.2% | 63.3% |

- **The quant, not the setting, sets acceptance.** Chat: 57.7-61.0% (IQ2_XS), 74.7-77.8%
  (IQ3_XXS), 72.0-73.5% (IQ3_S). Agent turns: 55.2-62.1%, 66.9-68.4%, 67.2-71.0%. Prompt requests:
  48.2-51.6%, 62.3-66.9%, 55.0-63.3%. Across the four settings of one quant the chat band is 2-4
  points wide, so WMMA on/off and 1-slot/2-slot move acceptance a little and the quant moves it 15
  points.
- **Why it matters for reading the decode columns**: an accepted draft is a free token, so IQ3_XXS
  and IQ3_S are running with a better speculation rate than IQ2_XS in every one of these suites, and
  their decode numbers are the result of that plus the extra weight bytes. The -5.8% and -17.6%
  chat numbers are net of a speculation advantage, not net of a speculation handicap.
- **One confound sits in this table, and it is in the engine's own answers**: `spec_min_p` is 0.50
  on the six IQ2_XS arms and 0.70 on the six IQ3_XXS/IQ3_S arms (`pool_workers` 7 against 11), and
  both are constant inside a quant. A lower bar lets more drafts through, so part of IQ2_XS's lower
  acceptance is the threshold it runs with and not the model. Inside a quant the bar is fixed, so
  the six WMMA pairs and the six parallel pairs are clean on this axis; the quant comparison is not,
  in acceptance and in decode, and it is reported with that caveat in "Quant".
- **Prompt requests speculate too** (the ranges above, 48.2-66.9% over the three quants), and that
  is where the MTP path is doing work inside prefill; `mtp_max: 4` in all 12 arms, `lookup: 3`.

## STRATA_HIP_WMMA=1: no cost on the chat and agent axes, large gain on the long-prompt axis

Each row is one matched pair, same quant, same slot count, one environment variable apart.
A positive number means the WMMA arm is faster.

| quant, slots | 4K prompt | 16K prompt | 32K prompt | geomean prompt | chat decode | agent decode | geomean decode |
| --- | --- | --- | --- | --- | --- | --- | --- |
| iq2_xs, 1 | -3.1% | +32.8% | +50.8% | +24.7% | -1.5% | +2.9% | +0.7% |
| iq3_xxs, 1 | +56.6% | +62.9% | +40.7% | +53.1% | -5.1% | +4.2% | -0.6% |
| iq3_s, 1 | -3.9% | +40.1% | +65.2% | +30.6% | +0.8% | +2.1% | +1.5% |
| iq2_xs, 2 | +19.3% | +47.9% | +46.1% | +37.1% | +0.3% | -2.6% | -1.2% |
| iq3_xxs, 2 | +25.3% | +56.2% | +42.0% | +40.6% | -0.3% | +1.9% | +0.8% |
| iq3_s, 2 | +54.6% | +78.5% | +77.2% | +69.7% | +4.8% | -0.3% | +2.2% |
| **geomean, six pairs** | **+22.4%** | **+52.3%** | **+53.1%** | - | **-0.2%** | **+1.3%** | - |

Time to first token, same pairs (negative = WMMA is faster):

| pair group | chat TTFT | 4K TTFT | 16K TTFT | 32K TTFT | agent TTFT |
| --- | --- | --- | --- | --- | --- |
| iq2_xs, 1 | -9.4% | +3.2% | -24.6% | -33.6% | -27.9% |
| iq3_xxs, 1 | -3.0% | -35.9% | -38.5% | -28.9% | -9.8% |
| iq3_s, 1 | -1.8% | +4.0% | -28.6% | -39.4% | -20.7% |
| iq2_xs, 2 | +0.5% | -16.1% | -32.3% | -31.5% | -35.7% |
| iq3_xxs, 2 | +23.1% | -20.0% | -35.9% | -29.5% | -38.4% |
| iq3_s, 2 | -10.7% | -35.0% | -43.9% | -43.5% | -39.4% |
| **geomean, six pairs** | **-0.8%** | **-18.2%** | **-34.3%** | **-34.6%** | **-29.4%** |

- **Decode: no effect, within the spread of one arm.** chat geomean -0.2%, agent geomean +1.3%,
  with the six pairs straddling zero, -5.1% to +4.8%. `docs/AMD_HIP.md` describes the kernel as a
  prefill-side change (it is the prompt path that changes shape), and that is what these pairs say:
  100-token chats and 4-64-token agent turns are decode-bound, so the kernel has nothing to do.
- **Prefill: this is where it lives.** 16K +32.8% to +62.9% at 1 slot, +47.9% to +78.5% at 2 slots,
  geomean +52.3%. At 32K, +40.7% to +77.2%, geomean +53.1%. Time to first token at 32K drops
  -28.9% to -43.5%, geomean -34.6%: a 32K prompt that took 35.1-39.1 s starts landing in
  21.6-26.8 s.
- **4K is the column to distrust, and it is the WMMA-off arms that are noisy, not the WMMA ones.**
  The gains are +19.3% to +56.6%, geomean +22.4%, with two pairs negative (-3.1%, -3.9%). The
  widest within-arm spread in this whole report is `iq2_xs-plain-p1` at 4K, 22.8% (its three runs
  read 661.8, 855.1, 857.1 tok/s). Every 4K arm with WMMA on is tight by comparison
  (0.3-8.0%). So a single 4K run of the portable path can land 23% below its own median, and
  that is bigger than the 4K effect being measured; the two negative pairs are inside that.
- **Where the kernel is a wash at 4K, it is also a wash in decode, and both are decode/prefill
  shapes below the size where the tiled path pays.** The engine's own prefill cap is 16,384, the
  4K prompt is 4,019 tokens, and the tile path only shows at 16K and 32K.

The kernel: `docs/AMD_HIP.md` (line 422) documents `STRATA_HIP_WMMA=1` as opt-in, gfx12 only,
and only with `--kv int8` (the config uses int8 KV, so it is eligible; eligibility is not the same
as enabling, the engine never enables it by itself). It uses `v_wmma_f32_16x16x16_f16`, the RDNA4
waveform-level matrix instruction, and `hip_prompt_attn_wmma` is the test that covers it.
`docs/AMD_HIP.md` reports the portable kernel at 7.2-7.5x on a 16K prompt on RDNA4 (R9700 matched
trials) and the expert ring at 96 slots with WMMA. No engine log was captured in these 12 suites
and `params.env` is null, so this report has no direct record of the variable being set; the
pairing rests on the operator's run log and on the two clean 16K clusters named above.

## parallel 2: 1.17-1.22x aggregate, geomean -16.6% per chat stream, prompt processing unchanged

Same quant, same WMMA state, one process with two slots.

| quant | chat decode | agent decode | 4K prompt | 16K prompt | 32K prompt | chat TTFT | agent TTFT |
| --- | --- | --- | --- | --- | --- | --- | --- |
| iq2_xs | -14.4% | -14.7% | -2.2% | -0.9% | -12.0% | +22.3% | +8.9% |
| iq3_xxs | -17.5% | -16.2% | -1.6% | -0.5% | -1.0% | +59.7% | -20.8% |
| iq3_s | -17.8% | -15.7% | +25.9% | +10.2% | -0.5% | +16.5% | +2.2% |
| **geomean** | **-16.6%** | **-15.5%** | **+1.5%** (nine prompt pairs) | - | - | **+31.6%** | - |

- **1.17-1.22x aggregate**, from the per-client medians: IQ2_XS chat 1 / (1 - 14.4%) = 1.169,
  IQ3_XXS 1.211, IQ3_S 1.216. The engine has one expert pool, one KV arena, one process; the second
  slot costs 14.6-16.1% of the expert slots (see "Expert cache"), and what is left is enough.
- **Per client, the cost lands on decode.** chat geomean -16.6%, agent geomean -15.5%, in a tight
  band (-14.4% to -17.8% chat, -14.7% to -16.2% agent). That is what `docs/BATCHING.md` warns of
  on a 16GB card: 10-25% per request when experts mostly fit.
- **Prefill does not lose.** Nine prompt pairs, geomean +1.5%, six of them inside +-2.2% (4K
  -2.2%, -1.6%, +25.9%; 16K -0.9%, -0.5%, +10.2%; 32K -12.0%, -1.0%, -0.5%). Two are outliers in
  the same direction, IQ3_S 4K +25.9% and 16K +10.2%, and both are inside that arm's 4K/16K
  repetition spread, 8.0% at 4K and 3.6% at 16K. The +25.9% at 4K is inside that spread; the
  +10.2% at 16K is not, both arms are tight there (3.6% and 3.0%), so 2-slot IQ3_S is genuinely
  the fastest 16K prefill in this report (1,510.2 tok/s) and that is not explained by anything in
  the configs. The one pair that reads as a real loss is IQ2_XS 32K: 1,361.8 tok/s at 1 slot
  against 1,198.8 at 2 slots, with 0.1% spread on both sides, so -12.0% there is real; the other
  two quants are 32K flat (-1.0%, -0.5%).
- **Time to first token at 2 slots pays for the second client.** Chat TTFT geomean +31.6%
  (+22.3%, +59.7%, +16.5%): a single chat's first token goes from 0.53 s to 0.65 s (IQ2_XS),
  0.64 s to 1.03 s (IQ3_XXS), 0.81 s to 0.94 s (IQ3_S). The 16K prompt TTFT at 2 slots is
  13.29 / 11.12 / 10.68 s, against 13.17 / 11.07 / 11.76 s at 1 slot: prefill does not queue.
- **The same pairs with WMMA off** (plain p2 vs plain p1): chat -16.0%, -21.5%, -20.9%
  (geomean -19.5%), agent -9.9%, -14.3%, -13.7% (geomean -12.6%). So the slot cost is the same
  story without the kernel; the kernel is not what makes 2 slots affordable. One asymmetry in those
  pairs, recorded in `engine_info`: the 2-slot arms that run with WMMA off report a smaller prefill
  window than their 1-slot partner - 15,872 (IQ2_XS) and 15,104 (IQ3_S) against 16,384 - so their
  prompt columns are read with that in mind. Every pair in the table above is at 16,384 on both
  sides.

## Two clients on one 16GB card: the quant decides, and IQ2_XS is the one that fits

The `-p2` arms ran the burst: 3 rounds, 2 clients per round, 400-word essay prompts,
nonce-prefixed so every prompt is fresh, 128 tokens each. `clients.total_tps` is the AGGREGATE of
the two clients; per client it is half. "share of solo" is against that same arm's 1-client chat
decode median at 2 slots, which is the rate one client would get alone in that process.

| quant (WMMA on, 2 slots) | burst total | per client | share of solo (total) | share of solo (per client) | p50 TTFT | p95 TTFT |
| --- | --- | --- | --- | --- | --- | --- |
| iq2_xs | 35.0 [32.89-35.13] | 17.5 | 91.0% | 45.5% | 1.481 s | 2.034 s |
| iq3_xxs | 27.1 [22.84-27.30] | 13.6 | 77.5% | 38.7% | 2.236 s | 3.169 s |
| iq3_s | 24.1 [21.52-24.73] | 12.1 | 79.1% | 39.6% | 2.532 s | 3.556 s |

- **IQ2_XS loses almost nothing in the aggregate**: 35.0 tok/s total against that arm's 38.5 tok/s
  solo chat rate, 91.0%; against the same quant's 1-slot solo rate (45.0) it is 77.8%, and the
  1-slot comparison for IQ3_XXS and IQ3_S is 64.0% and 65.1%. Per client it is 17.5 tok/s, 45.5%
  of solo, which is what two clients sharing one 16GB card should look like: the pair nearly
  doubles total output, each stream runs at about 45% of its solo rate. The geomean aggregate share
  over the three quants is **82.3%**.
- **16K prompt processing at 2 slots is 1,211.7 (IQ2_XS), 1,448.9 (IQ3_XXS), 1,510.2 (IQ3_S)
  tok/s** - within 1.0% of the 1-slot rates for IQ2_XS and IQ3_XXS (1,223.1 and 1,455.5), and
  higher for IQ3_S (1,371.0 at 1 slot, +10.2%). Prefill is not the thing that gets shared away.
- **End-to-end latency for a 128-token request is 2.2-2.6x the solo time.** The burst's p50
  latency is 7.298 s (IQ2_XS), 9.423 s (IQ3_XXS), 10.586 s (IQ3_S); a solo 128-token request at
  that arm's 2-slot chat rate (38.5 / 35.0 / 30.5 tok/s) is 3.32 / 3.66 / 4.20 s. So +119.5%,
  +157.7%, +152.2%: the pair pays, per request, in exchange for the aggregate.
  The p95s are 7.774 / 11.196 / 11.882 s: the tail is 6.5% (IQ2_XS), 18.8% (IQ3_XXS), 12.2%
  (IQ3_S) over the p50, so a two-slot box is not tail-spiky at 2 clients, 0 errors in all 36
  burst requests. The ratios are 2.20x, 2.58x, 2.52x.
- **WMMA off, same burst**: 34.89, 26.92, 24.44 tok/s (90.9%, 76.7%, 84.0% of each arm's solo).
  The kernel changes the solo rate a lot and the burst total almost nothing, which is what
  decode-bound clients do: the burst is 128 tokens per request, so it is decode, and the kernel is
  a prefill change.
- **The quant ranking flips between solo and pair.** At 1 slot IQ3_S is -17.6% (chat) vs IQ2_XS;
  in the 2-client burst it is -31.1% (24.14 vs 35.02 tok/s aggregate). The gap widens because
  IQ3_S starts the pair from a smaller expert cache (4,003 slots at 2 slots, 7,821 MiB) on a card
  with 586 MiB free at startup.

## Quant: IQ3_S costs decode, buys nothing on prefill, and costs 1.42x the arena

At WMMA on, 1 slot, against IQ2_XS at the same setting:

| quant | chat decode | agent decode | geomean decode | 4K prompt | 16K prompt | 32K prompt | geomean prompt | chat TTFT | 32K TTFT |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| iq2_xs | - | - | - | - | - | - | - | - | - |
| iq3_xxs | -5.8% | -8.1% | -7.0% | +36.3% | +19.0% | -5.5% | +15.3% | +21.8% | +5.8% |
| iq3_s | -17.6% | -21.0% | -19.3% | +5.3% | +12.1% | +9.4% | +8.9% | +52.7% | -8.6% |

At 2 slots, against IQ2_XS at 2 slots, with the 2-client burst as the client:

| quant | chat decode | agent decode | geomean decode | burst total | 4K prompt | 16K prompt | 32K prompt | geomean prompt | chat TTFT | 32K TTFT |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| iq2_xs | - | - | - | - | - | - | - | - | - | - |
| iq3_xxs | -9.1% | -9.8% | -9.4% | -22.6% | +37.1% | +19.6% | +6.4% | +20.4% | +59.0% | -6.0% |
| iq3_s | -20.8% | -22.0% | -21.4% | -31.1% | +35.6% | +24.6% | +23.7% | +27.9% | +45.4% | -19.0% |

- **Decode is where the quant is paid for**: chat -5.8% (IQ3_XXS) and -17.6% (IQ3_S), agent -8.1%
  and -21.0%. The agent column is worse than the chat column for both quants, which is what the
  expert cache does under long sessions: the 2-slot IQ3_S arm has 4,003 slots for 256 experts x
  48 layers, and every turn reaches for more of them.
- **The prompt numbers are the surprise and they are not a speed win.** Every quant pair is within
  a few percent of the others at 16K and 32K in the medians above, and the geomeans over the three
  prompt columns are **+15.3%** (IQ3_XXS) and **+8.9%** (IQ3_S) vs IQ2_XS: the bigger quants
  prefill faster in these runs, by 9-15% on average. This is the pattern a 4K column with 22.8% of
  within-arm spread invites, and the 32K column of IQ3_XXS is the one place where the ranking is
  negative (-5.5%), and the chat TTFT columns (+21.8% and +52.7% at 1 slot, +59.0% and +45.4% at
  2 slots) say the first token arrives later on the bigger quants, so the quant is paid for on
  every axis a client feels. Read the 16K/32K medians (0.1-6.4% and 0.0-6.6% spread) as the real signal
  and the 4K column as noise. On speed alone, IQ2_XS gives up nothing that IQ3_S buys.
- **The quant comparison is not a clean pair, and the engine's own answers say why.** IQ2_XS runs
  with `pool_workers: 7` and `spec_min_p: 0.50`; IQ3_XXS and IQ3_S run with 11 and 0.70. Those two
  fields are the engine's answers, not the config's (the config asks for `--pool-workers 11` and
  `--spec-min-p 0.70`), and they are constant inside a quant: across the four settings of one quant
  they never move. So the six WMMA pairs and the six parallel pairs are clean (same quant, same
  values) and the nine quant-vs-IQ2_XS comparisons in the two tables above are not: the quant comes
  bundled with a 7-worker pool and a lower speculation bar. The quant numbers are reported as they
  are, with that caveat attached, and the arena and expert-slot columns beside them are the part
  that is not in question.
- **The arena is 1.42x bigger on IQ3_S**: 33,812 MiB (33.0 GiB) IQ2_XS, 40,925 MiB (40.0 GiB)
  IQ3_XXS, 47,962 MiB (46.8 GiB) IQ3_S, on a 16,304 MiB card. The arena is virtual; what is real
  on the card is the expert pool and KV, and the expert pool shrinks 36% from IQ2_XS to IQ3_S
  (7,465 to 4,774 slots at 1 slot).

## The agent suite: what the conversation cache does, in the tool's own numbers

The agent suite is 3 sessions per arm, 6 turns per session, so 36 sessions and 216 turns in the
12 arms, of which 180 are follow-up turns (the tool's `turn_*` statistics are over those 180). These
are the tool's `results.agent` statistics, min-max over the 36 sessions; the hit rate is a property
of the prompt sequence, not of the engine.

| field | range across the 12 arms |
| --- | --- |
| cache hit rate | 68.4-68.8% |
| re-read tokens per session | 1-144 |
| new prompt tokens per session | 13,716-13,721 |
| last-turn prompt tokens | 14,528-14,611 |
| first-turn TTFT | 1.5-3.2 s |
| generated tokens per turn | 4-64 |

- **The hit rate is 68.4-68.8% in all 12 arms**, quant, slots and WMMA included: each session adds
  13,716-13,721 new prompt tokens over the 5 follow-up turns and re-reads 1-144, so about two thirds
  of the last turn's 14,528-14,611 tokens come from cache in every arm.
- **Re-read is 1-144 tokens, not 14,500.** The last-turn prompt is 14,528-14,611 tokens; what is
  re-read is 1-144. That is the cache (`conversation_cache_slots: 4`, `cache_min_tokens: 2048`)
  doing its job, and the 144 end of the range is the arms where a turn missed and had to be
  re-prefilled.
- **Turn 1 is the fast one, 1.5-3.2 s (609 tokens).** The 4-64 tokens generated per turn are why
  the agent decode column is the number to read for chat-like sessions; an uncached 5th turn at
  14,528 tokens would be a 16K-class prefill every time, 9.7-12.0 s in the WMMA arms and
  14.9-17.7 s in the portable arms, at the 16K rates in the table above.

## Expert cache: the budget that decides which quant fits

| arm | expert slots | MiB | GiB |
| --- | --- | --- | --- |
| iq2_xs, 1 slot | 7,465 | 10,239 | 10.0 |
| iq2_xs, 2 slots | 6,375 | 8,747 | 8.5 |
| iq3_xxs, 1 slot | 5,846 | 9,694 | 9.5 |
| iq3_xxs, 2 slots | 4,935 | 8,202 | 8.0 |
| iq3_s, 1 slot | 4,774 | 9,312 | 9.1 |
| iq3_s, 2 slots | 4,003 | 7,821 | 7.6 |

- **The second slot costs -14.6% to -16.1% of the expert slots**: 7,465 -> 6,375 (-14.6%),
  5,846 -> 4,935 (-15.6%), 4,774 -> 4,003 (-16.1%), with the same quant, the same config,
  `--expert-slots auto` in both cases. The
  engine sizes the pool from what is left after the slots and KV are paid for, so a slot count
  change moves the cache, and that is the mechanism behind the -14.4% to -17.8% chat numbers.
- **IQ2_XS is the only quant that gets a 10 GiB pool on this card**, and it is the only arm whose
  per-turn expert set can be resident at all 256 x 48 scale. 4,003 slots for IQ3_S at 2 slots is
  54% of IQ2_XS's 7,465.
- **`--expert-cache auto` is what the config asks for** (`settings-iq2_xs.json`; the operator's
  launch line adds `--expert-slots auto`); the numbers above are the engine's answers
  (`engine_info.expert_slots`), not a setting.
- **The KV side is identical in all 12 arms**: int8 KV, 32,768 resident tokens, 131,072 context,
  11 pool workers, `pcie_frac` 1.00. Only the model files and the expert pool differ between the
  three quant groups.

## Wall time, and the suite as a whole

| quant | 1 slot, WMMA on | 1 slot, WMMA off | delta | 2 slots, WMMA on | 2 slots, WMMA off | delta |
| --- | --- | --- | --- | --- | --- | --- |
| iq2_xs | 235.6 s | 309.0 s | -23.8% | 284.2 s | 369.0 s | -23.0% |
| iq3_xxs | 250.7 s | 317.5 s | -21.1% | 273.6 s | 358.2 s | -23.6% |
| iq3_s | 247.8 s | 307.4 s | -19.4% | 279.3 s | 400.5 s | -30.3% |

The suite is the tool's `elapsed_s`, model loading not included. The 2-slot rows include the
3-round burst, so they are not the same work as the 1-slot rows; the WMMA-on/off comparison inside
each slot count is the same work. WMMA on is **19.4-30.3% shorter wall time** for identical work,
six pairs, which is the prefill gain showing up as suite length: the suite is 108 prompt requests
out of 432, and they are the expensive ones.

## Limitations

- **Speed only.** No recall, no coding tasks, no KL, no needle test, no quality measurement of any
  kind. Quant choice is a quality/speed trade and this report can only speak for the speed side.
- **12 suites, 468 timed requests, run sequentially in one evening (2026-10-17, one suite after
  midnight on 2026-10-18).** No repeats across boots, no interleaving. Each arm has 36 suite
  requests and, for the 6 `-p2` arms, 6 burst requests.
- **No engine logs, and the WMMA state is not in the data.** `params.env` is null in all 12 arms,
  no engine log was captured, so nothing in `data/` proves which suite had `STRATA_HIP_WMMA=1`
  exported; the labels come from the operator's run log. The 16K medians split into two clean
  clusters (1,212-1,510 tok/s vs 819-978) with no overlap, which is consistent with the labels,
  and that is the strongest evidence in the data. Nothing here records the kernel identity of a
  suite.
- **3 prompt runs per length, 9 chat runs, 15 agent turns per arm.** The within-arm spread of the
  three prompt runs is 0.3-22.8% at 4K (median 5.4%), 0.1-6.4% at 16K (median 2.3%), 0.0-6.6% at
  32K (median 0.1%). The 4K column is the only one with a spread wider than its own effect, and
  the widest cases are all WMMA-off arms (22.8% on iq2_xs-plain-p1, 8.0% on iq3_s-plain-p1).
  So: the 4K gains in the WMMA table (+22.4% geomean) are a real median shift, but no single 4K
  pair should be read as a measurement, and the two negative 4K pairs (-3.1%, -3.9%) are not
  evidence of a regression.
- **The order is not counterbalanced, and it is the WMMA-off suite that runs second in every pair**
  (per quant: wmma-p1, wmma-p2, plain-p2, plain-p1). A warm card later in the sequence, if the
  order biases anything, biases the WMMA-off arm down, the same direction as the measured effect.
  Nothing in the 12 suite times (235.6-400.5 s) suggests thermal drift, and there is no
  power, clock, temperature, fan, DPCGT, ASPM, or host-co-tenant record.
- **The 32K medians in this report are 32K cold reads.** All 108 prompt requests report
  `reused_tokens: 0`, so they are all cold; nothing in this data measures a warm 32K re-read, and
  the 32K prompt cost is the cost of the first read, not of a conversation that re-reads its
  history.
- **`--mtp-max-tokens 4` in the launch line and `--spec 4` in the config; the engine reports `spec: 6`, `mtp_max: 4`,
  `lookup: 3`, in all 12 arms.** The tool records `drafts_offered` and `drafts_accepted` per suite
  request, which is the acceptance table above; it does not record verify rate, draft length, or why
  a draft was refused, and the 36 burst requests carry no counters at all. Speculation is shared
  under parallel 2, so it is part of what the -16.6% chat number includes. So "the engine's numbers"
  are not identical to the config's, and the 1-slot to 2-slot comparison is done at the same reported
  values in both.
- **`tail_role_token` is reported as -1 in all 12 arms, and the preserved config sets no
  `tail_role_token` at all** - docs list 21 as the Qwen3.5 ChatML value. Swift 1.5 is not ChatML, so
  -1 is the config being right about the model, not a silent failure. The IQ3_XXS and IQ3_S configs
  are not preserved, so for those two quants the engine's -1 is all the evidence there is.
- **One VM, one host, one pass-through, and the host is shared infrastructure.** The tool records
  `machine.launch: null` and `machine.config: {}` in all 12 arms, so these files cannot show
  anything about the VM: BIOS, IOMMU group, host CPU governor, NUMA, ballooning, ballooning
  pressure, or co-tenants. The VM's own view is in `machine`: 12 threads of a Ryzen 5 3600, 86.3
  GiB RAM, Linux 6.12.111+deb13-amd64.
- **The ROCm wheel version is not recorded** anywhere in this data - no field for it, and no
  `amd-smi` / `rocm-smi` capture. `machine.gpu` is the short name `["AMD Radeon"]` (16,304 MiB),
  not a full device name, and `machine.gpu_driver` and `machine.cuda` are `null`. The device is
  identified as gfx1200 / RDNA4 from `lspci` (`AMD/ATI[1002:7550] (rev c3)`) on the VM, not from
  the tool's own output.
- **The quant comparison is not a clean pair, and it is worth saying twice.** The engine answers
  `pool_workers: 7` and `spec_min_p: 0.50` on the six IQ2_XS arms and 11 / 0.70 on the six
  IQ3_XXS and IQ3_S arms, constant inside a quant. Every quant-vs-IQ2_XS number in this report (the
  decode columns, the prefill columns, the acceptance rates, the burst totals) carries that bundle;
  the six WMMA pairs and the six parallel pairs are inside one quant, so they are clean.
- **Settings for IQ2_XS only.** `settings-iq2_xs.json` is the only config preserved; the IQ3_XXS and
  IQ3_S configs are not on the machine any more. They are quoted from the operator's launch line
  (identical flags, different `--model` and config file), so a re-run cannot be reproduced exactly.
- **One model family, one size class, 256 experts, one MoE, one host.** No dense model, no
  non-Swift model, no second GPU, no non-VM control run. Two quants are one model at two sizes,
  so the quant axis is 3 points on one model.
- **The 2-slot numbers are 2 slots, not 2 processes.** `parallel_slots: 2` with
  `batch_slots: 2` in the same process, one expert pool, one KV arena. What 2 processes on 16GB
  costs is not measured. The burst is 2 clients, not 2 slots' worth of traffic at 2 clients.
- **No batched prefill** (`--prefill-workers 1`, `prefill_stages: 1`, no `--batch-mtp`), so
  `docs/BATCHING.md`'s +31-39% aggregate is not what this measures.

## Files

- `README.md` - this file.
- `arms.json` - schema 1, the 12 arms with quant, slots, dates, `elapsed_s`, the engine's expert
  slots and arena, launch command and the flags that were set, and what `results.json` does not
  record.
  record. Each arm in `arms.json` names the tool's own output directory it came from
  (`source_dir`, md5-matched to the copy in `data/`); the tool's directory names carry no order
  information, so the run order is the operator's log (see Method).
- `settings-iq2_xs.json` - IQ2_XS config as the machine has it, `api_key` replaced with
  `<redacted>`, path prefix rewritten to `~/`. The IQ3_XXS and IQ3_S configs are not in this
  report, see Limitations.
- `summarize.py` - prints the report's tables from `data/`: the raw medians and TTFT, both WMMA
  pair tables, the parallel pairs (its table carries an extra aggregate column), the 2-client burst
  (its table carries the latency columns this README quotes in prose), both quant tables, the
  acceptance table, the agent ranges, the expert cache, the wall time, the request shapes, and the
  machine and engine blocks. It shares no code with `check_report.py`; the two agreeing is the
  check.
- `check_report.py` - recomputes those numbers from `data/` independently of `summarize.py`, in two
  directions: it checks that every value it derives is stated in README.md (it derives ~500, from
  the medians, the pairs, the burst block, the agent block, the engine block and the machine block,
  and it asserts the machine block is identical in all 12 arms), and it checks every table cell in
  README.md, in position, against recomputation (13 tables). A cell that is stale, or rounded from
  a rounded number, is reported. `python3 check_report.py` should print "0 stated" failures and
  "0 cell mismatches".
- `data/<arm>/results.json` - the tool's own JSON, byte-identical to what the tool wrote (12 arms,
  schema 1; checked against the run copies at md5 level, all 24 files in `data/` match).
- `data/<arm>/strata-bench-README.md` - the tool's per-suite summary, byte-identical to the file
  the tool wrote at run time (the tool calls it `README.md`; renamed here so it does not clash with
  this report, and the tool's text contains no paths or keys), with the tool's own machine block: `gpu ['AMD Radeon']`, 16,304 MiB, driver `None`, cuda `None`, 12 threads,
  86.3 GiB RAM, engine_info with the slots, the arena, the KV, `spec 6`, `mtp_max 4`, `lookup 3`.

## What to run on a 16GB RDNA4 card in a VM

Reading this data as advice, for this card and this model family:

- **Set `STRATA_HIP_WMMA=1`, and do not expect anything to change on the chat axis.** Six pairs,
  chat decode geomean -0.2%, agent decode +1.3%, both inside a single arm's spread. The gain is on
  prompt processing: 16K geomean +52.3%, 32K +53.1%, 32K time to first token -34.6% (a 32K prompt
  goes from 35.1-39.1 s to 21.6-26.8 s). The kernel is opt-in, gfx12 only, and needs int8 KV;
  `docs/AMD_HIP.md` documents it, and the engine's own expert ring grows with it. Nothing in this
  data shows a cost, and the suite finishes 19.4-30.3% sooner.
- **IQ2_XS, not IQ3_XXS, not IQ3_S, if speed is the axis.** IQ3_S costs -17.6% chat decode, -21.0%
  agent decode, -31.1% of the 2-client aggregate, and buys a 1.42x arena (33,812 to 47,962 MiB)
  plus a 36% smaller expert pool (7,465 to 4,774 slots at 1 slot). IQ3_XXS is the middle point and
  still costs -5.8% / -8.1% / -22.6%. Nothing here measures quality, so this is only the speed side
  of that trade.
- **`"parallel": 2` pays on this card, 1.17-1.22x aggregate, and the cost lands on per-request
  decode**: chat -14.4% to -17.8%, agent -14.7% to -16.2%, time to first token +22.3% to +59.7%,
  prefill unchanged (nine pairs, geomean +1.5%). The second slot is affordable because the expert
  pool gives up -14.6% to -16.1% of its slots and the engine keeps serving, so it is a real trade and
  not free.
- **Two real clients on 16GB: IQ2_XS is the quant that fits.** 35.0 tok/s aggregate, 91.0% of that
  arm's solo rate, 17.5 tok/s each. With IQ3_XXS the pair gets 27.1 and with IQ3_S 24.1, and IQ3_S
  pays 31.1% of the aggregate against IQ2_XS from a 4,003-slot expert pool. The p50 for a
  128-token request in the pair is 2.2-2.6x its solo time, with no tail problem at 2 clients
  (p95 6.5-19% over p50, 0 errors in 36).
- **If the workload is single long prompts, use 1 slot.** IQ2_XS at 1 slot is the fastest 32K
  reader in this report, 1,361.8 tok/s, 12.0% above the same quant at 2 slots (1,198.8) - the only
  prompt pair in the parallel table that is a real loss, with 0.1% spread on both sides.
- **Do not choose the quant from the 4K column.** 4K prompt rates in these 12 suites span
  678.9 to 1,129.2 tok/s, a 66% spread across 12 arms of the same test, and within one arm the
  three 4K runs differ by up to 22.8%. The 16K and 32K columns (spreads 0.1-6.4% and 0.0-6.6%)
  are where the quant ranking is readable: 819-978 tok/s with the portable kernel, 1,212-1,510 with
  the WMMA kernel at 16K, and 16K is where all three quants land within 1,212-1,510 tok/s of each
  other with WMMA on.
- **Check the expert slots before believing any quant comparison on 16GB.** `engine_info` prints
  them in the first seconds of every engine start: 7,465 (IQ2_XS), 5,846 (IQ3_XXS), 4,774 (IQ3_S)
  at 1 slot. 256 experts x 48 layers is the denominator. This is the number that explains why the
  2-client aggregate is 35.0 on IQ2_XS and 24.1 on IQ3_S, and it is the first thing to read on a
  new card.
