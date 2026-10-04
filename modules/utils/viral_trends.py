import os
import requests
from datetime import datetime, timedelta, timezone

YT = "https://www.googleapis.com/youtube/v3"

DEFAULT_QUERIES = [
    "mystère histoire insolite",
    "histoire méconnue France",
    "affaire oubliée mystère",
    "légende secrète patrimoine",
]


def fetch_viral_videos(queries=None, days=14, per_query=15, top_n=12):
    key = os.getenv("YOUTUBE_API_KEY")
    if not key:
        return []
    since = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ")
    found = {}
    for q in (queries or DEFAULT_QUERIES):
        try:
            s = requests.get(f"{YT}/search", params={
                "part": "snippet", "q": q, "type": "video", "order": "viewCount",
                "publishedAfter": since, "videoDuration": "short",
                "relevanceLanguage": "fr", "regionCode": "FR",
                "maxResults": per_query, "key": key}, timeout=15).json()
            ids = ",".join(i["id"]["videoId"] for i in s.get("items", []))
            if not ids:
                continue
            v = requests.get(f"{YT}/videos", params={
                "part": "snippet,statistics", "id": ids, "key": key}, timeout=15).json()
            for it in v.get("items", []):
                pub = datetime.fromisoformat(it["snippet"]["publishedAt"].replace("Z", "+00:00"))
                age_days = max((datetime.now(timezone.utc) - pub).days, 1)
                views = int(it["statistics"].get("viewCount", 0))
                found[it["id"]] = {
                    "title": it["snippet"]["title"],
                    "views": views,
                    "views_per_day": views // age_days,
                }
        except Exception as e:
            print(f"⚠️ YouTube trends erreur ({q}) : {e}")
    ranked = sorted(found.values(), key=lambda x: x["views_per_day"], reverse=True)
    return ranked[:top_n]