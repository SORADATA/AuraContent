import os
import glob
import random
import shutil
import yt_dlp


class VideoScraper:
    def __init__(self, output_dir="assets/backgrounds", fallback_dir="assets/fallback_backgrounds"):
        self.output_dir = output_dir
        self.fallback_dir = fallback_dir
        os.makedirs(self.output_dir, exist_ok=True)
        os.makedirs(self.fallback_dir, exist_ok=True)

    def _cleanup_previous(self, base_name):
        for f in glob.glob(os.path.join(self.output_dir, base_name + ".*")):
            try:
                os.remove(f)
            except OSError:
                pass

    def _get_local_fallback(self, output_filename="current_bg.mp4"):
        candidates = glob.glob(os.path.join(self.fallback_dir, "*.mp4"))
        if not candidates:
            return None, None
        chosen = random.choice(candidates)
        final_path = os.path.join(self.output_dir, output_filename)
        try:
            shutil.copy2(chosen, final_path)
            return final_path, os.path.basename(chosen)
        except Exception:
            return None, None

    def _download_search(self, query, base_name, max_duration):
        search_target = f"ytsearch1:{query}"
        outtmpl = os.path.join(self.output_dir, base_name + ".%(ext)s")

        ydl_opts = {
            "format": "best[ext=mp4][height<=1080]/best[height<=1080]/best",
            "outtmpl": outtmpl,
            "noplaylist": True,
            "quiet": True,
            "no_warnings": True,
            "socket_timeout": 20,
            "retries": 3,
            "extract_flat": False,
            "match_filter": yt_dlp.utils.match_filter_func(f"duration < {max_duration}"),
            "http_headers": {
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/126.0.0.0 Safari/537.36"
                )
            },
        }

        if os.path.exists("cookies.txt"):
            ydl_opts["cookiefile"] = "cookies.txt"

        # Essai sans args exotiques d'abord
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(search_target, download=True)

            entries = info.get("entries") if info else None
            if not entries:
                return None, None

            video_info = entries[0]
            title = video_info.get("title", "Titre inconnu")
            return self._find_downloaded_file(base_name), title
        except Exception:
            return None, None

    def _find_downloaded_file(self, base_name):
        downloaded = glob.glob(os.path.join(self.output_dir, base_name + ".*"))
        if not downloaded:
            return None
        return downloaded[0]

    def search_and_download(
        self,
        query="mysterious dark cinematic drone vertical",
        output_filename="current_bg.mp4",
        max_duration=120
    ):
        base_name = os.path.splitext(output_filename)[0]
        final_path = os.path.join(self.output_dir, output_filename)

        raw_query = query.strip().replace('"', "") if query else ""
        clean_query = " ".join(raw_query.split()[:6]) if raw_query else "mysterious dark cinematic vertical"

        queries_to_try = [
            clean_query,
            "mysterious dark cinematic vertical background",
            "abandoned spooky place drone shot",
            "dark fantasy atmosphere vertical",
            "deep underground cave exploration",
            "scifi abstract mysterious dark background",
        ]

        for current_query in queries_to_try:
            if not current_query.strip():
                continue

            self._cleanup_previous(base_name)

            print(f"🔍 Recherche YouTube pour : {current_query}")
            downloaded_path, title = self._download_search(current_query, base_name, max_duration)

            if downloaded_path and os.path.exists(downloaded_path):
                try:
                    if downloaded_path != final_path:
                        os.replace(downloaded_path, final_path)
                    print(f"✅ Vidéo de fond trouvée : '{title}'")
                    return final_path, title
                except Exception:
                    pass

        print("⚠️ yt-dlp a échoué, tentative fallback local...")
        fallback_path, fallback_name = self._get_local_fallback(output_filename)
        if fallback_path and os.path.exists(fallback_path):
            print(f"✅ Fallback local utilisé : '{fallback_name}'")
            return fallback_path, fallback_name

        print("❌ Impossible de récupérer un fond vidéo valide.")
        return None, None