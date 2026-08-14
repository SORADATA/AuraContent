from modules.utils.download.utils_assets import load_history
from modules.utils.download.video_provider import VideoProvider
from modules.utils.download.archive_provider import ArchiveProvider
from modules.ai_image import AIImageGenerator


class AssetManager:
    def __init__(self):
        # 1. État global
        self.history = load_history()
        # 2. Initialisation des fournisseurs spécialisés
        self.videos = VideoProvider(self.history)
        self.archives = ArchiveProvider(self.history)
        self.ai = AIImageGenerator()

    def get_best_asset(self, query, output_path, scene_type="generic"):
        """
        Orchestrateur principal.
        scene_type: 'generic' (vagues, ambiance) ou 'specific' (personnage, événement précis).
        """
        # LOGIQUE IA-FIRST (Si c'est trop pointu, on ne perd pas de temps avec des vidéos génériques)
        if scene_type == "specific":
            print(f"🧠 Sujet spécifique : '{query}'. Tentative IA-First.")
            if self.ai.generate_image(query, output_path):
                return True, "ai"
                
        # RECHERCHE DE STOCK STANDARD
        print(f"🔍 Recherche de contenu existant : '{query}'...")
        
        # 1. Vidéos d'ambiance
        if self.videos.fetch_background(query, output_path):
            return True, "video"
            
        # 2. Photos documentaires/historiques
        if self.archives.get_wikimedia(query, output_path):
            return True, "wiki"

        # FALLBACK ULTIME (IA si ça n'a pas encore été fait)
        if scene_type != "specific":
            print(f"🎨 Génération IA de secours : '{query}'...")
            if self.ai.generate_image(query, output_path):
                return True, "ai"
                
        print(f"❌ Échec total de la récupération d'asset pour : '{query}'")
        return False, "none"