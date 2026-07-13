#!/usr/bin/env python3
"""QButler MOT-chain validation: fetch an ARTIQ RID's ndscan datasets from the
live REST dump and plot/judge. Reusable across the validation ladder.

Usage:
  qbval_plot.py <RID> [--channel excitation_fraction] [--title "..."] [--cache FILE]
"""
import sys, json, os, argparse, urllib.request

API = "https://artiq.stronlab.net/api/datasets"
SCRATCH = os.path.dirname(os.path.abspath(__file__))


def fetch(cache=None, force=False):
    if cache and os.path.exists(cache) and not force:
        return json.load(open(cache))
    with urllib.request.urlopen(API, timeout=90) as r:
        d = json.load(r)
    if cache:
        json.dump(d, open(cache, "w"))
    return d


def val(d, key, default=None):
    v = d.get(key)
    return v[1] if v is not None else default


def load_rid(d, rid):
    p = f"ndscan.rid_{rid}."
    out = {"completed": val(d, p + "completed"),
           "fragment_fqn": val(d, p + "fragment_fqn")}
    axraw = val(d, p + "axes")
    out["axes"] = json.loads(axraw) if axraw else []
    ann = val(d, p + "annotations")
    out["annotations"] = json.loads(ann) if ann else []
    out["axis_points"] = []
    for i in range(len(out["axes"])):
        out["axis_points"].append(val(d, p + f"points.axis_{i}"))
    out["channels"] = {k.split("points.channel_")[1]: v[1]
                       for k, v in d.items() if k.startswith(p + "points.channel_")}
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("rid", type=int)
    ap.add_argument("--channel", default="excitation_fraction")
    ap.add_argument("--title", default="")
    ap.add_argument("--cache", default=None)
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()

    d = fetch(args.cache, args.force)
    r = load_rid(d, args.rid)
    if not r["axes"]:
        print(f"RID {args.rid}: no ndscan axes found in live dump (evicted/archived?)")
        print("channels present:", list(r["channels"].keys())[:20])
        sys.exit(2)

    import numpy as np
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    ax0 = r["axes"][0]["param"]
    scale = ax0["spec"].get("scale", 1.0) or 1.0
    unit = ax0["spec"].get("unit", "")
    fqn = ax0["fqn"]
    x = np.array(r["axis_points"][0], float) / scale
    ch = r["channels"].get(args.channel)
    an = r["channels"].get("atom_number")
    if ch is None:
        print("channel not found. available:", list(r["channels"].keys()))
        sys.exit(2)
    y = np.array(ch, float)

    fig, axes = plt.subplots(2, 1, figsize=(9, 8), sharex=True)
    axes[0].scatter(x, y, s=14, alpha=0.5, color="#1f77b4")
    nb = 40
    bins = np.linspace(x.min(), x.max(), nb + 1)
    idx = np.digitize(x, bins)
    bx, by = [], []
    for b in range(1, nb + 1):
        m = idx == b
        if m.sum() >= 2:
            bx.append(x[m].mean()); by.append(np.median(y[m]))
    axes[0].plot(bx, by, "-o", color="#d62728", ms=4, lw=1.5, label="binned median")
    axes[0].set_ylabel(args.channel)
    axes[0].legend(loc="best", fontsize=8)
    axes[0].grid(alpha=0.3)
    ttl = args.title or f"RID {args.rid}  {fqn.split('.')[-1]}"
    axes[0].set_title(ttl + f"\ncompleted={r['completed']}  N={len(x)}", fontsize=10)

    if an is not None:
        axes[1].scatter(x, np.array(an, float), s=12, alpha=0.4, color="#2ca02c")
        axes[1].axhline(10000, color="gray", ls="--", lw=0.8, label="10k noise-floor line")
        axes[1].set_ylabel("atom_number")
        axes[1].legend(loc="best", fontsize=8)
        axes[1].grid(alpha=0.3)
    axes[1].set_xlabel(f"{fqn.split('.')[-1]}  [{unit}]")

    out = os.path.join(SCRATCH, "plots", f"rid{args.rid}_{args.channel}.png")
    fig.tight_layout(); fig.savefig(out, dpi=110)
    print("wrote", out)

    print(f"\n=== JUDGE RID {args.rid} ===")
    print(f"fragment: {r['fragment_fqn']}")
    print(f"completed: {r['completed']}   N points: {len(x)}")
    print(f"axis: {fqn}  span [{x.min():.4f}, {x.max():.4f}] {unit}")
    print(f"{args.channel}: median={np.median(y):.4f} min={y.min():.4f} max={y.max():.4f}")
    if an is not None:
        anv = np.array(an, float)
        print(f"atom_number: median={np.median(anv):.0f} max={anv.max():.0f} "
              f"frac>10k={np.mean(anv > 10000):.2f}")
    print("annotations:", r["annotations"])


if __name__ == "__main__":
    main()
