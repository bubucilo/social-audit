# Data sources: what to call, what comes back, what fails

## TikTok: `clockworks/tiktok-scraper` (primary)
```json
{"profiles": ["<handle>"], "resultsPerPage": 1000, "profileScrapeSections": ["videos"],
 "profileSorting": "latest", "shouldDownloadVideos": false, "shouldDownloadCovers": false,
 "shouldDownloadSlideshowImages": false, "shouldDownloadSubtitles": false}
```
- Returns every post; a 273-post account finished in under a minute.
- Fields used: `playCount diggCount commentCount collectCount shareCount isSlideshow
  isAd isSponsored isPinned createTimeISO videoMeta.duration text webVideoUrl authorMeta.fans`.
- `isAd` is TikTok's own promoted marker. It caught promoted posts that had normal
  like rates, which the like-rate heuristic misses.

## Instagram: `apify/instagram-scraper` (primary)
```json
{"directUrls": ["https://www.instagram.com/<handle>/"], "resultsType": "posts",
 "resultsLimit": 1000, "addParentData": false}
```
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
