#!/usr/bin/env python3
"""check_report.py - recompute every number README.md states, from data/, and check it is stated.

Usage: python3 check_report.py [data-dir] [README.md]

This is the independent check of README.md. It reads the 12 results.json files, recomputes the
medians, the matched-pair percentages, the geometric means, the shares, the spreads, the cache
sizes and the counts, formats each the way README.md writes it, and looks for that exact string in
README.md. It shares no code with summarize.py; the two agreeing on a number is the check.

Exit 0 and "0 missing" means every number this script derives from the raw data appears in the
prose. A missing number means README.md states a value the data does not produce, which is the
failure mode this file exists to catch.
"""
import json
import math
import re
import statistics
import sys
from pathlib import Path

QUANTS = ["iq2_xs", "iq3_xxs", "iq3_s"]
PROMPTS = ("4K", "16K", "32K")
ARM_ORDER = [("wmma", 1), ("wmma", 2), ("plain", 2), ("plain", 1)]


def f1(v):
    return f"{v:,.1f}"


def load(data_dir):
    d = {}
    for q in QUANTS:
        for w, s in ARM_ORDER:
            arm = f"{q}-{w}-p{s}"
            d[arm] = json.loads((Path(data_dir) / arm / "results.json").read_text())
    return d


def md(res, kind, key=None):
    """Median of one stat block: chat/agent/clients, or prompts[key]."""
    if kind == "chat":
        return res["chat"][key]["median"]
    if kind == "agent":
        return res["agent"][key]["median"]
    if kind == "clients":
        return res["clients"][key]["median"] if res.get("clients") else None
    blk = res["prompts"][key]
    return blk["prompt_tps"]["median"] if kind == "p" else blk["ttft_s"]["median"]


