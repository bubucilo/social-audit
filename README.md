# social-audit

A [Claude Code](https://claude.com/claude-code) skill that audits a brand's own **TikTok** and **Instagram** profile and turns what actually performed into a **content-pillar playbook** (max 5 pillars, each with objective, hooks, format per platform, and example content).

```
/social-audit https://www.tiktok.com/@yourbrand https://www.instagram.com/yourbrand/
```

## What it does

1. **Pulls every post** with metrics through Apify: views, likes, comments, saves, shares, format, duration, TikTok's ad marker.
2. **Separates paid from organic.** TikTok's `isAd` marker, ≥5K views at a <2% like rate, and non-video likes far above the follower base all get flagged and kept out of every ranking.
3. **Categorizes every post.** Claude reads the captions and writes a brand-specific taxonomy as regex rules plus hand overrides; a script applies them reproducibly.
4. **Computes the numbers deterministically:** trend by quarter, format, video length, caption length, category scorecard with hit rates, and top posts by views/saves/shares/comments.
5. **Writes the audit and the playbook.** Every number traces back to a generated stats file.

The scripts do all the counting; the model only makes judgment calls (taxonomy, why a winner won, the playbook).

## Output

Everything for a run lands in one folder under the project you run it from:

```
research/social-audit/<handle>/<YYYY-MM-DD>/
  raw/                    Apify datasets as downloaded
  data/posts-*.csv        normalized posts
  pillar-rules.json       the category taxonomy + rules (reused on the next run)
  stats-*.md              fact sheet per platform
  tiktok-audit.md         findings per platform
  instagram-audit.md
  playbook.md             ≤5 content pillars across platforms
```

## Install

```bash
git clone https://github.com/bubucilo/social-audit ~/.claude/skills/social-audit
```

Requirements:
- An **Apify** MCP server connected to Claude Code (actors used: `clockworks/tiktok-scraper`, `apify/instagram-scraper`). Runs spend Apify credits.
- Optional: an **Xpoz** MCP server, used for the Instagram follower count and shares/saves on recent posts, which Instagram hides publicly.
- Python 3.9+ (standard library only) and `curl`.

If the project has brand voice rules (`brand-voices/*`, `BRAND.md`, `VOICE.md`), the playbook uses them as guardrails.

## Scripts

| Script | Does |
| --- | --- |
| `scripts/normalize.py` | Apify TikTok/Instagram JSON → one unified posts CSV + a captions file |
| `scripts/classify.py` | Applies `pillar-rules.json` (regex rules, overrides, cross-platform inheritance) and prints a review list |
| `scripts/analyze.py` | Stats + paid flags → `stats-<platform>.md` |

```bash
python3 -m unittest discover tests
```

## Limits

- Public accounts only; TikTok and Instagram only.
- Paid flags are heuristics, except TikTok's own ad marker. Confirm them with the account owner.
- Instagram doesn't expose saves/shares or carousel reach, so Instagram formats are compared on likes + comments.
- Tested end to end on one account so far (273 TikTok + 371 Instagram posts).

## License

MIT
