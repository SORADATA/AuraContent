import os
import yt_dlp


class VideoScraper:
    def __init__(self, output_dir="assets/backgrounds"):
        self.output_dir = output_dir
        os.makedirs(self.output_dir, exist_ok=True)

    def download_background(self, query_or_url, output_filename="bg_loop.mp4"):
        """
        Télécharge une vidéo de fond soit via une URL directe, 
        soit en faisant une recherche automatique sur YouTube (ex: 'ytsearch1:sujet').
        """
        output_path = os.path.join(self.output_dir, output_filename)
        
        # Si le fichier existe déjà, on évite de le retélécharger inutilement
        if os.path.exists(output_path) and os.path.getsize(output_path) > 10000:
            print(f"📁 Vidéo de fond déjà présente : {output_path}")
            return output_path

        # Si ce n'est pas une URL, on utilise la recherche textuelle de yt-dlp
        target = query_or_url
        if not query_or_url.startswith("http://") and not query_or_url.startswith("https://"):
            target = f"ytsearch1:{query_or_url}"
            print(f"🔍 Recherche automatique du fond vidéo : {query_or_url}")
        else:
            print(f"📥 Téléchargement du fond vidéo via URL : {query_or_url}")

        # Configuration officielle recommandée par yt-dlp pour l'embedding Python
        ydl_opts = {
            'format': 'bv*[height<=1920][ext=mp4]+ba[ext=m4a]/b[ext=mp4] / b',
            'outtmpl': output_path.replace('.mp4', ''),
            'noplaylist': True,
            'quiet': True,
            'no_warnings': True,
        }

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([target])
            
            # Vérification de la présence du fichier final
            if os.path.exists(output_path):
                print(f"✅ Vidéo de fond prête : {output_path}")
                return output_path
            else:
                # Parfois yt-dlp ajoute l'extension différemment selon le format fusionné
                for f in os.listdir(self.output_dir):
                    if f.startswith(output_filename.split('.')[0]):
                        final_found = os.path.join(self.output_dir, f)
                        return final_found
                        
            return None
        except Exception as e:
            print(f"❌ Erreur lors du téléchargement yt-dlp : {e}")
            return None