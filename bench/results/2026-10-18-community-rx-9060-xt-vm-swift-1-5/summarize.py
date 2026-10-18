#!/usr/bin/env python3
"""summarize.py - print the README's tables from data/, so every number in README.md is reproducible.

Usage: python3 summarize.py [data-dir]

Reads the 12 `data/<quant>-<wmma|plain>-p<slots>/results.json` files (one `tools/strata_bench.py
--long` suite each, 3 repetitions per test, the `-p2` arms also ran the 2-client burst) and prints
the medians, the matched-pair percentages, the geometric means, the burst shares, the cache sizes,
the spreads and the counts, as markdown. Medians, min, max and n are the tool's own statistics over
that arm's requests; throughput is the engine's own `prompt_per_second` / `predicted_per_second`,
never tokens over total request time. A percentage is (median A / median B - 1) x 100 on those
medians; "geomean" is the geometric mean over matched pairs, which is how a set containing both
+50% and -3% should be averaged. `clients.total_tps` is the AGGREGATE of the two clients, so per
client it is half. Suite wall time is the tool's `elapsed_s`, model loading not included.

`check_report.py` does the same recomputation and checks README.md states it; the two scripts share
no code.
"""
import json
import math
import statistics
import sys
from pathlib import Path

QUANTS = ["iq2_xs", "iq3_xxs", "iq3_s"]
PROMPTS = ("4K", "16K", "32K")
ORDER = [("wmma", 1), ("wmma", 2), ("plain", 2), ("plain", 1)]


def load(data_dir):
    d = {}
    for q in QUANTS:
        for w, s in ORDER:
            arm = f"{q}-{w}-p{s}"
            d[arm] = json.loads((Path(data_dir) / arm / "results.json").read_text())
    return d


def cell(b, k, nd=1):
    c = b[k]
    f = (lambda v: f"{v:,.{nd}f}") if nd else (lambda v: f"{v:.2f}")
    return f"{f(c['median'])} [{f(c['min'])}-{f(c['max'])}]"


def med(res, kind, key):
    if kind in ("chat", "agent", "clients"):
        b = res[kind]
        if not b:
            return None
        return b[key]["median"]
    b = res["prompts"][key]
    return b["prompt_tps"]["median"] if kind == "p" else b["ttft_s"]["median"]


def pct(a, b):
    return f"{100 * (a / b - 1):+.1f}%"


def geo(vals):
    return 100 * (math.exp(sum(math.log(v) for v in vals) / len(vals)) - 1)


def gp(vals):
    return f"{geo(vals):+.1f}%"


