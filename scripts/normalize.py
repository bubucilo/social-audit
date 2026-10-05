#!/usr/bin/env python3
"""Normalize an Apify TikTok or Instagram dataset into one posts CSV + a captions file.

Usage:
  normalize.py --platform tiktok    --raw RUN/raw/tiktok-apify.json    --run RUN [--days 180]
  normalize.py --platform instagram --raw RUN/raw/instagram-apify.json --run RUN [--days 180] [--extra RUN/raw/instagram-xpoz.json]

--days: audit window, default 180 (6 months back from today). Posts older than the
cutoff are dropped, so a pull that overshoots still yields a 6-month audit. --days 0 = all.

Writes:
  RUN/data/posts-<platform>.csv   one row per post, unified schema (see COLUMNS)
  RUN/captions-<platform>.txt     compact list the model reads to classify pillars
Prints a one-line profile summary (followers when the dataset carries it).

--extra: optional JSON list of {"shortcode"|"id", "shares", "saves"} (e.g. from Xpoz)
merged into posts that match; IG hides these publicly so Apify leaves them empty.
"""
import argparse, csv, datetime, json, os, re, sys

COLUMNS = ["id", "url", "date", "platform", "format", "duration_s", "views",
           "likes", "comments", "saves", "shares", "pinned", "paid_marker", "caption"]


def num(x):
    try:
        return int(x) if x is not None and x != "" else None
    except (TypeError, ValueError):
        return None


def tiktok_rows(items):
    rows, fans = [], None
    for it in items:
        if it.get("isStory"):
            continue
        am = it.get("authorMeta") or {}
        fans = fans or am.get("fans")
        vm = it.get("videoMeta") or {}
        rows.append({
            "id": str(it["id"]),
            "url": it.get("webVideoUrl") or "",
            "date": (it.get("createTimeISO") or "")[:10],
            "platform": "tiktok",
            "format": "photo" if it.get("isSlideshow") else "video",
            "duration_s": round(vm.get("duration") or 0),
            "views": num(it.get("playCount")),
            "likes": num(it.get("diggCount")),
            "comments": num(it.get("commentCount")),
            "saves": num(it.get("collectCount")),
            "shares": num(it.get("shareCount")),
            "pinned": int(bool(it.get("isPinned"))),
            "paid_marker": int(bool(it.get("isAd") or it.get("isSponsored"))),
            "caption": (it.get("text") or "").replace("\n", " ").strip(),
        })
    return rows, fans


IG_FORMAT = {"Video": "reel", "Sidecar": "carousel", "Image": "image"}


def instagram_rows(items):
    rows = []
    for it in items:
        if it.get("error") or not it.get("shortCode"):
            continue
        fmt = IG_FORMAT.get(it.get("type"), (it.get("type") or "").lower())
        rows.append({
            "id": it["shortCode"],
            "url": it.get("url") or f"https://www.instagram.com/p/{it['shortCode']}/",
            "date": (it.get("timestamp") or "")[:10],
            "platform": "instagram",
            "format": fmt,
            "duration_s": round(it.get("videoDuration") or 0),
            # videoPlayCount = plays incl. replays (what the app shows); fall back to views
            "views": num(it.get("videoPlayCount") or it.get("videoViewCount")) if fmt == "reel" else None,
            "likes": num(it.get("likesCount")),
            "comments": num(it.get("commentsCount")),
            "saves": None,
            "shares": None,
            "pinned": int(bool(it.get("isPinned"))),
            "paid_marker": int(bool(it.get("paidPartnership"))),
            "caption": (it.get("caption") or "").replace("\n", " ").strip(),
        })
    return rows, None


def merge_extra(rows, path):
    extra = json.load(open(path))
    by_key = {}
    for e in extra:
        k = e.get("shortcode") or e.get("id")
        if not k and e.get("codeUrl"):  # Xpoz shape
            k = e["codeUrl"].rstrip("/").split("/")[-1]
        if k:
            by_key[str(k)] = e
    hit = 0
    for r in rows:
        e = by_key.get(r["id"])
        if not e:
            continue
        hit += 1
        for field, keys in (("shares", ("shares", "reshareCount")), ("saves", ("saves", "saveCount"))):
            for k in keys:
                if e.get(k) is not None:
                    r[field] = num(e[k])
                    break
    print(f"extra metrics merged into {hit} posts", file=sys.stderr)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--platform", required=True, choices=["tiktok", "instagram"])
    ap.add_argument("--raw", required=True)
    ap.add_argument("--run", required=True, help="run folder, e.g. research/social-audit/<handle>/<date>")
    ap.add_argument("--extra")
    ap.add_argument("--days", type=int, default=180, help="audit window in days back from today; 0 = no cutoff")
    a = ap.parse_args()

    items = json.load(open(a.raw))
    if isinstance(items, dict):
        items = items.get("items") or items.get("data") or []
    rows, fans = (tiktok_rows if a.platform == "tiktok" else instagram_rows)(items)
    if not rows:
        sys.exit(f"ERROR: no posts parsed from {a.raw} — check the dataset (private account? wrong actor?)")
    if a.extra:
        merge_extra(rows, a.extra)

    seen, uniq = set(), []
    for r in sorted(rows, key=lambda r: r["date"]):
        if r["id"] not in seen:
            seen.add(r["id"]); uniq.append(r)
    rows = uniq
    if a.days:
        cutoff = (datetime.date.today() - datetime.timedelta(days=a.days)).isoformat()
        before = len(rows)
        rows = [r for r in rows if r["date"] >= cutoff]
        print(f"window: last {a.days} days (since {cutoff}) · kept {len(rows)} of {before} posts", file=sys.stderr)
        if not rows:
            sys.exit(f"ERROR: no posts since {cutoff} — account inactive in the window; rerun with --days 0 and say so")

    os.makedirs(os.path.join(a.run, "data"), exist_ok=True)
    out = os.path.join(a.run, "data", f"posts-{a.platform}.csv")
    with open(out, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COLUMNS)
        w.writeheader()
        w.writerows(rows)

    cap = os.path.join(a.run, f"captions-{a.platform}.txt")
    with open(cap, "w") as f:
        f.write("id|date|format|dur|views|likes|comments|caption\n")
        for r in rows:
            c = re.sub(r"\s+", " ", r["caption"])[:160]
            f.write(f"{r['id']}|{r['date']}|{r['format']}|{r['duration_s']}|{r['views'] if r['views'] is not None else '-'}|{r['likes']}|{r['comments']}|{c}\n")

    fmts = {}
    for r in rows:
        fmts[r["format"]] = fmts.get(r["format"], 0) + 1
    print(f"{a.platform}: {len(rows)} posts {rows[0]['date']} → {rows[-1]['date']} · formats {fmts}"
          + (f" · followers {fans}" if fans else ""))
    print(f"wrote {out}\nwrote {cap}")


if __name__ == "__main__":
    main()
