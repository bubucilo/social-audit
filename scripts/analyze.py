#!/usr/bin/env python3
"""Deterministic stats for one platform's posts → a markdown fact sheet the audit is written from.

Usage:
  analyze.py --posts RUN/data/posts-tiktok.csv [--pillars RUN/pillars-tiktok.json]
             [--followers 4639] --out RUN/stats-tiktok.md

Everything numeric in the audit must come from this file. No judgment happens here:
paid flags are heuristics and are labelled as such.

Primary metric ("score"):
  tiktok     → views (every format has views)
  instagram  → likes + comments (only reels have plays; L+C is the one cross-format metric)
"""
import argparse, csv, json, statistics as st
from collections import Counter, defaultdict

PAID_LIKE_RATE = 0.02   # views >= 5K but likes/views under 2% → likely paid reach
PAID_MIN_VIEWS = 5000


def n(x):
    return int(x) if x not in (None, "", "None") else None


def med(xs):
    xs = [x for x in xs if x is not None]
    return st.median(xs) if xs else None


def fmt_num(x, pct=False, dp=1):
    if x is None:
        return "–"
    if pct:
        return f"{x:.{dp}f}%"
    if isinstance(x, float) and not x.is_integer():
        return f"{x:,.1f}"
    return f"{int(x):,}"


def table(headers, rows):
    out = ["| " + " | ".join(headers) + " |", "| " + " | ".join("---" for _ in headers) + " |"]
    out += ["| " + " | ".join(str(c) for c in r) + " |" for r in rows]
    return "\n".join(out)


def load(posts_path, pillars_path):
    rows = list(csv.DictReader(open(posts_path)))
    labels = json.load(open(pillars_path)) if pillars_path else {}
    for r in rows:
        for k in ("views", "likes", "comments", "saves", "shares", "duration_s"):
            r[k] = n(r[k])
        r["likes"] = r["likes"] or 0
        r["comments"] = r["comments"] or 0
        r["pillar"] = labels.get(r["id"], "UNLABELED")
        r["lc"] = r["likes"] + r["comments"]
        eng = r["lc"] + (r["saves"] or 0) + (r["shares"] or 0)
        r["er"] = eng / r["views"] * 100 if r["views"] else None
        r["save_rate"] = r["saves"] / r["views"] * 100 if r["views"] and r["saves"] is not None else None
        r["share_rate"] = r["shares"] / r["views"] * 100 if r["views"] and r["shares"] is not None else None
        r["like_rate"] = r["likes"] / r["views"] * 100 if r["views"] else None
    return rows


def flag_paid(rows, followers):
    has_views = [r for r in rows if r["views"]]
    like_med = med([r["likes"] for r in rows if not r["views"]]) or 0
    boost_floor = max(300, 0.3 * followers) if followers else max(300, 10 * like_med)
    for r in rows:
        f = []
        if r["paid_marker"] == "1":
            f.append("marked paid/ad")
        if r["views"] and r["views"] >= PAID_MIN_VIEWS and r["likes"] / r["views"] < PAID_LIKE_RATE:
            f.append(f"likely paid (like rate {r['likes'] / r['views'] * 100:.1f}%)")
        if not r["views"] and r["likes"] >= boost_floor:
            f.append(f"likely boosted ({r['likes']:,} likes vs {'followers ' + format(followers, ',') if followers else 'median ' + str(like_med)})")
        r["flag"] = "; ".join(f)
    return boost_floor, len(has_views)


