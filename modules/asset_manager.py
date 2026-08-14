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
        
        # ---------------------------------------------------------
        # SCÈNES SPÉCIFIQUES (Lieux réels, personnages, objets)
        # ---------------------------------------------------------
        if scene_type == "specific":
            # 1. On cherche d'ABORD la vraie photo dans les archives !
            print(f"🔍 Recherche de la vraie photo historique : '{query}'...")
            if self.archives.get_wikimedia(query, output_path):
                print("🏛️ Vraie archive trouvée !")
                return True, "wiki"
                
            # 2. Si Wikipédia n'a rien, on demande à l'IA de l'imaginer
            print(f"🧠 Archive introuvable. Tentative IA-First pour : '{query}'.")
            if self.ai.generate_image(query, output_path):
                return True, "ai"
                
        # ---------------------------------------------------------
        # SCÈNES GÉNÉRIQUES (Ambiance, paysages, émotions)
        # ---------------------------------------------------------
        else:
            # 3. Vidéos d'ambiance Pexels
            print(f"🔍 Recherche vidéo d'ambiance : '{query}'...")
            if self.videos.fetch_background(query, output_path):
                return True, "video"

        # 4. FALLBACK ULTIME POUR TOUT LE MONDE
        print(f"🎨 Génération IA de secours : '{query}'...")
        if self.ai.generate_image(query, output_path):
            return True, "ai"
            
        print(f"❌ Échec total de la récupération d'asset pour : '{query}'")
        return False, "none"