def main(data_dir="data", readme="README.md"):
    d = load(data_dir)
    text = re.sub(r"\s+", " ", Path(readme).read_text())
    out = []      # (label, string)
    miss = []

    def add(label, s):
        out.append((label, s))

    # ---- raw medians, tables 1 and 2 -------------------------------------------------------
    for arm in d:
        r = d[arm]["results"]
        for lab, blk, nd in (("chat", r["chat"]["decode_tps"], 1), ("4K", r["prompts"]["4K"]["prompt_tps"], 1),
                             ("16K", r["prompts"]["16K"]["prompt_tps"], 1), ("32K", r["prompts"]["32K"]["prompt_tps"], 1),
                             ("agent", r["agent"]["turn_decode_tps"], 1),
                             ("chat ttft", r["chat"]["ttft_s"], 2), ("4K ttft", r["prompts"]["4K"]["ttft_s"], 2),
                             ("16K ttft", r["prompts"]["16K"]["ttft_s"], 2), ("32K ttft", r["prompts"]["32K"]["ttft_s"], 2),
                             ("agent ttft", r["agent"]["turn_ttft_s"], 2)):
            add(f"{arm} {lab}", f"{f1(blk['median']) if nd == 1 else format(blk['median'], '.2f')} "
                                f"[{f1(blk['min']) if nd == 1 else format(blk['min'], '.2f')}-"
                                f"{f1(blk['max']) if nd == 1 else format(blk['max'], '.2f')}]")
        if r.get("clients"):
            c = r["clients"]["total_tps"]
            add(f"{arm} burst", f"{c['median']:.2f} [{c['min']:.2f}-{c['max']:.2f}]")
            if "-wmma-" in arm:
                add(f"{arm} burst 1dp", f"{c['median']:.1f}")

    def pct(a, b):
        return f"{100 * (a / b - 1):+.1f}%"

    def geo(vals):
        return 100 * (math.exp(sum(math.log(v) for v in vals) / len(vals)) - 1)

    def gp(vals):
        return f"{geo(vals):+.1f}%"

    # ---- WMMA pairs: on vs off, same quant, same slots ------------------------------------
    g = {k: [] for k in ("4K", "16K", "32K", "chat", "agent")}
    gt = {k: [] for k in ("4K", "16K", "32K", "agent")}
    for w_off_s in ((1), (2)):
        for q in QUANTS:
            a, b = f"{q}-wmma-p{w_off_s}", f"{q}-plain-p{w_off_s}"
            ra, rb = d[a]["results"], d[b]["results"]
            for k in PROMPTS:
                add(f"wmma {a} {k}", pct(md(ra, "p", k), md(rb, "p", k)))
                g[k].append(md(ra, "p", k) / md(rb, "p", k))
            for k in PROMPTS:
                gt[k].append(md(ra, "t", k) / md(rb, "t", k))
                add(f"wmma-ttft {a} {k}", pct(md(ra, "t", k), md(rb, "t", k)))
            add(f"wmma {a} chat", pct(md(ra, "chat", "decode_tps"), md(rb, "chat", "decode_tps")))
            add(f"wmma {a} agent", pct(md(ra, "agent", "turn_decode_tps"), md(rb, "agent", "turn_decode_tps")))
            add(f"wmma-ttft {a} chat", pct(md(ra, "chat", "ttft_s"), md(rb, "chat", "ttft_s")))
            add(f"wmma-ttft {a} agent", pct(md(ra, "agent", "turn_ttft_s"), md(rb, "agent", "turn_ttft_s")))
            gt["agent"].append(md(ra, "agent", "turn_ttft_s") / md(rb, "agent", "turn_ttft_s"))
            g["chat"].append(md(ra, "chat", "decode_tps") / md(rb, "chat", "decode_tps"))
            g["agent"].append(md(ra, "agent", "turn_decode_tps") / md(rb, "agent", "turn_decode_tps"))
            add(f"wmma {a} gm prompt", gp([md(ra, "p", k) / md(rb, "p", k) for k in PROMPTS]))
            add(f"wmma {a} gm decode", gp([md(ra, "chat", "decode_tps") / md(rb, "chat", "decode_tps"),
                                           md(ra, "agent", "turn_decode_tps") / md(rb, "agent", "turn_decode_tps")]))
    for k in ("4K", "16K", "32K", "chat", "agent"):
        add(f"wmma geomean {k}", gp(g[k]))
    for k in ("4K", "16K", "32K", "agent"):
        add(f"wmma geomean ttft {k}", gp(gt[k]))
    add("wmma geomean ttft chat", gp([md(d[f'{q}-wmma-p{s}']["results"], "chat", "ttft_s") /
                                      md(d[f"{q}-plain-p{s}"]["results"], "chat", "ttft_s")
                                      for q in QUANTS for s in (1, 2)]))

    # ---- parallel 2 vs parallel 1, WMMA on -------------------------------------------------
    pc, pa, pp, ptt = [], [], [], []
    for q in QUANTS:
        a, b = f"{q}-wmma-p2", f"{q}-wmma-p1"
        ra, rb = d[a]["results"], d[b]["results"]
        ch = md(ra, "chat", "decode_tps") / md(rb, "chat", "decode_tps")
        ag = md(ra, "agent", "turn_decode_tps") / md(rb, "agent", "turn_decode_tps")
        pc.append(ch); pa.append(ag)
        add(f"par {q} chat", pct(ch, 1))
        add(f"par {q} agent", pct(ag, 1))
        for k in PROMPTS:
            r = md(ra, "p", k) / md(rb, "p", k)
            pp.append(r)
            add(f"par {q} {k}", pct(r, 1))
        t = md(ra, "chat", "ttft_s") / md(rb, "chat", "ttft_s")
        ptt.append(t)
        add(f"par {q} chat ttft", pct(t, 1))
        add(f"par {q} agent ttft", pct(md(ra, "agent", "turn_ttft_s") / md(rb, "agent", "turn_ttft_s"), 1))
        add(f"par {q} aggregate", f"{1 / ch:.3f}")
    add("par geomean chat", gp(pc))
    add("par geomean agent", gp(pa))
    add("par geomean prompt", gp(pp))
    add("par geomean chat ttft", gp(ptt))
    for q in QUANTS:
        a, b = f"{q}-plain-p2", f"{q}-plain-p1"
        ra, rb = d[a]["results"], d[b]["results"]
        add(f"par-plain {q} chat", pct(md(ra, "chat", "decode_tps"), md(rb, "chat", "decode_tps")))
        add(f"par-plain {q} agent", pct(md(ra, "agent", "turn_decode_tps"), md(rb, "agent", "turn_decode_tps")))
    add("par-plain geomean chat", gp([md(d[f"{q}-plain-p2"]["results"], "chat", "decode_tps") /
                                      md(d[f"{q}-plain-p1"]["results"], "chat", "decode_tps") for q in QUANTS]))
    add("par-plain geomean agent", gp([md(d[f"{q}-plain-p2"]["results"], "agent", "turn_decode_tps") /
                                       md(d[f"{q}-plain-p1"]["results"], "agent", "turn_decode_tps") for q in QUANTS]))

    # ---- burst ----------------------------------------------------------------------------
    shares, agg_shares = [], []
    for q in QUANTS:
        a = f"{q}-wmma-p2"
        r = d[a]["results"]
        tot, solo = md(r, "clients", "total_tps"), md(r, "chat", "decode_tps")
        c = r["clients"]
        shares.append(tot / solo)
        add(f"burst {q} share", f"{100 * tot / solo:.1f}%")
        add(f"burst {q} per client share", f"{100 * tot / 2 / solo:.1f}%")
        add(f"burst {q} per client", f"{tot / 2:.1f}")
        add(f"burst {q} p50ttft", f"{c['ttft_p50_s']} s")
        add(f"burst {q} p95ttft", f"{c['ttft_p95_s']} s")
        add(f"burst {q} p50lat", f"{c['latency_p50_s']} s")
        add(f"burst {q} p95lat", f"{c['latency_p95_s']}")
        solo128 = 128 / solo
        add(f"burst {q} solo128", f"{solo128:.2f}")
        add(f"burst {q} lat ratio", f"{100 * (c['latency_p50_s'] / solo128 - 1):+.1f}%")
        add(f"burst {q} x", f"{c['latency_p50_s'] / solo128:.2f}x")
        add(f"burst {q} tail", f"{100 * (c['latency_p95_s'] / c['latency_p50_s'] - 1):.1f}%")
        b = f"{q}-plain-p2"
        rb = d[b]["results"]
        add(f"burst {b} total", f"{md(rb, 'clients', 'total_tps'):.2f}")
        add(f"burst {b} share", f"{100 * md(rb, 'clients', 'total_tps') / md(rb, 'chat', 'decode_tps'):.1f}%")
        add(f"burst {q} share vs 1-slot", f"{100 * tot / md(d[f'{q}-wmma-p1']['results'], 'chat', 'decode_tps'):.1f}%")
    add("burst geomean share", f"{geo(shares) + 100:.1f}%")
    add("burst errors", str(sum(d[a]["results"]["clients"]["errors"] for a in d if d[a]["results"].get("clients"))))
    add("burst vs iq2_xs iq3_xxs", pct(md(d["iq3_xxs-wmma-p2"]["results"], "clients", "total_tps"),
                                       md(d["iq2_xs-wmma-p2"]["results"], "clients", "total_tps")))
    add("burst vs iq2_xs iq3_s", pct(md(d["iq3_s-wmma-p2"]["results"], "clients", "total_tps"),
                                     md(d["iq2_xs-wmma-p2"]["results"], "clients", "total_tps")))

    # ---- quant ---------------------------------------------------------------------------
    for slots in (1, 2):
        base = f"iq2_xs-wmma-p{slots}"
        for q in QUANTS[1:]:
            a = f"{q}-wmma-p{slots}"
            ra, rb = d[a]["results"], d[base]["results"]
            add(f"quant {q} p{slots} chat", pct(md(ra, "chat", "decode_tps"), md(rb, "chat", "decode_tps")))
            add(f"quant {q} p{slots} agent", pct(md(ra, "agent", "turn_decode_tps"), md(rb, "agent", "turn_decode_tps")))
            for k in PROMPTS:
                add(f"quant {q} p{slots} {k}", pct(md(ra, "p", k), md(rb, "p", k)))
            add(f"quant {q} p{slots} gm decode", gp([md(ra, "chat", "decode_tps") / md(rb, "chat", "decode_tps"),
                                                     md(ra, "agent", "turn_decode_tps") / md(rb, "agent", "turn_decode_tps")]))
            add(f"quant {q} p{slots} gm prompt", gp([md(ra, "p", k) / md(rb, "p", k) for k in PROMPTS]))
            if slots == 2:
                add(f"quant {q} p2 burst", pct(md(ra, "clients", "total_tps"), md(rb, "clients", "total_tps")))
            add(f"quant {q} p{slots} chat ttft", pct(md(ra, "chat", "ttft_s"), md(rb, "chat", "ttft_s")))
            add(f"quant {q} p{slots} 32K ttft", pct(md(ra, "t", "32K"), md(rb, "t", "32K")))

    # ---- sizes, wall time, spread, counts -------------------------------------------------
    for q in QUANTS:
        for s in (1, 2):
            e = d[f"{q}-wmma-p{s}"]["machine"]["engine_info"]
            add(f"expert {q} p{s} slots", f"{e['expert_slots']:,}")
            add(f"expert {q} p{s} mib", f"{e['expert_cache_mib']:,}")
            add(f"expert {q} p{s} gib", f"{e['expert_cache_mib'] / 1024:.1f}")
            add(f"arena {q}", f"{e['arena_mib']:,}")
            add(f"arena {q} gib", f"{e['arena_mib'] / 1024:.1f}")
            add(f"vramfree {q}", f"{e['vram_free_mib']}")
        e1, e2 = d[f"{q}-wmma-p1"]["machine"]["engine_info"], d[f"{q}-wmma-p2"]["machine"]["engine_info"]
        add(f"expert cost {q}", f"{100 * (e2['expert_slots'] / e1['expert_slots'] - 1):.1f}%")
    add("arena ratio", f"{d['iq3_s-wmma-p1']['machine']['engine_info']['arena_mib'] / d['iq2_xs-wmma-p1']['machine']['engine_info']['arena_mib']:.2f}")
    add("expert drop iq2xs->iq3_s", f"{abs(100 * (d['iq3_s-wmma-p1']['machine']['engine_info']['expert_slots'] / d['iq2_xs-wmma-p1']['machine']['engine_info']['expert_slots'] - 1)):.0f}%")
    add("expert ratio p2", f"{100 * d['iq3_s-wmma-p2']['machine']['engine_info']['expert_slots'] / d['iq2_xs-wmma-p1']['machine']['engine_info']['expert_slots']:.0f}%")
    for s in (1, 2):
        for q in QUANTS:
            a, b = d[f"{q}-wmma-p{s}"]["elapsed_s"], d[f"{q}-plain-p{s}"]["elapsed_s"]
            add(f"wall {q} p{s} on", f"{a:.1f} s")
            add(f"wall {q} p{s} off", f"{b:.1f} s")
            add(f"wall {q} p{s} delta", f"{100 * (a / b - 1):.1f}%")
    walls = [d[a]["elapsed_s"] for a in d]
    add("wall range", f"{min(walls):.1f}-{max(walls):.1f}")
    deltas = [100 * (d[f"{q}-wmma-p{s}"]["elapsed_s"] / d[f"{q}-plain-p{s}"]["elapsed_s"] - 1)
              for q in QUANTS for s in (1, 2)]
    ad = sorted(abs(x) for x in deltas)
    add("wall delta range", f"{ad[0]:.1f}-{ad[-1]:.1f}%")

    spreads = {}
    for k in PROMPTS:
        v = []
        for arm in d:
            reqs = [x["prompt_tps"] for x in d[arm]["results"]["prompts"][k]["requests"]]
            v.append(((max(reqs) - min(reqs)) / statistics.median(reqs) * 100, arm))
        spreads[k] = v
        s = sorted(x[0] for x in v)
        add(f"spread {k}", f"{s[0]:.1f}-{s[-1]:.1f}%")
        add(f"spread {k} median", f"{statistics.median(s):.1f}%")
        add(f"spread {k} worst", f"{s[-1]:.1f}%")
    for arm, lab in (("iq2_xs-plain-p1", "4K"), ("iq3_s-plain-p1", "4K")):
        reqs = [x["prompt_tps"] for x in d[arm]["results"]["prompts"][lab]["requests"]]
        add(f"spread {arm}", f"{(max(reqs) - min(reqs)) / statistics.median(reqs) * 100:.1f}%")
    for arm, k, lab in (("iq3_s-wmma-p2", "4K", "4K"), ("iq3_s-wmma-p2", "16K", "16K"),
                        ("iq3_s-wmma-p1", "16K", "16K"), ("iq2_xs-wmma-p2", "32K", "32K"),
                        ("iq2_xs-wmma-p1", "32K", "32K")):
        reqs = [x["prompt_tps"] for x in d[arm]["results"]["prompts"][k]["requests"]]
        add(f"spread {arm} {lab}", f"{(max(reqs) - min(reqs)) / statistics.median(reqs) * 100:.1f}%")
    w4k = sorted((max(x["prompt_tps"] for x in d[a]["results"]["prompts"]["4K"]["requests"]) -
                  min(x["prompt_tps"] for x in d[a]["results"]["prompts"]["4K"]["requests"])) /
                 statistics.median([x["prompt_tps"] for x in d[a]["results"]["prompts"]["4K"]["requests"]]) * 100
                 for a in d if "-wmma-" in a)
    add("spread 4K wmma range", f"{w4k[0]:.1f}-{w4k[-1]:.1f}%")

    n_suite = n_burst = n_turns = 0
    for arm in d:
        r = d[arm]["results"]
        n_suite += len(r["chat"]["requests"]) + sum(len(r["prompts"][k]["requests"]) for k in PROMPTS) \
                   + sum(len(x) for x in r["agent"]["sessions"])
        n_turns += sum(len(x) - 1 for x in r["agent"]["sessions"])
        if r.get("clients"):
            n_burst += 2 * len(r["clients"]["rounds"])
    add("suite requests", str(n_suite))
    add("burst requests", str(n_burst))
    add("total requests", str(n_suite + n_burst))
    add("agent turns", str(n_turns))
    add("prompt requests", str(sum(len(d[a]["results"]["prompts"][k]["requests"]) for a in d for k in PROMPTS)))
    add("prompt reused sum", str(sum(q["reused_tokens"] for a in d for k in PROMPTS for q in d[a]["results"]["prompts"][k]["requests"])))
    add("failures", str(sum(len(d[a]["results"]["failures"]) for a in d)))
    add("skipped", str(sum(len(d[a]["results"]["skipped"]) for a in d)))
    ag = [d[a]["results"]["agent"] for a in d]
    add("agent hit range", f"{min(x['hit_pct']['min'] for x in ag):.1f}-{max(x['hit_pct']['max'] for x in ag):.1f}")
    add("agent reread range", f"{min(x['reread_tokens']['min'] for x in ag)}-{max(x['reread_tokens']['max'] for x in ag)}")
    add("agent new range", f"{min(x['new_tokens']['min'] for x in ag):,}-{max(x['new_tokens']['max'] for x in ag):,}")
    add("agent last range", f"{min(x['last_turn_prompt_tokens']['min'] for x in ag):,}-{max(x['last_turn_prompt_tokens']['max'] for x in ag):,}")
    add("agent first ttft range", f"{min(x['first_turn_ttft_s']['min'] for x in ag):.1f}-{max(x['first_turn_ttft_s']['max'] for x in ag):.1f}")
    cp = [x["prompt_tokens"] for a in d for x in d[a]["results"]["chat"]["requests"]]
    add("chat prompt tokens", f"{min(cp)}-{max(cp)}")
    add("chat generated", str(d["iq2_xs-wmma-p1"]["results"]["chat"]["generated_tokens"]["median"]))
    gen = [x["generated_tokens"] for a in d for s in d[a]["results"]["agent"]["sessions"] for x in s]
    add("agent generated", f"{min(gen)}-{max(gen)}")
    for k in PROMPTS:
        add(f"tokens {k}", f"{d['iq2_xs-wmma-p1']['results']['prompts'][k]['prompt_tokens']['median']:,}")
    w16 = sorted(md(d[a]["results"], "p", "16K") for a in ARM_NAMES if "-wmma-" in a)
    p16 = sorted(md(d[a]["results"], "p", "16K") for a in ARM_NAMES if "-plain-" in a)
    assert p16[-1] < w16[0], f"the 16K clusters overlap: plain max {p16[-1]}, wmma min {w16[0]}"
    pr = {(L, s): 100 * (md(d[f"{q}-wmma-p{s}"]["results"], "p", L) /
                         md(d[f"{q}-plain-p{s}"]["results"], "p", L) - 1)
          for q in QUANTS for s in (1, 2) for L in ("4K", "16K", "32K")}
    for lab, keys in [("16K pairs", [(L, s) for L in ("16K", "32K") for s in (1, 2)]),
                      ("16K 1-slot", [("16K", 1)]), ("16K 2-slot", [("16K", 2)]),
                      ("32K pairs", [("32K", 1), ("32K", 2)]),
                      ("4K pairs", [("4K", 1), ("4K", 2)]),
                      ("prefill pairs", list(pr))]:
        vals = sorted(pr[k] for k in keys)
        add(f"{lab} min", f"{vals[0]:+.1f}%")
        add(f"{lab} max", f"{vals[-1]:+.1f}%")
    add("16K clusters wmma", f"{w16[0]:,.0f}-{w16[-1]:,.0f}")
    add("16K clusters plain", f"{p16[0]:,.0f}-{p16[-1]:,.0f}")
    lo = min(md(d[a]["results"], "p", "16K") for a in d if "-wmma-" in a)
    hi = max(md(d[a]["results"], "p", "16K") for a in d if "-wmma-" in a)
    add("16K wmma check", f"{lo:,.0f}-{hi:,.0f}")
    lo, hi = min(md(d[a]["results"], "p", "16K") for a in d if "-plain-" in a), max(md(d[a]["results"], "p", "16K") for a in d if "-plain-" in a)
    add("16K plain check", f"{lo:,.0f}-{hi:,.0f}")
    lo = min(md(d[a]["results"], "p", "4K") for a in d)
    hi = max(md(d[a]["results"], "p", "4K") for a in d)
    add("4K range", f"{f1(lo)} to {f1(hi)}")
    add("4K range pct", f"{100 * (hi / lo - 1):.0f}%")
    lo32 = min(md(d[a]["results"], "t", "32K") for a in d if "-plain-" in a)
    hi32 = max(md(d[a]["results"], "t", "32K") for a in d if "-plain-" in a)
    add("32K ttft plain", f"{lo32:.1f}-{hi32:.1f}")
    lo32 = min(md(d[a]["results"], "t", "32K") for a in d if "-wmma-" in a)
    hi32 = max(md(d[a]["results"], "t", "32K") for a in d if "-wmma-" in a)
    add("32K ttft wmma", f"{lo32:.1f}-{hi32:.1f}")
    mc = d["iq2_xs-wmma-p1"]["machine"]
    for k, s in (("gpu vram", f"{mc['gpu_vram_mib']:,.0f} MiB"), ("ram", f"{mc['ram_gib']} GiB"),
                 ("threads", str(mc["cpu_threads"])), ("cores", str(mc["cpu_cores"])),
                 ("os", mc["os"]), ("python", mc["python"]), ("strata", mc["strata_version"]),
                 ("commit", mc["strata_commit"]), ("engine", mc["engine_version"]),
                 ("cpu", mc["cpu"]), ("context", f"{mc['context']:,}")):
        add(f"machine {k}", s)
    ei = mc["engine_info"]
    for k, s in (("kv", ei["kv"]), ("kv_resident", f"{ei['kv_resident']:,}"), ("spec", str(ei["spec"])),
                 ("mtp_max", str(ei["mtp_max"])), ("lookup", str(ei["lookup"])),
                 ("pool_workers", str(ei["pool_workers"])), ("prefill_cap", f"{ei['prefill_cap']:,}"),
                 ("conv_slots", str(ei["conversation_cache_slots"])), ("tail", str(ei["tail_role_token"])),
                 ("prefill_stages", str(ei["prefill_stages"])), ("prefill_pipe", str(ei["prefill_pipe"])),
                 ("stream_all_min", f"{ei['stream_all_min']:,}"), ("cvec", str(ei["cvec"])),
                 ("expert_slots_primary", f"{ei['expert_slots_primary']:,}")):
        add(f"engine {k}", s)
    if "batch_slots" in ei:
        add(f"{arm} batch_slots", str(ei["batch_slots"]))
        add(f"{arm} slot_cache", str(ei["slot_cache"]))
        add(f"{arm} batch_groups", str(ei["batch_groups"]))

    # the README claims the machine block is identical in all 12 arms and the engine reports the
    # same numbers except where a row says otherwise; verify that, and state the hardware numbers.
    m = [d[a]["machine"] for a in ARM_NAMES]
    HW_EXCEPT = ("engine_info", "model", "parallel_slots", "quant")
    hw = [json.dumps({k: v for k, v in x.items() if k not in HW_EXCEPT}, sort_keys=True) for x in m]
    assert len(set(hw)) == 1, "machine block is not identical across the 12 arms (minus " + str(HW_EXCEPT) + ")"
    ps = {a: d[a]["machine"]["parallel_slots"] for a in ARM_NAMES}
    assert {ps[a] for a in ARM_NAMES if a.endswith("-p2")} == {2}
    assert {ps[a] for a in ARM_NAMES if a.endswith("-p1")} == {1}
    assert {d[a]["machine"]["model"] for a in ARM_NAMES if a.startswith("iq2_xs")} == {"swift-1.5-iq2_xs"}
    assert {d[a]["machine"]["quant"] for a in ARM_NAMES} == {None}
    assert {d[a]["machine"]["model"] for a in ARM_NAMES} == {f"swift-1.5-{q}" for q in QUANTS}
    add("parallel_slots", "1 in the six 1-slot arms, 2 in the six 2-slot arms")
    for q in QUANTS:
        add(f"machine model {q}", f"swift-1.5-{q}")
    add("machine quant null", "`quant` is null")
    m0 = m[0]
    for k, s in (("gpu", ", ".join(m0["gpu"])), ("gpu_vram_mib", f"{m0['gpu_vram_mib']:,.0f} MiB"),
                 ("cpu", m0["cpu"]), ("cores", str(m0["cpu_cores"])), ("threads", str(m0["cpu_threads"])),
                 ("ram_gib", f"{m0['ram_gib']:.1f} GiB"), ("os", m0["os"]), ("python", m0["python"]),
                 ("strata_version", m0["strata_version"]), ("strata_commit", m0["strata_commit"]),
                 ("engine_version", m0["engine_version"]),
                 ("context", f"{m0['context']:,}"), ("gpu_driver", "null"), ("cuda", "null")):
        add(f"hardware {k}", s)
    VARIES = {"arena_mib", "expert_slots", "expert_slots_primary", "expert_cache_mib",
              "expert_cache_primary_mib", "prefill_cap", "batch_slots", "slot_cache",
              "batch_groups", "model", "model_name", "vram_free_mib", "pool_workers", "spec_min_p"}
    ei0 = m0["engine_info"]
    for k, v in ei0.items():
        if k in VARIES:
            continue
        vals = {json.dumps(x["engine_info"].get(k)) for x in m}
        assert len(vals) == 1, f"engine_info.{k} differs across arms: {sorted(vals)}"
    print(f"engine_info: {len(ei0) - len(VARIES)} fields identical in all 12 arms; "
          f"{len(VARIES)} keys are allowed to vary (arena, expert slots/MiB, prefill_cap, batch keys, model)")
    ei2 = d["iq2_xs-wmma-p2"]["machine"]["engine_info"]
    for k in ("batch_slots", "slot_cache", "batch_groups"):
        for a in ARM_NAMES:
            if a.endswith("-p2"):
                assert d[a]["machine"]["engine_info"][k] == ei2[k], f"{a}.{k} differs"
            else:
                assert d[a]["machine"]["engine_info"].get(k) is None, f"{a}.{k} present in a 1-slot arm"
    for k, s in (("batch_slots", str(ei2["batch_slots"])), ("slot_cache", str(ei2["slot_cache"])),
                 ("batch_groups", str(ei2["batch_groups"]))):
        add(f"engine {k}", s)
    add("1-slot batch keys", "the keys are absent in the six 1-slot arms")
    # per-quant engine answers that the README lists as pairs
    pw = {q: {d[f"{q}-wmma-p1"]["machine"]["engine_info"]["pool_workers"],
              d[f"{q}-plain-p2"]["machine"]["engine_info"]["pool_workers"]} for q in QUANTS}
    sp = {q: {d[f"{q}-wmma-p1"]["machine"]["engine_info"]["spec_min_p"],
              d[f"{q}-plain-p2"]["machine"]["engine_info"]["spec_min_p"]} for q in QUANTS}
    assert all(len(v) == 1 for v in pw.values()) and all(len(v) == 1 for v in sp.values()), \
        "pool_workers/spec_min_p are not constant inside a quant"
    add("pool_workers per quant", f"{pw['iq2_xs'].pop()} on IQ2_XS and {pw['iq3_xxs'].pop()} on "
        f"IQ3_XXS/IQ3_S")
    add("spec_min_p per quant", f"{sp['iq2_xs'].pop()} on IQ2_XS and {sp['iq3_xxs'].pop()} on the other two")
    for c in sorted({d[a]["machine"]["engine_info"]["prefill_cap"] for a in ARM_NAMES}):
        add(f"prefill_cap {c:,}", f"{c:,}")
    for a in ARM_NAMES:
        cap = d[a]["machine"]["engine_info"]["prefill_cap"]
        if cap != 16384:
            add(f"{a} prefill_cap", f"{cap:,}")
    for q in QUANTS:
        for a in (f"{q}-wmma-p1", f"{q}-wmma-p2", f"{q}-plain-p1", f"{q}-plain-p2"):
            e = d[a]["machine"]["engine_info"]
            assert e["expert_cache_primary_mib"] == e["expert_cache_mib"], f"{a} primary MiB differs"
            assert e["expert_slots_primary"] == e["expert_slots"], f"{a} primary slots differ"

    def acc(reqs):
        o = sum(x["drafts_offered"] for x in reqs)
        a = sum(x["drafts_accepted"] for x in reqs)
        return 100 * a / o
    for what, pick in (("chat", lambda r: r["chat"]["requests"]),
                       ("agent", lambda r: [x for sess in r["agent"]["sessions"] for x in sess]),
                       ("prompt", lambda r: [x for k in PROMPTS for x in r["prompts"][k]["requests"]])):
        for q in QUANTS:
            v = sorted(acc(pick(d[f"{q}-wmma-p{s}"]["results"])) for s in (1, 2)) + \
                sorted(acc(pick(d[f"{q}-plain-p{s}"]["results"])) for s in (1, 2))
            add(f"accept {q} {what}", f"{min(v):.1f}-{max(v):.1f}%")

    for label, s in out:
        if s not in text:
            miss.append((label, s))
    print(f"{len(out)} numbers recomputed from {data_dir}/, {len(out) - len(miss)} stated in {readme}")
    for label, s in miss:
        print(f"  MISSING: {label}: {s}")
    bad, ntab = check_tables(d, Path(readme).read_text())
    print(f"{ntab} tables checked cell by cell, {len(bad)} cell mismatches")
    for b in bad:
        print("  CELL: " + b)
    return 1 if (miss or bad) else 0




