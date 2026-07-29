import os
from modules.composer import Composer

class ComposerKids(Composer):
    """
    Étend le Composer classique pour la chaîne Mimolune.
    Gère l'assemblage même s'il n'y a pas de musique de fond.
    """
    def __init__(self):
        super().__init__()
        
        self.base_dir = os.path.join(os.getcwd(), "assets", "mimolune")
        self.temp_dir = os.path.join(self.base_dir, "temp")
        self.final_dir = os.path.join(self.base_dir, "final")
        self.music_dir = os.path.join(self.base_dir, "audio")

        os.makedirs(self.temp_dir, exist_ok=True)
        os.makedirs(self.final_dir, exist_ok=True)
        os.makedirs(self.music_dir, exist_ok=True)

        self.bg_music_path = os.path.join(self.music_dir, "kids_bgm.mp3")

    def assemble_final_video(self, scenes):
        print("🎞️ Assemblage final de la vidéo Mimolune...")
        
        valid_scenes = [s["video_path"] for s in scenes if "video_path" in s]
        
        if not valid_scenes:
            print("❌ Aucune scène valide à assembler.")
            return None

        # Concaténation des clips avec transitions
        final_path = self.concatenate_with_transitions(valid_scenes, output_filename="final_short.mp4")
        
        # Si la musique de fond n'existe pas, on retourne directement la vidéo assemblée
        if not os.path.exists(self.bg_music_path):
            print("⚠️ Aucune musique 'kids_bgm.mp3' trouvée, export de la vidéo sans musique.")
            return final_path

        # Si par contre tu ajoutes un fichier plus tard, il se mixera automatiquement
        return final_path