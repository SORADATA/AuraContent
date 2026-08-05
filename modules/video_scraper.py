import os
import yt_dlp

class VideoScraper:
    def __init__(self, output_dir="assets/backgrounds"):
        self.output_dir = output_dir
        os.makedirs(self.output_dir, exist_ok=True)

    def search_and_download(self, query="mysterious dark cinematic drone vertical", output_filename="current_bg.mp4"):
        """
        Recherche une vidéo sur YouTube, la télécharge, et retourne 
        le chemin du fichier ET le titre réel de la vidéo trouvée.
        """
        output_path = os.path.join(self.output_dir, output_filename)
        search_target = f"ytsearch1:{query}"

        ydl_opts = {
            'format': 'bv*[height<=1920][ext=mp4]+ba[ext=m4a]/b[ext=mp4] / b',
            'outtmpl': output_path.replace('.mp4', ''),
            'noplaylist': True,
            'quiet': True,
            'no_warnings': True,
        }

        try:
            print(f"🔍 Recherche du meilleur fond vidéo dispo sur YouTube pour : {query}")
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(search_target, download=True)
                
                # Si c'est une liste (résultat de recherche), on prend le premier élément
                if 'entries' in info:
                    video_info = info['entries'][0]
                else:
                    video_info = info

                real_title = video_info.get('title', 'Mystère insondable')
                print(f"✅ Vidéo trouvée et validée : '{real_title}'")

                # Vérification du fichier de sortie
                if os.path.exists(output_path):
                    return output_path, real_title
                else:
                    for f in os.listdir(self.output_dir):
                        if f.startswith(output_filename.split('.')[0]):
                            return os.path.join(self.output_dir, f), real_title

            return None, None
        except Exception as e:
            print(f"❌ Erreur yt-dlp : {e}")
            return None, None