def main(data_dir="data"):
    d = load(data_dir)
    print("## raw medians, tok/s [min-max]\n")
    print("| arm | chat decode | 4K prompt | 16K prompt | 32K prompt | agent decode | burst (2 clients, total) |")
    print("| --- | --- | --- | --- | --- | --- | --- |")
    for q in QUANTS:
        for w, s in ORDER:
            arm, r = f"{q}-{w}-p{s}", d[f"{q}-{w}-p{s}"]["results"]
            print(f"| {arm} | {cell(r['chat'], 'decode_tps')} | {cell(r['prompts']['4K'], 'prompt_tps')} | "
                  f"{cell(r['prompts']['16K'], 'prompt_tps')} | {cell(r['prompts']['32K'], 'prompt_tps')} | "
                  f"{cell(r['agent'], 'turn_decode_tps')} | "
                  f"{cell(r['clients'], 'total_tps', 2) if r.get('clients') else 'n/a'} |")
    print("\n## time to first token, seconds [min-max]\n")
    print("| arm | chat | 4K | 16K | 32K | agent turn |")
    print("| --- | --- | --- | --- | --- | --- |")
    for q in QUANTS:
        for w, s in ORDER:
            arm, r = f"{q}-{w}-p{s}", d[f"{q}-{w}-p{s}"]["results"]
            print(f"| {arm} | {cell(r['chat'], 'ttft_s', 0)} | {cell(r['prompts']['4K'], 'ttft_s', 0)} | "
                  f"{cell(r['prompts']['16K'], 'ttft_s', 0)} | {cell(r['prompts']['32K'], 'ttft_s', 0)} | "
                  f"{cell(r['agent'], 'turn_ttft_s', 0)} |")

    print("\n## STRATA_HIP_WMMA=1 vs unset, same quant and slots (positive = WMMA faster)\n")
    print("| quant, slots | 4K prompt | 16K prompt | 32K prompt | geomean prompt | chat decode | agent decode | geomean decode |")
    print("| --- | --- | --- | --- | --- | --- | --- | --- |")
    g = {k: [] for k in ("4K", "16K", "32K", "chat", "agent")}
    gt = {k: [] for k in ("chat", "4K", "16K", "32K", "agent")}
    for s in (1, 2):
        for q in QUANTS:
            a, b = f"{q}-wmma-p{s}", f"{q}-plain-p{s}"
            ra, rb = d[a]["results"], d[b]["results"]
            v = {k: med(ra, "p", k) / med(rb, "p", k) for k in PROMPTS}
            v["chat"] = med(ra, "chat", "decode_tps") / med(rb, "chat", "decode_tps")
            v["agent"] = med(ra, "agent", "turn_decode_tps") / med(rb, "agent", "turn_decode_tps")
            for k in g:
                g[k].append(v[k])
            print(f"| {q}, {s} | {pct(v['4K'], 1)} | {pct(v['16K'], 1)} | {pct(v['32K'], 1)} | "
                  f"{gp([v[k] for k in PROMPTS])} | {pct(v['chat'], 1)} | {pct(v['agent'], 1)} | "
                  f"{gp([v['chat'], v['agent']])} |")
    print("| **geomean, six pairs** | " + " | ".join(gp(g[k]) for k in ("4K", "16K", "32K")) +
          " | - | " + " | ".join(gp(g[k]) for k in ("chat", "agent")) + " | - |")
    print("\nsame pairs, time to first token (negative = WMMA faster)\n")
    print("| quant, slots | chat | 4K | 16K | 32K | agent |")
    print("| --- | --- | --- | --- | --- | --- |")
    for s in (1, 2):
        for q in QUANTS:
            a, b = f"{q}-wmma-p{s}", f"{q}-plain-p{s}"
            ra, rb = d[a]["results"], d[b]["results"]
            t = {"chat": med(ra, "chat", "ttft_s") / med(rb, "chat", "ttft_s"),
                 "agent": med(ra, "agent", "turn_ttft_s") / med(rb, "agent", "turn_ttft_s")}
            for k in PROMPTS:
                t[k] = med(ra, "t", k) / med(rb, "t", k)
            for k in gt:
                gt[k].append(t[k])
            print(f"| {q}, {s} | " + " | ".join(pct(t[k], 1) for k in ("chat", "4K", "16K", "32K", "agent")) + " |")
    print("| **geomean, six pairs** | " + " | ".join(gp(gt[k]) for k in ("chat", "4K", "16K", "32K", "agent")) + " |")

    print("\n## parallel 2 vs parallel 1, WMMA on\n")
    print("| quant | chat decode | agent decode | 4K prompt | 16K prompt | 32K prompt | chat TTFT | agent TTFT | aggregate |")
    print("| --- | --- | --- | --- | --- | --- | --- | --- | --- |")
    pc, pa, pp, ptt = [], [], [], []
    for q in QUANTS:
        a, b = f"{q}-wmma-p2", f"{q}-wmma-p1"
        ra, rb = d[a]["results"], d[b]["results"]
        ch = med(ra, "chat", "decode_tps") / med(rb, "chat", "decode_tps")
        ag = med(ra, "agent", "turn_decode_tps") / med(rb, "agent", "turn_decode_tps")
        t = med(ra, "chat", "ttft_s") / med(rb, "chat", "ttft_s")
        att = med(ra, "agent", "turn_ttft_s") / med(rb, "agent", "turn_ttft_s")
        pr = {k: med(ra, "p", k) / med(rb, "p", k) for k in PROMPTS}
        pc.append(ch); pa.append(ag); pp += list(pr.values()); ptt.append(t)
        print(f"| {q} | {pct(ch, 1)} | {pct(ag, 1)} | " + " | ".join(pct(pr[k], 1) for k in PROMPTS) +
              f" | {pct(t, 1)} | {pct(att, 1)} | {1 / ch:.3f} |")
    print(f"| **geomean** | {gp(pc)} | {gp(pa)} | {gp(pp)} (nine prompt pairs) | | | {gp(ptt)} | | |")
    print("\nsame pairs with WMMA off\n")
    for q in QUANTS:
        ra, rb = d[f"{q}-plain-p2"]["results"], d[f"{q}-plain-p1"]["results"]
        print(f"| {q} | chat {pct(med(ra, 'chat', 'decode_tps'), med(rb, 'chat', 'decode_tps'))} | "
              f"agent {pct(med(ra, 'agent', 'turn_decode_tps'), med(rb, 'agent', 'turn_decode_tps'))} |")
    print("geomeans over the three: chat "
          + gp([med(d[f'{q}-plain-p2']['results'], 'chat', 'decode_tps') / med(d[f'{q}-plain-p1']['results'], 'chat', 'decode_tps') for q in QUANTS])
          + ", agent "
          + gp([med(d[f'{q}-plain-p2']['results'], 'agent', 'turn_decode_tps') / med(d[f'{q}-plain-p1']['results'], 'agent', 'turn_decode_tps') for q in QUANTS]))

    print("\n## 2-client burst (the 6 -p2 arms), aggregate of the two clients\n")
    print("| quant (WMMA on, 2 slots) | burst total | per client | share of that arm's solo | share vs 1 slot | p50 TTFT | p95 TTFT | p50 latency | p95 latency | solo 128-token time | latency ratio |")
    print("| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |")
    shares = []
    for q in QUANTS:
        r = d[f"{q}-wmma-p2"]["results"]
        tot, solo, solo1 = med(r, "clients", "total_tps"), med(r, "chat", "decode_tps"), med(d[f"{q}-wmma-p1"]["results"], "chat", "decode_tps")
        c, s128 = r["clients"], 128 / solo
        shares.append(tot / solo)
        print(f"| {q} | {tot:,.1f} [{cell(r['clients'], 'total_tps', 2)}] | {tot / 2:.1f} | {100 * tot / solo:.1f}% | "
              f"{100 * tot / solo1:.1f}% | {c['ttft_p50_s']} s | {c['ttft_p95_s']} s | {c['latency_p50_s']} s | "
              f"{c['latency_p95_s']} s | {s128:.2f} | {c['latency_p50_s'] / s128:.2f}x |")
    print(f"geomean aggregate share {geo(shares) + 100:.1f}%; "
          f"tail (p95/p50) " + ", ".join(f"{100 * (d[f'{q}-wmma-p2']['results']['clients']['latency_p95_s'] / d[f'{q}-wmma-p2']['results']['clients']['latency_p50_s'] - 1):.1f}%" for q in QUANTS)
          + "; errors " + str(sum(d[a]["results"]["clients"]["errors"] for a in d if d[a]["results"].get("clients"))))
    for q in QUANTS:
        rb = d[f"{q}-plain-p2"]["results"]
        print(f"{q} burst with WMMA off: {med(rb, 'clients', 'total_tps'):.2f} = "
              f"{100 * med(rb, 'clients', 'total_tps') / med(rb, 'chat', 'decode_tps'):.1f}% of that arm's solo")

    print("\n## quant, against IQ2_XS at the same setting\n")
    for slots in (1, 2):
        base = f"iq2_xs-wmma-p{slots}"
        print(f"parallel {slots}:")
        for q in QUANTS[1:]:
            ra, rb = d[f"{q}-wmma-p{slots}"]["results"], d[base]["results"]
            ch = med(ra, "chat", "decode_tps") / med(rb, "chat", "decode_tps")
            ag = med(ra, "agent", "turn_decode_tps") / med(rb, "agent", "turn_decode_tps")
            line = (f"  {q}: chat {pct(ch, 1)}, agent {pct(ag, 1)}, gm decode {gp([ch, ag])}, "
                    f"gm prompt {gp([med(ra, 'p', k) / med(rb, 'p', k) for k in PROMPTS])}, "
                    f"chat TTFT {pct(med(ra, 'chat', 'ttft_s'), med(rb, 'chat', 'ttft_s'))}, "
                    f"32K TTFT {pct(med(ra, 't', '32K'), med(rb, 't', '32K'))}")
            line += ", " + ", ".join(f"{k} {pct(med(ra, 'p', k), med(rb, 'p', k))}" for k in PROMPTS)
            if slots == 2:
                line += f", burst {pct(med(ra, 'clients', 'total_tps'), med(rb, 'clients', 'total_tps'))}"
            print(line)

    print("\n## expert cache, arena, VRAM at start, wall time\n")
    for q in QUANTS:
        for s in (1, 2):
            e = d[f"{q}-wmma-p{s}"]["machine"]["engine_info"]
            print(f"{q} parallel {s}: {e['expert_slots']:,} slots, {e['expert_cache_mib']:,} MiB "
                  f"({e['expert_cache_mib'] / 1024:.1f} GiB); arena {e['arena_mib']:,} MiB "
                  f"({e['arena_mib'] / 1024:.1f} GiB); {e['vram_free_mib']} MiB free at start")
    for q in QUANTS:
        e1, e2 = d[f"{q}-wmma-p1"]["machine"]["engine_info"], d[f"{q}-wmma-p2"]["machine"]["engine_info"]
        print(f"{q}: parallel 2 costs {100 * (e2['expert_slots'] / e1['expert_slots'] - 1):.1f}% of the expert slots")
    print(f"arena IQ3_S / IQ2_XS = {d['iq3_s-wmma-p1']['machine']['engine_info']['arena_mib'] / d['iq2_xs-wmma-p1']['machine']['engine_info']['arena_mib']:.2f}x; "
          f"expert slots IQ3_S / IQ2_XS at 1 slot = {100 * d['iq3_s-wmma-p1']['machine']['engine_info']['expert_slots'] / d['iq2_xs-wmma-p1']['machine']['engine_info']['expert_slots'] - 1:.0f}%")
    for s in (1, 2):
        for q in QUANTS:
            a, b = d[f"{q}-wmma-p{s}"]["elapsed_s"], d[f"{q}-plain-p{s}"]["elapsed_s"]
            print(f"{q} parallel {s}: wall {a:.1f} s (WMMA on) vs {b:.1f} s (off) = {100 * (a / b - 1):.1f}%")

    print("\n## within-arm repetition spread of the 3 prompt runs, (max-min)/median\n")
    for k in PROMPTS:
        v = sorted((max(x["prompt_tps"] for x in d[a]["results"]["prompts"][k]["requests"]) -
                    min(x["prompt_tps"] for x in d[a]["results"]["prompts"][k]["requests"])) /
                   statistics.median([x["prompt_tps"] for x in d[a]["results"]["prompts"][k]["requests"]]) * 100
                   for a in d)
        print(f"{k}: {v[0]:.1f}-{v[-1]:.1f}%, median {statistics.median(v):.1f}%")

    print("\n## agent suite, over the 60 sessions\n")
    ag = [d[a]["results"]["agent"] for a in d]
    print(f"cache hit {min(x['hit_pct']['min'] for x in ag):.1f}-{max(x['hit_pct']['max'] for x in ag):.1f}%; "
          f"re-read {min(x['reread_tokens']['min'] for x in ag)}-{max(x['reread_tokens']['max'] for x in ag)} tokens; "
          f"new {min(x['new_tokens']['min'] for x in ag):,}-{max(x['new_tokens']['max'] for x in ag):,}; "
          f"last turn {min(x['last_turn_prompt_tokens']['min'] for x in ag):,}-{max(x['last_turn_prompt_tokens']['max'] for x in ag):,}; "
          f"first turn TTFT {min(x['first_turn_ttft_s']['min'] for x in ag):.1f}-{max(x['first_turn_ttft_s']['max'] for x in ag):.1f} s")

    print("\n## counts and request shapes\n")
    n = b = turns = 0
    for a in d:
        r = d[a]["results"]
        n += len(r["chat"]["requests"]) + sum(len(r["prompts"][k]["requests"]) for k in PROMPTS) + sum(len(x) for x in r["agent"]["sessions"])
        turns += sum(len(x) - 1 for x in r["agent"]["sessions"])
        if r.get("clients"):
            b += 2 * len(r["clients"]["rounds"])
    cp = [x["prompt_tokens"] for a in d for x in d[a]["results"]["chat"]["requests"]]
    gen = [x["generated_tokens"] for a in d for s in d[a]["results"]["agent"]["sessions"] for x in s]
    print(f"suite requests {n}, burst requests {b}, total {n + b}; agent follow-up turns {turns}; "
          f"failures {sum(len(d[a]['results']['failures']) for a in d)}, "
          f"skipped {sum(len(d[a]['results']['skipped']) for a in d)}")
    print(f"chat prompt tokens {min(cp)}-{max(cp)}, generated {d['iq2_xs-wmma-p1']['results']['chat']['generated_tokens']['median']}; "
          + " / ".join(f"{k} {d['iq2_xs-wmma-p1']['results']['prompts'][k]['prompt_tokens']['median']:,}" for k in PROMPTS)
          + f"; agent generated {min(gen)}-{max(gen)} per turn")
    print(f"reused tokens across the {sum(len(d[a]['results']['prompts'][k]['requests']) for a in d for k in PROMPTS)} "
          f"prompt requests: {sum(q['reused_tokens'] for a in d for k in PROMPTS for q in d[a]['results']['prompts'][k]['requests'])}")
    readme_tables(d)