# ---------------------------------------------------------------- table cells
#
# The number check above is a substring test: a value stated with the wrong digits can be found
# somewhere else in the file. This part checks the tables cell by cell, in position, against
# recomputation. Every table cell in README.md is in one of these specs, so a cell that is stale,
# rounded from a rounded number, or copied from an older draft is reported.

SEP = re.compile(r"^\|(\s*:?-+:?\s*\|)+\s*$")


def cells(line):
    return [c.strip() for c in line.strip().strip("|").split("|")]


def norm(s):
    s = re.sub(r"\([^)]*\)", "", s)
    return s.replace("*", "").replace(" ", "").strip()


def md_tables(text):
    out, lines, i = [], text.split("\n"), 0
    while i < len(lines):
        if lines[i].startswith("|") and i + 1 < len(lines) and SEP.match(lines[i + 1].strip()):
            head, rows, j = cells(lines[i]), [], i + 2
            while j < len(lines) and lines[j].startswith("|"):
                rows.append(cells(lines[j]))
                j += 1
            out.append((tuple(head), rows))
            i = j
        else:
            i += 1
    return out


def pct(a, b=1):
    return f"{100 * (a / b - 1):+.1f}%"


def gp(vals):
    return f"{100 * (math.exp(sum(math.log(v) for v in vals) / len(vals)) - 1):+.1f}%"


