#!/usr/bin/env python3
"""Render + judge the QButler calibration DAG from live datasets.

Reads calibrations.dag / calibrations.status / calibrations.optimizer via the
ARTIQ REST /values endpoint (targeted, no 15MB dump) and produces:
  - a DAG node/edge figure coloured by status
  - a status table (node, state, data, age, timeout, fresh?)
  - per-node optimizer sweep plots (param value vs metric, optimum marked)

Status Flag (qbutler calibration.py:57): OK=0 BAD_EXPIRED=1 BAD_DEPS=2 BAD_DATA=4 INVALID_DATA=8
Use --payload FILE to render a saved/synthetic json payload instead of the live API (unit test).
"""
import sys, json, os, argparse, urllib.request, time

API = "https://artiq.stronlab.net/api"
D = os.path.dirname(os.path.abspath(__file__))
STATUS_NAMES = {0: "OK"}
FLAGS = {1: "EXPIRED", 2: "BAD_DEPS", 4: "BAD_DATA", 8: "INVALID_DATA"}


def status_str(s):
    if s == 0:
        return "OK"
    parts = [n for b, n in FLAGS.items() if s & b]
    return "|".join(parts) or f"?{s}"


def status_color(s):
    if s == 0:
        return "#2ca02c"          # green
    if s & 1 and not (s & 6):
        return "#ff7f0e"          # orange = only expired
    if s & 6 or s & 8:
        return "#d62728"          # red = bad data/deps
    return "#7f7f7f"


def fetch_values(names):
    q = ",".join(names)
    url = f"{API}/datasets/values?names={urllib.parse.quote(q)}"
    with urllib.request.urlopen(url, timeout=30) as r:
        d = json.load(r)
    return {k: v[1] for k, v in d.items()}


def render(dag, status, optim, tag=""):
    import numpy as np, matplotlib
    matplotlib.use("Agg"); import matplotlib.pyplot as plt

    # --- DAG figure ---
    nodes = dag.get("nodes", []) if dag else []
    edges = dag.get("edges", []) if dag else []
    # simple layered layout: depth = longest path from a root
    dep = {n: [] for n in nodes}
    for parent, d_ in edges:            # edge = [parent, dependency]
        dep.setdefault(parent, []).append(d_)
        dep.setdefault(d_, [])
    def depth(n, seen=None):
        seen = seen or set()
        if n in seen or not dep.get(n):
            return 0
        return 1 + max((depth(c, seen | {n}) for c in dep[n]), default=-1)
    depths = {n: depth(n) for n in dep}
    maxd = max(depths.values(), default=0)
    layers = {}
    for n, dd in depths.items():
        layers.setdefault(dd, []).append(n)
    pos = {}
    for dd, ns in layers.items():
        for i, n in enumerate(sorted(ns)):
            pos[n] = (maxd - dd, -i)   # deps on the left, target on the right

    fig, ax = plt.subplots(figsize=(10, 4))
    for parent, d_ in edges:
        if parent in pos and d_ in pos:
            x0, y0 = pos[d_]; x1, y1 = pos[parent]
            ax.annotate("", xy=(x1, y1), xytext=(x0, y0),
                        arrowprops=dict(arrowstyle="->", color="#555", lw=1.3))
    for n, (x, y) in pos.items():
        s = status.get(n, {}).get("status") if status else None
        col = status_color(s) if s is not None else "#cccccc"
        ax.scatter([x], [y], s=2600, c=col, edgecolors="k", zorder=3)
        lbl = n
        if status and n in status:
            e = status[n]
            age = time.time() - e.get("last_check", 0) if e.get("last_check") else None
            lbl += f"\n{status_str(e.get('status'))}"
            if e.get("data") is not None:
                lbl += f"\ndata={e['data']:.3g}"
            if age is not None:
                lbl += f"\nage={age/60:.0f}m/{e.get('timeout',0)/60:.0f}m"
        ax.text(x, y, lbl, ha="center", va="center", fontsize=7, zorder=4)
    ax.set_title(f"calibrations.dag  {tag}\n(deps left → target right; green OK / orange expired / red bad)",
                 fontsize=10)
    ax.axis("off")
    out = os.path.join(D, "plots", f"cal_dag{('_'+tag) if tag else ''}.png")
    fig.tight_layout(); fig.savefig(out, dpi=110); plt.close(fig)
    print("wrote", out)

    # --- optimizer sweeps ---
    if optim:
        for name, e in optim.items():
            pts = np.array(e.get("points", []), float)
            data = np.array([np.nan if v is None else v for v in e.get("data", [])], float)
            if pts.size == 0:
                continue
            pn = e.get("param_names", [])
            fig, ax = plt.subplots(figsize=(8, 4.5))
            if pts.shape[1] == 1:
                x = pts[:, 0]
                ax.scatter(x, data, s=30, c="#1f77b4")
                gv = np.isfinite(data)
                if gv.any():
                    bi = np.nanargmax(data)
                    ax.axvline(x[bi], color="#d62728", ls="--",
                               label=f"best {pn[0] if pn else 'p'}={x[bi]:.5g} → {data[bi]:.4g}")
                    ax.legend(fontsize=8)
                ax.set_xlabel(pn[0] if pn else "param 0")
            else:
                sc = ax.scatter(pts[:, 0], pts[:, 1], c=data, cmap="viridis", s=40)
                fig.colorbar(sc, label="metric")
                ax.set_xlabel(pn[0] if pn else "p0"); ax.set_ylabel(pn[1] if len(pn) > 1 else "p1")
            ax.set_ylabel(ax.get_ylabel() or "metric")
            ax.set_title(f"{name} optimizer sweep  ({len(x) if pts.shape[1]==1 else len(pts)} pts)  {tag}",
                         fontsize=10)
            ax.grid(alpha=0.3)
            out = os.path.join(D, "plots", f"cal_optim_{name}{('_'+tag) if tag else ''}.png")
            fig.tight_layout(); fig.savefig(out, dpi=110); plt.close(fig)
            print("wrote", out)

    # --- judge text ---
    print(f"\n=== JUDGE cal DAG {tag} ===")
    print("nodes:", nodes)
    print("edges (parent<-dep):", edges)
    if status:
        print(f"{'node':32} {'state':16} {'data':>10} {'age_min':>8} {'to_min':>7}")
        for n in nodes or status:
            e = status.get(n)
            if not e:
                print(f"{n:32} {'(no status)':16}"); continue
            age = (time.time() - e['last_check'])/60 if e.get('last_check') else float('nan')
            dstr = '' if e.get('data') is None else f"{e['data']:.3g}"
            print(f"{n:32} {status_str(e['status']):16} {dstr:>10} "
                  f"{age:8.1f} {e.get('timeout',0)/60:7.1f}")
    allok = status and all(status.get(n, {}).get("status") == 0 for n in (nodes or status))
    print("ALL-OK:", bool(allok))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--payload", help="json file with keys calibrations.dag/status/optimizer")
    ap.add_argument("--tag", default="")
    args = ap.parse_args()
    global urllib
    import urllib.parse  # noqa
    if args.payload:
        p = json.load(open(args.payload))
        dag = p.get("calibrations.dag"); status = p.get("calibrations.status")
        optim = p.get("calibrations.optimizer")
    else:
        v = fetch_values(["calibrations.dag", "calibrations.status", "calibrations.optimizer"])
        dag = v.get("calibrations.dag"); status = v.get("calibrations.status")
        optim = v.get("calibrations.optimizer")
        if not dag and not status:
            print("No calibrations.* datasets live right now.")
    render(dag, status, optim, args.tag)


if __name__ == "__main__":
    import urllib.parse
    main()