def quarter(d):
    return f"{d[:4]}-Q{(int(d[5:7]) - 1) // 3 + 1}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--posts", required=True)
    ap.add_argument("--pillars")
    ap.add_argument("--followers", type=int)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()

    rows = load(a.posts, a.pillars)
    platform = rows[0]["platform"]
    score_key, score_name = ("views", "views") if platform == "tiktok" else ("lc", "likes+comments")
    flag_paid(rows, a.followers)
    org = [r for r in rows if not r["flag"]]
    paid = [r for r in rows if r["flag"]]
    base = med([r[score_key] for r in org])
    hit = 2 * base if base else None
    has_saves = any(r["saves"] is not None for r in rows)
    has_shares = any(r["shares"] is not None for r in rows)

    def stats(g):
        sc = [r[score_key] for r in g]
        return {
            "n": len(g),
            "med": med(sc),
            "mean": st.mean([x for x in sc if x is not None]) if g else None,
            "views": med([r["views"] for r in g]),
            "er": med([r["er"] for r in g]),
            "save": med([r["save_rate"] for r in g]),
            "share": med([r["share_rate"] for r in g]),
            "comments": med([r["comments"] for r in g]),
            "hit": sum(1 for r in g if r[score_key] is not None and hit and r[score_key] >= hit) / len(g) * 100 if g else None,
        }

    def srow(label, s, extra=()):
        cells = [label, s["n"], fmt_num(s["med"]), fmt_num(s["mean"])]
        if score_key != "views":
            cells.append(fmt_num(s["views"]))
        cells += [fmt_num(s["er"], pct=True), fmt_num(s["comments"])]
        if has_saves:
            cells.append(fmt_num(s["save"], pct=True, dp=2))
        if has_shares:
            cells.append(fmt_num(s["share"], pct=True, dp=2))
        cells.append(fmt_num(s["hit"], pct=True, dp=0))
        return cells + list(extra)

    H = ["Group", "Posts", f"Median {score_name}", "Mean"]
    if score_key != "views":
        H.append("Median plays (reels)")
    H += ["Median ER", "Median comments"]
    if has_saves:
        H.append("Median save rate")
    if has_shares:
        H.append("Median share rate")
    H.append(f"Hit rate (≥{fmt_num(hit)})")

    L = []
    dates = sorted(r["date"] for r in rows)
    L.append(f"# Stats — {platform} · {rows[0]['url'].split('/')[3] if platform == 'tiktok' else ''}".rstrip(" ·"))
    L.append(f"\n{len(rows)} posts, {dates[0]} → {dates[-1]} · formats {dict(Counter(r['format'] for r in rows))}"
             + (f" · followers {a.followers:,}" if a.followers else ""))
    L.append(f"\nPrimary metric: **{score_name}**. Organic baseline (paid-flagged excluded): median **{fmt_num(base)}**; "
             f"a hit = ≥ 2× median = **{fmt_num(hit)}**. ER = (likes+comments+saves+shares) ÷ views, posts with views only."
             + ("" if has_saves else " Saves not public on this platform.")
             + ("" if has_shares else " Shares not public on this platform."))

    L.append(f"\n## Paid / boosted flags ({len(paid)} posts, excluded from every table below)\n")
    L.append("Heuristic, not proof: ask the owner to confirm. Rules: ≥5K views with like rate <2%; or a non-video post with likes far above the follower base; or marked as an ad.\n")
    if paid:
        L.append(table(["Date", "Format", "Pillar", "Views", "Likes", "Comments", "Flag", "Caption"],
                       [[r["date"], r["format"], r["pillar"], fmt_num(r["views"]), fmt_num(r["likes"]), r["comments"], r["flag"], r["caption"][:70]]
                        for r in sorted(paid, key=lambda r: -(r["views"] or r["likes"]))]))
    else:
        L.append("None.")

    L.append("\n## Trend by quarter (organic)\n")
    q = defaultdict(list)
    for r in org:
        q[quarter(r["date"])].append(r)
    L.append(table(H + ["Top pillars"], [srow(k, stats(v), [", ".join(f"{p} {c}" for p, c in Counter(r['pillar'] for r in v).most_common(3))]) for k, v in sorted(q.items())]))
    L.append("\nPosts per month: " + ", ".join(f"{k} {v}" for k, v in sorted(Counter(r["date"][:7] for r in rows).items())))

    L.append("\n## Format (organic)\n")
    fm = defaultdict(list)
    for r in org:
        fm[r["format"]].append(r)
    L.append(table(H, [srow(k, stats(v)) for k, v in sorted(fm.items(), key=lambda kv: -len(kv[1]))]))

    vids = [r for r in org if r["format"] in ("video", "reel") and r["duration_s"]]
    if vids:
        L.append("\n## Video length (organic)\n")
        b = [(0, 15), (15, 30), (30, 60), (60, 120), (120, 10 ** 6)]
        L.append(table(H, [srow(f"{lo}–{hi if hi < 10**6 else '∞'}s", stats(g)) for lo, hi in b
                           if (g := [r for r in vids if lo <= r["duration_s"] < hi])]))

    L.append("\n## Caption length (organic)\n")
    cb = [(0, 100), (100, 300), (300, 600), (600, 10 ** 6)]
    L.append(table(H, [srow(f"{lo}–{hi if hi < 10**6 else '∞'} chars", stats(g)) for lo, hi in cb
                       if (g := [r for r in org if lo <= len(r["caption"]) < hi])]))

    if any(r["pillar"] != "UNLABELED" for r in rows):
        L.append("\n## Pillar scorecard (organic, sorted by median)\n")
        pl = defaultdict(list)
        for r in org:
            pl[r["pillar"]].append(r)
        order = sorted(pl, key=lambda p: -(stats(pl[p])["med"] or 0))
        L.append(table(H + ["Share of posts", "Formats"],
                       [srow(p, stats(pl[p]), [f"{len(pl[p]) / len(org) * 100:.0f}%", dict(Counter(r['format'] for r in pl[p]))]) for p in order]))
        L.append("\n### Pillar × format (median " + score_name + ", posts)\n")
        fmts = sorted({r["format"] for r in org})
        L.append(table(["Pillar"] + fmts, [[p] + [(f"{fmt_num(med([r[score_key] for r in g]))} ({len(g)})" if (g := [r for r in pl[p] if r['format'] == f]) else "–") for f in fmts] for p in order]))
        recent_cut = dates[-1][:7]
        last = sorted({r["date"][:7] for r in rows})[-3:]
        rec = [r for r in rows if r["date"][:7] in last]
        L.append(f"\nPillar mix, last 3 months ({', '.join(last)}): " + ", ".join(f"{p} {c}" for p, c in Counter(r['pillar'] for r in rec).most_common()))

    def top(title, g, key, k=10, cond=lambda r: True):
        g = [r for r in g if cond(r) and r.get(key) is not None]
        if not g:
            return
        L.append(f"\n## {title}\n")
        L.append(table(["Date", "Format", "Pillar", "Dur", "Views", "Likes", "Comments", "Saves", "Shares", "URL", "Caption"],
                       [[r["date"], r["format"], r["pillar"], r["duration_s"] or "–", fmt_num(r["views"]), fmt_num(r["likes"]), r["comments"],
                         fmt_num(r["saves"]), fmt_num(r["shares"]), r["url"], r["caption"][:80]]
                        for r in sorted(g, key=lambda r: -r[key])[:k]]))

    for f, g in fm.items():
        top(f"Top {f} posts by {score_name} (organic)", g, score_key)
    if score_key != "views":
        top("Top reels by plays (organic)", org, "views", cond=lambda r: r["format"] == "reel")
    if has_saves:
        top("Top save rate (organic, ≥500 views)", org, "save_rate", cond=lambda r: (r["views"] or 0) >= 500)
    if has_shares:
        top("Top shares (organic)", org, "shares")
    top("Top comments (organic)", org, "comments")

    open(a.out, "w").write("\n".join(L) + "\n")
    print(f"{platform}: {len(rows)} posts · {len(paid)} paid-flagged · organic median {score_name} {fmt_num(base)} · wrote {a.out}")


if __name__ == "__main__":
    main()