ORDER = [("wmma", 1), ("wmma", 2), ("plain", 2), ("plain", 1)]
ARM_NAMES = [f"{q}-{w}-p{s}" for q in QUANTS for w, s in ORDER]


def stat(v, nd=1):
    f = (lambda x: f"{x:,.{nd}f}") if nd else (lambda x: f"{x:.2f}")
    return f"{f(v['median'])} [{f(v['min'])}-{f(v['max'])}]"


def pair_specs(d):
    """expected rows for the comparison tables: name -> (label, [cells])"""
    g, gt = {k: [] for k in ("4K", "16K", "32K", "chat", "agent")}, {}
    wrows, trows = [], []
    for s in (1, 2):
        for q in QUANTS:
            a, b = f"{q}-wmma-p{s}", f"{q}-plain-p{s}"
            ra, rb = d[a]["results"], d[b]["results"]
            v = {k: md(d[a]['results'], "p", k) / md(d[b]['results'], "p", k) for k in PROMPTS}
            v["chat"] = md(d[a]['results'], "chat", "decode_tps") / md(d[b]['results'], "chat", "decode_tps")
            v["agent"] = md(d[a]['results'], "agent", "turn_decode_tps") / md(d[b]['results'], "agent", "turn_decode_tps")
            for k in g:
                g[k].append(v[k])
            wrows.append((f"{q}, {s}", [pct(v[k], 1) for k in ("4K", "16K", "32K")]
                          + [gp([v[k] for k in PROMPTS]), pct(v["chat"], 1), pct(v["agent"], 1),
                             gp([v["chat"], v["agent"]])]))
            t = {"chat": md(d[a]['results'], "chat", "ttft_s") / md(d[b]['results'], "chat", "ttft_s"),
                 "agent": md(d[a]['results'], "agent", "turn_ttft_s") / md(d[b]['results'], "agent", "turn_ttft_s")}
            for k in PROMPTS:
                t[k] = md(d[a]['results'], "t", k) / md(d[b]['results'], "t", k)
            for k in t:
                gt.setdefault(k, []).append(t[k])
            trows.append((f"{q}, {s}", [pct(t[k], 1) for k in ("chat", "4K", "16K", "32K", "agent")]))
    wrows.append(("geomean, six pairs", [gp(g[k]) for k in ("4K", "16K", "32K")]
                  + ["-", gp(g["chat"]), gp(g["agent"]), "-"]))
    trows.append(("geomean, six pairs", [gp(gt[k]) for k in ("chat", "4K", "16K", "32K", "agent")]))

    prows, pc, pa, pp, pt = [], [], [], [], []
    for q in QUANTS:
        ra, rb = d[f"{q}-wmma-p2"]["results"], d[f"{q}-wmma-p1"]["results"]
        ch = md(d[f'{q}-wmma-p2']['results'], "chat", "decode_tps") / md(d[f'{q}-wmma-p1']['results'], "chat", "decode_tps")
        ag = md(d[f'{q}-wmma-p2']['results'], "agent", "turn_decode_tps") / md(d[f'{q}-wmma-p1']['results'], "agent", "turn_decode_tps")
        t = md(d[f'{q}-wmma-p2']['results'], "chat", "ttft_s") / md(d[f'{q}-wmma-p1']['results'], "chat", "ttft_s")
        att = md(d[f'{q}-wmma-p2']['results'], "agent", "turn_ttft_s") / md(d[f'{q}-wmma-p1']['results'], "agent", "turn_ttft_s")
        pr = {k: md(d[f'{q}-wmma-p2']['results'], "p", k) / md(d[f'{q}-wmma-p1']['results'], "p", k) for k in PROMPTS}
        pc.append(ch); pa.append(ag); pp += list(pr.values()); pt.append(t)
        prows.append((q, [pct(ch, 1), pct(ag, 1)] + [pct(pr[k], 1) for k in PROMPTS] + [pct(t, 1), pct(att, 1)]))
    prows.append(("geomean", [gp(pc), gp(pa), gp(pp), "-", "-", gp(pt), "-"]))

    brows, shares = [], []
    for q in QUANTS:
        r = d[f"{q}-wmma-p2"]["results"]
        tot = md(d[f'{q}-wmma-p2']['results'], "clients", "total_tps")
        solo = md(d[f'{q}-wmma-p2']['results'], "chat", "decode_tps")
        shares.append(tot / solo)
        c = r["clients"]
        brows.append((q, [f"{tot:,.1f} [{c['total_tps']['min']:.2f}-{c['total_tps']['max']:.2f}]",
                          f"{tot / 2:.1f}", f"{100 * tot / solo:.1f}%", f"{100 * tot / 2 / solo:.1f}%",
                          f"{c['ttft_p50_s']} s", f"{c['ttft_p95_s']} s"]))
    qrows = {}
    for slots, key in ((1, "q1"), (2, "q2")):
        rows = [("iq2_xs", ["-"] * (9 if slots == 1 else 10))]
        for q in QUANTS[1:]:
            ra, rb = f"{q}-wmma-p{slots}", f"iq2_xs-wmma-p{slots}"
            ch = md(d[ra]['results'], "chat", "decode_tps") / md(d[rb]['results'], "chat", "decode_tps")
            ag = md(d[ra]['results'], "agent", "turn_decode_tps") / md(d[rb]['results'], "agent", "turn_decode_tps")
            row = [pct(ch, 1), pct(ag, 1), gp([ch, ag])]
            if slots == 2:
                row.append(pct(md(d[ra]['results'], "clients", "total_tps"), md(d[rb]['results'], "clients", "total_tps")))
            row += [pct(md(d[ra]['results'], "p", k), md(d[rb]['results'], "p", k)) for k in PROMPTS]
            row += [gp([md(d[ra]['results'], "p", k) / md(d[rb]['results'], "p", k) for k in PROMPTS]),
                    pct(md(d[ra]['results'], "chat", "ttft_s"), md(d[rb]['results'], "chat", "ttft_s")),
                    pct(md(d[ra]['results'], "t", "32K"), md(d[rb]['results'], "t", "32K"))]
            rows.append((q, row))
        qrows[key] = rows
    return {"wmma": wrows, "wmma_t": trows, "par": prows, "burst": brows, "q1": qrows["q1"],
            "q2": qrows["q2"], "shares": shares}


