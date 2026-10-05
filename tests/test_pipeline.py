"""End-to-end checks of normalize → classify → analyze on synthetic fixtures.

Run: python3 -m unittest discover tests
Each test names the business rule it protects; if the rule changes, the test should fail.
"""
import csv, json, os, subprocess, sys, tempfile, unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.join(HERE, "..", "scripts")
FIX = os.path.join(HERE, "fixtures")


def run(script, *args, ok=True):
    p = subprocess.run([sys.executable, os.path.join(SCRIPTS, script), *args], capture_output=True, text=True)
    if ok and p.returncode != 0:
        raise AssertionError(f"{script} failed:\n{p.stdout}\n{p.stderr}")
    return p


class Pipeline(unittest.TestCase):
    def setUp(self):
        self.run_dir = tempfile.mkdtemp()
        run("normalize.py", "--platform", "tiktok", "--raw", os.path.join(FIX, "tiktok-sample.json"), "--run", self.run_dir, "--days", "0")
        run("normalize.py", "--platform", "instagram", "--raw", os.path.join(FIX, "instagram-sample.json"), "--run", self.run_dir, "--days", "0")
        self.rules = os.path.join(self.run_dir, "rules.json")
        json.dump({"pillars": {"HOWTO": "", "TESTIMONIAL": "", "PROMO": "", "EMOTIONAL": ""},
                   "rules": [["TESTIMONIAL", "(?i)testimonial"], ["PROMO", "(?i)package|book now"], ["HOWTO", "(?i)how to|checklist"]],
                   "default": "EMOTIONAL", "overrides": {}}, open(self.rules, "w"))

    def posts(self, platform):
        return {r["id"]: r for r in csv.DictReader(open(os.path.join(self.run_dir, "data", f"posts-{platform}.csv")))}

    def test_default_window_drops_posts_older_than_180_days(self):
        # Apify bills per post; audits default to 6 months, so older posts must never reach the baseline.
        import datetime
        d = tempfile.mkdtemp()
        today = datetime.date.today()
        items = [{"shortCode": "new", "type": "Image", "timestamp": (today - datetime.timedelta(days=10)).isoformat() + "T00:00:00.000Z", "likesCount": 5, "commentsCount": 0},
                 {"shortCode": "old", "type": "Image", "timestamp": (today - datetime.timedelta(days=200)).isoformat() + "T00:00:00.000Z", "likesCount": 5, "commentsCount": 0}]
        raw = os.path.join(d, "ig.json"); json.dump(items, open(raw, "w"))
        run("normalize.py", "--platform", "instagram", "--raw", raw, "--run", d)
        ids = {r["id"] for r in csv.DictReader(open(os.path.join(d, "data", "posts-instagram.csv")))}
        self.assertEqual(ids, {"new"})

    def test_tiktok_slideshows_are_their_own_format(self):
        # Slideshows and videos are judged separately in the audit, so the flag must survive normalization.
        self.assertEqual(self.posts("tiktok")["2"]["format"], "photo")
        self.assertEqual(self.posts("tiktok")["1"]["format"], "video")

    def test_stories_are_not_counted_as_posts(self):
        # Stories expire and aren't feed content; counting them would skew the baseline.
        self.assertNotIn("6", self.posts("tiktok"))

    def test_instagram_only_reels_carry_views(self):
        # Carousels/images have no public views; giving them 0 would drag every median down.
        p = self.posts("instagram")
        self.assertEqual(p["REEL1"]["views"], "500")
        self.assertEqual(p["CARO1"]["views"], "")

    def _analyze(self, platform, followers):
        run("classify.py", "--posts", os.path.join(self.run_dir, "data", f"posts-{platform}.csv"),
            "--rules", self.rules, "--out", os.path.join(self.run_dir, f"pillars-{platform}.json"))
        out = os.path.join(self.run_dir, f"stats-{platform}.md")
        run("analyze.py", "--posts", os.path.join(self.run_dir, "data", f"posts-{platform}.csv"),
            "--pillars", os.path.join(self.run_dir, f"pillars-{platform}.json"), "--followers", str(followers), "--out", out)
        return open(out).read()

    def test_paid_reach_is_flagged_and_kept_out_of_the_baseline(self):
        # A 20K-view post with a 0.5% like rate is bought reach; if it stayed in, the organic
        # median and every "best performer" list would be wrong.
        s = self._analyze("tiktok", 1200)
        self.assertIn("likely paid (like rate 0.5%)", s)
        self.assertIn("median **800**", s)  # organic = 1000, 800, 600 → 800 (20K and the ad excluded)

    def test_tiktok_ad_marker_flags_posts_with_healthy_like_rates(self):
        # Promoted posts can have a normal like rate; TikTok's own isAd marker is the only tell.
        s = self._analyze("tiktok", 1200)
        self.assertIn("marked paid/ad", s)

    def test_instagram_likes_far_above_followers_are_flagged(self):
        # 900 likes on a 1,000-follower account's image = engagement ads or a giveaway, not a repeatable format.
        s = self._analyze("instagram", 1000)
        self.assertIn("likely boosted (900 likes", s)
        self.assertIn("likely paid (like rate 0.4%)", s)

    def test_override_beats_rule_and_unknown_pillar_is_rejected(self):
        # Hand review is the final word; a typo in a pillar name must fail loudly, not create a new pillar.
        cfg = json.load(open(self.rules))
        cfg["overrides"] = {"1": "EMOTIONAL"}
        json.dump(cfg, open(self.rules, "w"))
        out = os.path.join(self.run_dir, "p.json")
        run("classify.py", "--posts", os.path.join(self.run_dir, "data", "posts-tiktok.csv"), "--rules", self.rules, "--out", out)
        self.assertEqual(json.load(open(out))["1"], "EMOTIONAL")
        cfg["overrides"] = {"1": "EMOTINAL"}
        json.dump(cfg, open(self.rules, "w"))
        p = run("classify.py", "--posts", os.path.join(self.run_dir, "data", "posts-tiktok.csv"), "--rules", self.rules, "--out", out, ok=False)
        self.assertNotEqual(p.returncode, 0)

    def test_cross_posted_captions_inherit_the_other_platforms_label(self):
        # The same post on both platforms must land in the same pillar, or the cross-platform playbook disagrees with itself.
        tt_out = os.path.join(self.run_dir, "pillars-tiktok.json")
        cfg = json.load(open(self.rules)); cfg["overrides"] = {"1": "EMOTIONAL"}; json.dump(cfg, open(self.rules, "w"))
        run("classify.py", "--posts", os.path.join(self.run_dir, "data", "posts-tiktok.csv"), "--rules", self.rules, "--out", tt_out)
        cfg["overrides"] = {}; json.dump(cfg, open(self.rules, "w"))
        ig_out = os.path.join(self.run_dir, "pillars-instagram.json")
        run("classify.py", "--posts", os.path.join(self.run_dir, "data", "posts-instagram.csv"), "--rules", self.rules, "--out", ig_out,
            "--inherit", f"{os.path.join(self.run_dir, 'data', 'posts-tiktok.csv')}:{tt_out}")
        self.assertEqual(json.load(open(ig_out))["REEL1"], "EMOTIONAL")  # rule alone would say HOWTO


if __name__ == "__main__":
    unittest.main()
