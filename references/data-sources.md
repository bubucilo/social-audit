# Data sources: what to call, what comes back, what fails

## TikTok: `clockworks/tiktok-scraper` (primary)
```json
{"profiles": ["<handle>"], "resultsPerPage": 300, "profileScrapeSections": ["videos"],
 "profileSorting": "latest", "oldestPostDateUnified": "180",
 "shouldDownloadVideos": false, "shouldDownloadCovers": false,
 "shouldDownloadSlideshowImages": false, "shouldDownloadSubtitles": false}
```
- **Window = last 180 days.** `oldestPostDateUnified` takes days back (or a date) and only
  works with `latest`/`oldest` sorting. It is a *charged* filter. If you'd rather not pay
  for it, drop it and cap `resultsPerPage` at ~1.3× (posts per week × 26), because
  normalize trims to 180 days either way.
- A 273-post full history finished in under a minute.
- Fields used: `playCount diggCount commentCount collectCount shareCount isSlideshow
  isAd isSponsored isPinned createTimeISO videoMeta.duration text webVideoUrl authorMeta.fans`.
- `isAd` is TikTok's own promoted marker. It caught promoted posts that had normal
  like rates, which the like-rate heuristic misses.

## Instagram: `apify/instagram-scraper` (primary)
```json
{"directUrls": ["https://www.instagram.com/<handle>/"], "resultsType": "posts",
 "resultsLimit": 300, "onlyPostsNewerThan": "180 days", "addParentData": false}
```
- **Window = last 180 days** via `onlyPostsNewerThan` (UTC; also accepts `YYYY-MM-DD`).
  Pinned posts may still come through, and normalize drops them if they're older.
  `resultsLimit` 300 is a cost cap (≈11 posts/day); raise it only for very high-volume accounts.
- Cost: pay-per-result, $0.0027/post on the free tier ($0.0023 bronze … $0.0005 diamond).
  A full-history pull of a 947-post account cost ~$2.56; its 180-day
  window would have been ~170 posts ≈ $0.46.
- A 434-post profile took about 2 minutes and returned 371 posts; the gap is archived or
  deleted posts.
- Fields used: `type (Video|Sidecar|Image) likesCount commentsCount videoPlayCount
  videoDuration timestamp shortCode caption childPosts isPinned paidPartnership`.
- No saves/shares (Instagram hides them). No follower count; get it from Xpoz.

## Downloading a dataset
Default run datasets are readable by id without a token:
`curl -s "https://api.apify.com/v2/datasets/<id>/items?format=json&clean=1" -o raw/<platform>-apify.json`.
If it returns 401/empty (restricted storage enabled on the account), page it in with
the Apify `get-dataset-items` tool using `fields=` and `limit`/`offset`, and write the JSON yourself.

## Xpoz (profile + IG enrichment only)
- `getTiktokUser` / `getInstagramUser`: followers, post count, bio.
- `getInstagramPostsByUser` with `fields: [codeUrl, reshareCount, saveCount, videoPlayCount]`:
  shares/saves for the ~75 most recent IG posts. Save as `raw/instagram-xpoz.json`
  (a list of objects with `codeUrl`, `reshareCount`, `saveCount`) → `normalize.py --extra`.
- Don't use it for the post list: TikTok returns only ~13 cached posts, and the csv
  export came back with 0 rows.

## TikTok fallback: yt-dlp (when Apify is down or out of credit)
If a recent yt-dlp fails on TikTok with "Unable to extract universal data for rehydration", the
`api_hostname` extractor arg below is the one-flag fix.
```bash
yt-dlp --extractor-args "tiktok:api_hostname=api22-normal-c-useast2a.tiktokv.com" \
  --skip-download --ignore-errors --flat-playlist --dump-json "https://www.tiktok.com/@<handle>" > raw/tiktok-ytdlp.jsonl
```
Gives views/likes/comments/saves/shares for every post, but **no slideshow flag and no
ad marker**. normalize.py doesn't read this shape; convert it to the Apify field names
first, or state that format and paid marker are missing.