def table_specs(d, p):
    """header tuple -> expected rows, plus the field/value tables handled separately"""
    S = {}
    S[("arm", "chat decode", "4K prompt", "16K prompt", "32K prompt", "agent decode", "burst (2 clients, total)")] = [
        (a, [stat(d[a]["results"]["chat"]["decode_tps"]),
             stat(d[a]["results"]["prompts"]["4K"]["prompt_tps"]),
             stat(d[a]["results"]["prompts"]["16K"]["prompt_tps"]),
             stat(d[a]["results"]["prompts"]["32K"]["prompt_tps"]),
             stat(d[a]["results"]["agent"]["turn_decode_tps"]),
             stat(d[a]["results"]["clients"]["total_tps"], 0) if d[a]["results"].get("clients") else "n/a"])
        for a in ARM_NAMES]
    S[("arm", "chat", "4K", "16K", "32K", "agent turn")] = [
        (a, [stat(d[a]["results"]["chat"]["ttft_s"], 0),
             stat(d[a]["results"]["prompts"]["4K"]["ttft_s"], 0),
             stat(d[a]["results"]["prompts"]["16K"]["ttft_s"], 0),
             stat(d[a]["results"]["prompts"]["32K"]["ttft_s"], 0),
             stat(d[a]["results"]["agent"]["turn_ttft_s"], 0)]) for a in ARM_NAMES]
    S[("quant, slots", "4K prompt", "16K prompt", "32K prompt", "geomean prompt", "chat decode", "agent decode", "geomean decode")] = p["wmma"]
    S[("pair group", "chat TTFT", "4K TTFT", "16K TTFT", "32K TTFT", "agent TTFT")] = p["wmma_t"]
    S[("quant", "chat decode", "agent decode", "4K prompt", "16K prompt", "32K prompt", "chat TTFT", "agent TTFT")] = p["par"]
    S[("quant (WMMA on, 2 slots)", "burst total", "per client", "share of solo (total)", "share of solo (per client)", "p50 TTFT", "p95 TTFT")] = p["burst"]
    S[("quant", "chat decode", "agent decode", "geomean decode", "4K prompt", "16K prompt", "32K prompt", "geomean prompt", "chat TTFT", "32K TTFT")] = p["q1"]
    S[("quant", "chat decode", "agent decode", "geomean decode", "burst total", "4K prompt", "16K prompt", "32K prompt", "geomean prompt", "chat TTFT", "32K TTFT")] = p["q2"]
    ag = [d[a]["results"]["agent"] for a in ARM_NAMES]
    def acc(arm, reqs):
        o = sum(x["drafts_offered"] for x in reqs)
        a = sum(x["drafts_accepted"] for x in reqs)
        return f"{100 * a / o:.1f}%"
    S[("arm", "chat accept", "agent accept", "prompt accept")] = [
        (a, [acc(a, d[a]["results"]["chat"]["requests"]),
             acc(a, [x for sess in d[a]["results"]["agent"]["sessions"] for x in sess]),
             acc(a, [x for k in PROMPTS for x in d[a]["results"]["prompts"][k]["requests"]])])
        for a in ARM_NAMES]
    turns = [x for a in ARM_NAMES for sess in d[a]["results"]["agent"]["sessions"] for x in sess]
    r0 = d[ARM_NAMES[0]]["results"]
    cpt = [x["prompt_tokens"] for a in ARM_NAMES for x in d[a]["results"]["chat"]["requests"]]
    S[("test", "prompt tokens", "reused", "generated", "requests per arm")] = [
        ("chat (4 prompts, warm)", [f"{min(cpt)}-{max(cpt)}", None,
                                    f"{r0['chat']['generated_tokens']['median']:.0f}",
                                    str(len(r0["chat"]["requests"]))]),
        ("4K / 16K / 32K prompt", [" / ".join(f"{r0['prompts'][k]['prompt_tokens']['median']:,.0f}" for k in PROMPTS),
                                   None, "0", "3 each"]),
        ("agent session, 6 turns", [f"{min(x['prompt_tokens'] for x in r0['agent']['sessions'][0])} (turn 1) -> "
                                    f"{min(x['last_turn_prompt_tokens']['min'] for x in [d[a]['results']['agent'] for a in ARM_NAMES]):,}-"
                                    f"{max(x['last_turn_prompt_tokens']['max'] for x in [d[a]['results']['agent'] for a in ARM_NAMES]):,} (turn 6)",
                                    None, "4-64 per turn",
                                    f"{len(r0['agent']['sessions'])} sessions x {len(r0['agent']['sessions'][0])}"]),
        ("2-client burst, 3 rounds x 2 clients", [None, None, "128 each", None]),
    ]
    S[("field", "range across the 12 arms")] = [
        ("cache hit rate", [f"{min(x['hit_pct']['min'] for x in ag):.1f}-{max(x['hit_pct']['max'] for x in ag):.1f}%"]),
        ("re-read tokens per session", [f"{min(x['reread_tokens']['min'] for x in ag)}-{max(x['reread_tokens']['max'] for x in ag)}"]),
        ("new prompt tokens per session", [f"{min(x['new_tokens']['min'] for x in ag):,}-{max(x['new_tokens']['max'] for x in ag):,}"]),
        ("last-turn prompt tokens", [f"{min(x['last_turn_prompt_tokens']['min'] for x in ag):,}-{max(x['last_turn_prompt_tokens']['max'] for x in ag):,}"]),
        ("first-turn TTFT", [f"{min(x['first_turn_ttft_s']['min'] for x in ag):.1f}-{max(x['first_turn_ttft_s']['max'] for x in ag):.1f} s"]),
        ("generated tokens per turn", [f"{min(x['generated_tokens'] for x in turns)}-{max(x['generated_tokens'] for x in turns)}"]),
    ]
    S[("arm", "expert slots", "MiB", "GiB")] = [
        (f"{q}, {s} slot" + ("s" if s == 2 else ""),
         [f"{d[f'{q}-wmma-p{s}']['machine']['engine_info']['expert_slots']:,}",
          f"{d[f'{q}-wmma-p{s}']['machine']['engine_info']['expert_cache_mib']:,}",
          f"{d[f'{q}-wmma-p{s}']['machine']['engine_info']['expert_cache_mib'] / 1024:.1f}"])
        for q in QUANTS for s in (1, 2)]
    S[("quant", "1 slot, WMMA on", "1 slot, WMMA off", "delta", "2 slots, WMMA on", "2 slots, WMMA off", "delta")] = [
        (q, [f"{d[f'{q}-wmma-p1']['elapsed_s']:.1f} s", f"{d[f'{q}-plain-p1']['elapsed_s']:.1f} s",
             pct(d[f'{q}-wmma-p1']['elapsed_s'], d[f'{q}-plain-p1']['elapsed_s']),
             f"{d[f'{q}-wmma-p2']['elapsed_s']:.1f} s", f"{d[f'{q}-plain-p2']['elapsed_s']:.1f} s",
             pct(d[f'{q}-wmma-p2']['elapsed_s'], d[f'{q}-plain-p2']['elapsed_s'])]) for q in QUANTS]
    return S


