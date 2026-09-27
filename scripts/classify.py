#!/usr/bin/env python3
"""Apply the model's pillar rules to a posts CSV and print a review list.

The model decides WHAT the pillars are and writes the rules; this script only applies
them so the result is reproducible and cheap to re-run after each round of fixes.

Usage:
  classify.py --posts RUN/data/posts-tiktok.csv --rules RUN/pillar-rules.json --out RUN/pillars-tiktok.json
              [--inherit RUN/data/posts-instagram.csv:RUN/pillars-instagram.json] [--review]

pillar-rules.json:
  {
    "pillars":   {"HOWTO": "step-by-step guides", ...},       # the fine-grained taxonomy, with meaning
    "rules":     [["TESTIMONIAL", "(?i)testimonial|review from"], ...],  # first regex that matches wins
    "default":   "EMOTIONAL",
    "overrides": {"<post id>": "PILLAR", ...}                     # hand fixes after review; beat everything
  }

Order of precedence: overrides > inherited (same caption on the other platform) > rules > default.
"""
import argparse, csv, json, re, sys
from collections import Counter


def norm(s):
    return re.sub(r"\W+", "", (s or "").lower())[:60]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--posts", required=True)
    ap.add_argument("--rules", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--inherit", help="OTHER_POSTS_CSV:OTHER_PILLARS_JSON — reuse labels of cross-posted captions")
    ap.add_argument("--review", action="store_true", help="print every post grouped by pillar")
    a = ap.parse_args()

    cfg = json.load(open(a.rules))
    known = set(cfg.get("pillars", {})) | {p for p, _ in cfg["rules"]} | {cfg["default"]}
    rules = [(p, re.compile(rx)) for p, rx in cfg["rules"]]
    overrides = {str(k): v for k, v in cfg.get("overrides", {}).items()}
    bad = {v for v in overrides.values() if v not in known}
    if bad:
        sys.exit(f"ERROR: overrides use pillars not in the taxonomy: {sorted(bad)}")

    inherited = {}
    if a.inherit:
        ocsv, ojson = a.inherit.split(":", 1)
        olabels = json.load(open(ojson))
        for r in csv.DictReader(open(ocsv)):
            k = norm(r["caption"])
            if len(k) >= 30 and r["id"] in olabels:
                inherited[k] = olabels[r["id"]]

    posts = list(csv.DictReader(open(a.posts)))
    labels, source = {}, Counter()
    for r in posts:
        pid, cap = r["id"], r["caption"]
        if pid in overrides:
            labels[pid] = overrides[pid]; source["override"] += 1; continue
        k = norm(cap)
        if len(k) >= 30 and k in inherited and inherited[k] in known:
            labels[pid] = inherited[k]; source["inherited"] += 1; continue
        for p, rx in rules:
            if rx.search(cap):
                labels[pid] = p; source["rule"] += 1; break
        else:
            labels[pid] = cfg["default"]; source["default"] += 1

    json.dump(labels, open(a.out, "w"), indent=1, ensure_ascii=False)
    print(f"labelled {len(labels)} posts · by {dict(source)}")
    print("counts:", dict(Counter(labels.values()).most_common()))
    if source["default"] > 0.25 * len(posts):
        print(f"WARNING: {source['default']} posts fell to the default pillar — add rules or overrides")

    if a.review:
        by = {}
        for r in posts:
            by.setdefault(labels[r["id"]], []).append(r)
        for p in sorted(by):
            print(f"\n== {p} ({len(by[p])})")
            for r in by[p]:
                v = r["views"] or "-"
                print(f"{r['id']}|{r['format'][:4]}|{v}|{r['caption'][:90]}")


if __name__ == "__main__":
    main()
