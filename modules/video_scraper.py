import os
import glob
import yt_dlp



class VideoScraper:
    def __init__(self, output_dir="assets/backgrounds"):
        self.output_dir = output_dir
        os.makedirs(self.output_dir, exist_ok=True)

    def search_and_download(self, query="mysterious dark cinematic drone vertical",
                             output_filename="current_bg.mp4",
                             max_duration=120):
        base_name = os.path.splitext(output_filename)[0]
        final_path = os.path.join(self.output_dir, output_filename)

        raw_query = query.strip().replace('"', '') if query else ""
        clean_query = " ".join(raw_query.split()[:6]) if raw_query else "mysterious dark cinematic vertical"

        queries_to_try = [
            clean_query,
            "mysterious dark cinematic vertical background 9:16",
            "abandoned spooky place drone shot vertical",
            "dark fantasy atmosphere Unreal Engine 5 vertical",
            "deep underground cave exploration cinematic 9:16",
            "scifi abstract mysterious dark background vertical",
        ]

        for current_query in queries_to_try:
            if not current_query.strip():
                continue

            # Nettoyage des résidus des tentatives précédentes
            for f in glob.glob(os.path.join(self.output_dir, base_name + ".*")):
                try:
                    os.remove(f)
                except OSError:
                    pass

            search_target = f"ytsearch1:{current_query}"
            outtmpl = os.path.join(self.output_dir, base_name + ".%(ext)s")

            ydl_opts = {
                'format': 'best[ext=mp4][height<=1920]/best[height<=1920]/best',
                'outtmpl': outtmpl,
                'noplaylist': True,
                'quiet': True,
                'no_warnings': True,
                'match_filter': yt_dlp.utils.match_filter_func(
                    f"duration < {max_duration}"
                ),
                'socket_timeout': 15,
            }

            try:
                print(f"🔍 Recherche sur YouTube pour : {current_query}")
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    info = ydl.extract_info(search_target, download=True)

                entries = info.get('entries') if info else None
                if not entries:
                    continue

                video_info = entries[0]
                real_title = video_info.get('title', 'Titre inconnu')

                downloaded = glob.glob(os.path.join(self.output_dir, base_name + ".*"))
                if not downloaded:
                    continue

                actual_path = downloaded[0]
                if actual_path != final_path:
                    os.replace(actual_path, final_path)

                print(f"✅ Vidéo de fond trouvée et validée : '{real_title}'")
                return final_path, real_title

            except Exception as e:
                print(f"⚠️ Échec avec '{current_query}' ({e}), tentative suivante...")
                continue

        print("❌ Erreur critique : Impossible de récupérer un fond vidéo valide.")
        return None, None