def readme_tables(d):
    """The README tables in README.md's shape, printed from data/. The README's own numbers come
    from these; check_report.py recomputes the same cells a second time, in its own code, and
    checks the file against that."""
    m = {a: d[a]["machine"] for a in d}
    m0 = m["iq2_xs-wmma-p1"]
    ei, ei2 = m0["engine_info"], m["iq2_xs-wmma-p2"]["engine_info"]
    ag = [d[a]["results"]["agent"] for a in d]
    turns = [x for a in d for sess in d[a]["results"]["agent"]["sessions"] for x in sess]
    r0 = d["iq2_xs-wmma-p1"]["results"]

    print("\n## README table: the machine block\n")
    print("| field | value |\n| --- | --- |")
    print(f"| `machine.gpu` / `machine.gpu_vram_mib` | `[\"{m0['gpu'][0]}\"]` / {m0['gpu_vram_mib']:,.0f} MiB |")
    print("| `machine.gpu_driver` / `machine.cuda` | `null` / `null` |")
    print(f"| `machine.cpu` / cores / threads / RAM | {m0['cpu']} / {m0['cpu_cores']} / "
          f"{m0['cpu_threads']} / {m0['ram_gib']:.1f} GiB |")
    print(f"| `machine.os` / `machine.python` | {m0['os']} / {m0['python']} |")
    print(f"| `machine.strata_version` / `strata_commit` | {m0['strata_version']} / `{m0['strata_commit']}` |")
    print(f"| `machine.engine_version` | {m0['engine_version']} |")
    print("| `machine.model` / `machine.context` | " + ", ".join(f"`swift-1.5-{q}`" for q in QUANTS) +
          f" / {m0['context']:,} |")
    print("| `machine.quant` | `quant` is null in all 12 arms |")
    print("| `machine.parallel_slots` | 1 in the six 1-slot arms, 2 in the six 2-slot arms |")
    print("| `machine.config` / `machine.launch` | `{}` / `null` |")
    print("| `machine.vram_after` | `{\"elastic\": false}` |")

    print("\n## README table: what the engine reports about itself\n")
    print("| field | value |\n| --- | --- |")
    print(f"| `kv` / `kv_resident` / `context` | {ei['kv']} / {ei['kv_resident']:,} / {ei['context']:,} |")
    print(f"| `spec` / `mtp_max` / `lookup` | {ei['spec']} / {ei['mtp_max']} / {ei['lookup']} |")
    print(f"| `pcie_frac` / `pool_workers` / `spec_min_p` | {ei['pcie_frac']} in all 12; `pool_workers` "
          f"{ei['pool_workers']} on IQ2_XS and {m['iq3_xxs-wmma-p1']['engine_info']['pool_workers']} on "
          f"IQ3_XXS/IQ3_S; `spec_min_p` {ei['spec_min_p']} on IQ2_XS and "
          f"{m['iq3_xxs-wmma-p1']['engine_info']['spec_min_p']} on the other two |")
    caps = sorted({m[a]['engine_info']['prefill_cap'] for a in m})
    print(f"| `prefill_cap` / `prefill_stages` / `prefill_pipe` | " +
          f"{caps[-1]:,} in ten arms, " +
          ", ".join(f"{c:,} in {a} ({m[a]['engine_info']['prefill_cap']:,})" for a, c in
                    sorted(((a, m[a]['engine_info']['prefill_cap']) for a in m
                            if m[a]['engine_info']['prefill_cap'] != caps[-1]))) +
          f" / {ei['prefill_stages']} / {ei['prefill_pipe']} |")
    print(f"| `cvec` | {ei['cvec']} |")
    print(f"| `conversation_cache_slots` / `min_free_mib` / `min_tokens` | {ei['conversation_cache_slots']} / "
          f"{ei['conversation_cache_min_free_mib']:,} / {ei['conversation_cache_min_tokens']} |")
    print(f"| `tail_role_token` | {ei['tail_role_token']} |")
    print(f"| `vram_elastic` | {ei['vram_elastic']} |")
    print("| `arena_mib` | " + " / ".join(f"{m[f'{q}-wmma-p1']['engine_info']['arena_mib']:,} ({q})" for q in QUANTS) + " |")
    print("| `expert_slots` / `expert_cache_mib` | see the expert table, they differ per quant and per slot count |")
    print(f"| `batch_slots` / `slot_cache` / `batch_groups` | {ei2['batch_slots']} / {ei2['slot_cache']} / "
          f"{ei2['batch_groups']} in the six 2-slot arms; the keys are absent in the six 1-slot arms |")
    print(f"| `stream_all_min` | {ei['stream_all_min']:,} |")

    print("\n## README table: request shapes\n")
    cp = [x["prompt_tokens"] for a in d for x in d[a]["results"]["chat"]["requests"]]
    gen = [x["generated_tokens"] for x in turns]
    print("| test | prompt tokens | reused | generated | requests per arm |\n| --- | --- | --- | --- | --- |")
    print(f"| chat (4 prompts, warm) | {min(cp)}-{max(cp)} | 0 on the first, warm after | "
          f"{r0['chat']['generated_tokens']['median']:.0f} | {len(r0['chat']['requests'])} |")
    print(f"| 4K / 16K / 32K prompt | " + " / ".join(f"{r0['prompts'][k]['prompt_tokens']['median']:,.0f}" for k in PROMPTS) +
          f" | 0 (all {sum(len(d[a]['results']['prompts'][k]['requests']) for a in d for k in PROMPTS)} prompt requests start cold) | 0 | 3 each |")
    lo = min(x["last_turn_prompt_tokens"]["min"] for x in ag)
    hi = max(x["last_turn_prompt_tokens"]["max"] for x in ag)
    print(f"| agent session, 6 turns | {min(x['prompt_tokens'] for x in r0['agent']['sessions'][0])} (turn 1) -> "
          f"{lo:,}-{hi:,} (turn 6) | grows with the session | {min(gen)}-{max(gen)} per turn | "
          f"{len(r0['agent']['sessions'])} sessions x {len(r0['agent']['sessions'][0])} |")
    print("| 2-client burst, 3 rounds x 2 clients | 400-word essay prompts, nonce-prefixed | "
          "0 (nonce-prefixed, so every prompt is fresh) | 128 each | 6 (only in the `-p2` arms) |")

    print("\n## README table: speculation acceptance\n")
    def acc(reqs):
        return 100 * sum(x["drafts_accepted"] for x in reqs) / sum(x["drafts_offered"] for x in reqs)
    print("| arm | chat accept | agent accept | prompt accept |\n| --- | --- | --- | --- |")
    for q in QUANTS:
        for w, s in ORDER:
            arm = f"{q}-{w}-p{s}"
            r = d[arm]["results"]
            print(f"| {arm} | {acc(r['chat']['requests']):.1f}% | "
                  f"{acc([x for sess in r['agent']['sessions'] for x in sess]):.1f}% | "
                  f"{acc([x for k in PROMPTS for x in r['prompts'][k]['requests']]):.1f}% |")

    print("\n## README table: quant, against IQ2_XS at the same setting\n")
    for slots in (1, 2):
        base = f"iq2_xs-wmma-p{slots}"
        head = ("| quant | chat decode | agent decode | geomean decode | 4K prompt | 16K prompt | 32K prompt | "
                "geomean prompt | chat TTFT | 32K TTFT |")
        cols = 10
        if slots == 2:
            head = ("| quant | chat decode | agent decode | geomean decode | burst total | 4K prompt | 16K prompt | "
                    "32K prompt | geomean prompt | chat TTFT | 32K TTFT |")
            cols = 11
        print(head)
        print("| " + " | ".join(["---"] * cols) + " |")
        for q in QUANTS:
            ra, rb = d[f"{q}-wmma-p{slots}"]["results"], d[base]["results"]
            if q == "iq2_xs":
                print("| iq2_xs | " + " | ".join(["-"] * (cols - 1)) + " |")
                continue
            ch = med(ra, "chat", "decode_tps") / med(rb, "chat", "decode_tps")
            agv = med(ra, "agent", "turn_decode_tps") / med(rb, "agent", "turn_decode_tps")
            pr = [med(ra, "p", k) / med(rb, "p", k) for k in PROMPTS]
            cells = [pct(ch, 1), pct(agv, 1), gp([ch, agv])]
            if slots == 2:
                cells.append(pct(med(ra, "clients", "total_tps"), med(rb, "clients", "total_tps")))
            cells += [pct(v, 1) for v in pr] + [gp(pr),
                    pct(med(ra, "chat", "ttft_s"), med(rb, "chat", "ttft_s")),
                    pct(med(ra, "t", "32K"), med(rb, "t", "32K"))]
            print(f"| {q} | " + " | ".join(cells) + " |")

    print("\n## README table: the agent suite, ranges over the 12 arms\n")
    print("| field | range across the 12 arms |\n| --- | --- |")
    print(f"| cache hit rate | {min(x['hit_pct']['min'] for x in ag):.1f}-{max(x['hit_pct']['max'] for x in ag):.1f}% |")
    print(f"| re-read tokens per session | {min(x['reread_tokens']['min'] for x in ag)}-{max(x['reread_tokens']['max'] for x in ag)} |")
    print(f"| new prompt tokens per session | {min(x['new_tokens']['min'] for x in ag):,}-{max(x['new_tokens']['max'] for x in ag):,} |")
    print(f"| last-turn prompt tokens | {lo:,}-{hi:,} |")
    print(f"| first-turn TTFT | {min(x['first_turn_ttft_s']['min'] for x in ag):.1f}-"
          f"{max(x['first_turn_ttft_s']['max'] for x in ag):.1f} s |")
    print(f"| generated tokens per turn | {min(gen)}-{max(gen)} |")

    print("\n## README table: expert cache\n")
    print("| arm | expert slots | MiB | GiB |\n| --- | --- | --- | --- |")
    for q in QUANTS:
        for s in (1, 2):
            e = d[f"{q}-wmma-p{s}"]["machine"]["engine_info"]
            print(f"| {q}, {s} slot{'s' if s == 2 else ''} | {e['expert_slots']:,} | {e['expert_cache_mib']:,} | "
                  f"{e['expert_cache_mib'] / 1024:.1f} |")

    print("\n## README table: suite wall time\n")
    print("| quant | 1 slot, WMMA on | 1 slot, WMMA off | delta | 2 slots, WMMA on | 2 slots, WMMA off | delta |")
    print("| --- | --- | --- | --- | --- | --- | --- |")
    for q in QUANTS:
        a1, b1 = d[f"{q}-wmma-p1"]["elapsed_s"], d[f"{q}-plain-p1"]["elapsed_s"]
        a2, b2 = d[f"{q}-wmma-p2"]["elapsed_s"], d[f"{q}-plain-p2"]["elapsed_s"]
        print(f"| {q} | {a1:.1f} s | {b1:.1f} s | {100 * (a1 / b1 - 1):.1f}% | {a2:.1f} s | {b2:.1f} s | "
              f"{100 * (a2 / b2 - 1):.1f}% |")
    walls = sorted(abs(100 * (d[f'{q}-wmma-p{s}']['elapsed_s'] / d[f'{q}-plain-p{s}']['elapsed_s'] - 1)) for q in QUANTS for s in (1, 2))
    print(f"the six deltas span {walls[0]:.1f}-{walls[-1]:.1f}%")



if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "data")