FIELD_VALUE = {
    "machine.gpu": ['["AMD Radeon"]', "16,304 MiB"],
    "machine.cpu": ["AMD Ryzen 5 3600 6-Core Processor", "12", "86.3 GiB"],
    "machine.os": ["Linux 6.12.111+deb13-amd64", "3.13.5"],
    "machine.strata_version": ["0.1.45", "477ac13c"],
    "machine.engine_version": ["0.1.45"],
    "machine.context": ["131,072"],
    "kv": ["int8", "32,768", "131,072"],
    "spec": ["6", "4", "3"],
    "pcie_frac": ["1.00", "11", "0.70"],
    "prefill_cap": ["16,384", "15,104"],
    "cvec": ["0"],
    "conversation_cache_slots": ["4", "2,560"],
    "tail_role_token": ["-1"],
    "vram_elastic": ["0"],
    "arena_mib": ["33,812", "40,925", "47,962"],
    "stream_all_min": ["1,024"],
}


def check_tables(d, text):
    bad = []
    p = pair_specs(d)
    specs = table_specs(d, p)
    seen = set()
    for head, rows in md_tables(text):
        if head in specs:
            seen.add(head)
            exp = {norm(l): c for l, c in specs[head]}
            for row in rows:
                lab = norm(row[0])
                if lab not in exp:
                    bad.append(f"table {head[0]!r}: row {row[0]!r} is not derivable from data/")
                    continue
                want = exp[lab]
                got = [norm(c) for c in row[1:]]
                for i, w in enumerate(want):
                    if w is None:
                        continue
                    g = got[i] if i < len(got) else "<missing cell>"
                    if g != norm(w):
                        col = head[i + 1] if i + 1 < len(head) else f"col{i + 1}"
                        bad.append(f"table {head[0]!r} row {row[0]!r} column {col!r}: README {g!r}, data {w!r}")
                if len(got) > len(want):
                    bad.append(f"table {head[0]!r} row {row[0]!r}: {len(got) - len(want)} extra cells")
            missing = set(exp) - {norm(r[0]) for r in rows}
            for m in missing:
                bad.append(f"table {head[0]!r}: row {m!r} missing from README")
        elif head and head[0] == "field":
            for row in rows:
                toks = set(re.split(r"[^A-Za-z0-9_]+", row[0].replace("`", "")))
                for k, vals in FIELD_VALUE.items():
                    if k.replace("machine.", "") in toks:
                        for v in vals:
                            if v not in " ".join(row):
                                bad.append(f"field/value row {row[0]!r}: {v!r} not in the row (data says {row})")
    for head in specs:
        if head not in seen:
            bad.append(f"README has no table with header {head}")
    return bad, len(seen)


if __name__ == "__main__":
    sys.exit(main())
