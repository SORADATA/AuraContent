import asyncio
import os
import shutil
import time
from datetime import datetime

from huggingface_hub import HfApi

from modules.brain import ContentBrain
from modules.asset_manager import AssetManager  # <-- Remplacement de VideoScraper
from modules.audio import AudioEngine
from modules.composer import Composer

try:
    from modules.utils.zernio_client import get_latest_videos_stats
except ImportError:
    print("⚠️ Module zernio_client introuvable. Feedback loop desactive pour cette execution.")

    def get_latest_videos_stats():
        return None


# =====================================================================
# --- UPLOAD HUGGING FACE (VIDÉO + LÉGENDE) ---
# =====================================================================

def upload_to_huggingface(video_path, topic, max_retries=5):
    hf_token = os.getenv("HF_TOKEN")
    if not hf_token:
        print("Upload HF ignore : token manquant.")
        return False

    if not video_path or not os.path.exists(video_path):
        print("Upload HF ignore : fichier video introuvable.")
        return False

    api = HfApi(token=hf_token)
    repo_id = os.getenv("HF_REPO_ID", "soradata/AIShortvideos")

    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    safe_topic = "".join(c if c.isalnum() else "_" for c in topic)[:50]
    remote_filename = f"videos/{timestamp}_{safe_topic}.mp4"
    remote_caption_filename = f"videos/{timestamp}_{safe_topic}.txt"

    for attempt in range(1, max_retries + 1):
        try:
            api.upload_file(
                path_or_fileobj=video_path,
                path_in_repo=remote_filename,
                repo_id=repo_id,
                repo_type="dataset",
                commit_message=f"Add generated short: {safe_topic}",
            )
            print(f"✅ Video uploadee sur Hugging Face : {repo_id}/{remote_filename}")

            caption_path = os.path.abspath("caption.txt")
            if os.path.exists(caption_path):
                api.upload_file(
                    path_or_fileobj=caption_path,
                    path_in_repo=remote_caption_filename,
                    repo_id=repo_id,
                    repo_type="dataset",
                    commit_message=f"Add caption for: {safe_topic}",
                )
                print(f"✅ Légende uploadee sur Hugging Face : {repo_id}/{remote_caption_filename}")

            return True
        except Exception as e:
            msg = str(e)
            print(f"❌ Echec upload Hugging Face (tentative {attempt}/{max_retries}) : {e}")
            if "429" in msg and attempt < max_retries:
                wait_s = min(2 ** attempt, 20)
                print(f"⏳ Attente de {wait_s}s avant retry...")
                time.sleep(wait_s)
                continue
            return False


# =====================================================================
# --- NETTOYAGE ---
# =====================================================================

def clean_cache():
    print("🧹 Cleaning up temporary files...")

    folders_to_clean = [
        os.path.join(os.getcwd(), "assets", "audio_clips"),
        os.path.join(os.getcwd(), "assets", "video_clips"),
        os.path.join(os.getcwd(), "assets", "temp"),
    ]

    for folder in folders_to_clean:
        if not os.path.exists(folder):
            continue

        normalized = os.path.abspath(folder)
        cwd = os.path.abspath(os.getcwd())

        if not normalized.startswith(os.path.join(cwd, "assets")):
            print(f"    SECURITY ALERT: Skipping unsafe path {folder}")
            continue

        for filename in os.listdir(folder):
            file_path = os.path.join(folder, filename)
            try:
                if os.path.isfile(file_path) or os.path.islink(file_path):
                    os.unlink(file_path)
                elif os.path.isdir(file_path):
                    shutil.rmtree(file_path)
            except Exception as e:
                print(f"    Failed to delete {file_path}. Reason: {e}")

    print("✅ Workspace clean!")


# =====================================================================
# --- SOUS-TITRES ---
# =====================================================================

def format_srt_timestamp(seconds):
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = seconds % 60
    return f"{h:02d}:{m:02d}:{s:06.3f}".replace(".", ",")


def chunk_words_for_subtitles(words, max_words=3):
    chunks = []
    current = []
    for word in words:
        current.append(word)
        if len(current) >= max_words:
            chunks.append(current)
            current = []
    if current:
        chunks.append(current)
    return chunks


def generate_grouped_srt(text, duration, output_path, max_words_per_caption=3, min_caption_dur=0.45):
    words = text.split()
    if not words:
        return None

    chunks = chunk_words_for_subtitles(words, max_words=max_words_per_caption)
    total_words = len(words)
    cursor = 0.0
    lines = []

    for idx, chunk in enumerate(chunks, start=1):
        proportion = len(chunk) / total_words
        seg_duration = max(duration * proportion, min_caption_dur)

        start = cursor
        end = min(start + seg_duration, duration)
        cursor = end

        caption_text = " ".join(chunk)
        lines.append(f"{idx}\n{format_srt_timestamp(start)} --> {format_srt_timestamp(end)}\n{caption_text}\n")

    if lines:
        last_block = lines[-1].split("\n")
        if len(last_block) >= 3:
            start_line = last_block[1].split(" --> ")[0]
            lines[-1] = f"{len(lines)}\n{start_line} --> {format_srt_timestamp(duration)}\n{last_block[2]}\n"

    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    return output_path


# =====================================================================
# --- HELPERS SCRIPT ---
# =====================================================================

def estimate_scene_count(duration_target):
    return max(6, min(14, round(duration_target / 5)))


def validate_script_payload(script_payload):
    if not isinstance(script_payload, dict):
        raise ValueError("script_payload doit etre un dict.")

    scenes = script_payload.get("scenes")
    if not isinstance(scenes, list) or not scenes:
        raise ValueError("script_payload['scenes'] est vide ou invalide.")

    for scene in scenes:
        if "id" not in scene or "text" not in scene:
            raise ValueError(f"Scene invalide : {scene}")

    return True


# =====================================================================
# --- GÉNÉRATION DE LA LÉGENDE ---
# =====================================================================

GEMINI_CAPTION_MODEL = "gemini-2.0-flash"
GROQ_CAPTION_MODEL = "openai/gpt-oss-120b"


def generate_caption_with_gemini(prompt_legende):
    from google import genai

    gemini_key = os.getenv("GEMINI_API_KEY")
    if not gemini_key:
        raise ValueError("Clé GEMINI_API_KEY introuvable.")

    client = genai.Client(api_key=gemini_key)
    response = client.models.generate_content(
        model=GEMINI_CAPTION_MODEL,
        contents=prompt_legende,
    )

    text = (response.text or "").strip()
    if not text:
        raise ValueError("Réponse Gemini vide.")
    return text


def generate_caption_with_groq(prompt_legende):
    import requests

    groq_key = os.getenv("GROQ_API_KEY")
    if not groq_key:
        raise ValueError("Clé GROQ_API_KEY introuvable.")

    headers = {
        "Authorization": f"Bearer {groq_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": GROQ_CAPTION_MODEL,
        "messages": [{"role": "user", "content": prompt_legende}],
    }

    response = requests.post(
        "https://api.groq.com/openai/v1/chat/completions",
        headers=headers,
        json=payload,
        timeout=30,
    )
    response.raise_for_status()

    text = response.json()["choices"][0]["message"]["content"].strip()
    if not text:
        raise ValueError("Réponse Groq vide.")
    return text


def generate_caption(full_text, video_title):
    prompt_legende = f"""
Voici le texte exact de ma vidéo TikTok/Shorts ({video_title}) :
"{full_text}"

Rédige une légende ultra-captivante.
Règles :
1. 1ère ligne très accrocheuse avec un emoji.
2. 1 ou 2 phrases courtes pour teaser le contenu sans le spoiler.
3. Termine par une question courte pour inciter aux commentaires.
4. Ajoute 4 hashtags pertinents dont #MinuteMystère.
Ne mets pas de guillemets autour de ta réponse.
"""

    fallback = f"{video_title} 🧠✨ #MinuteMystère #Decouverte #Pourtoi #Secretscachés"

    try:
        print("🧠 Tentative de génération de la légende avec Gemini...")
        return generate_caption_with_gemini(prompt_legende)
    except Exception as e_gemini:
        print(f"⚠️ Échec avec Gemini ({e_gemini}). Basculement sur Groq...")

    try:
        print("🚀 Tentative de génération de la légende avec Groq...")
        return generate_caption_with_groq(prompt_legende)
    except Exception as e_groq:
        print(f"⚠️ Échec avec Groq également ({e_groq}). Utilisation de la légende de secours.")
        return fallback


def save_caption(legende_finale):
    try:
        caption_path = os.path.abspath("caption.txt")
        with open(caption_path, "w", encoding="utf-8") as fichier:
            fichier.write(legende_finale)
        print(f"✅ Légende finale sauvegardée avec succès à la racine : {caption_path}")
        print("👀 TEXTE DE LA LÉGENDE :\n" + "-" * 30 + f"\n{legende_finale}\n" + "-" * 30)
    except Exception as e:
        print(f"⚠️ Erreur lors de l'écriture du fichier caption.txt : {e}")


# =====================================================================
# --- PIPELINE PRINCIPAL ---
# =====================================================================

async def main():
    print("🚀 STARTING AUTOMATION...")

    topic_input = os.getenv("VIDEO_TOPIC", "").strip()
    duration_target = int(os.getenv("VIDEO_DURATION", "45"))
    refine_angle = os.getenv("REFINE_ANGLE", "true").lower() == "true"
    use_hooks_ab_test = os.getenv("USE_HOOK_VARIANTS", "true").lower() == "true"

    brain = ContentBrain()
    asset_manager = AssetManager() # Initialisation du nouveau gestionnaire d'assets

    print("📡 Récupération des statistiques Zernio pour l'Agent IA...")
    try:
        stats_historique = get_latest_videos_stats()
    except Exception as e:
        print(f"⚠️ Impossible de recuperer les stats Zernio : {e}")
        stats_historique = None

    # --- 1. GÉNÉRATION DU SUJET ET DE LA REQUÊTE ---
    try:
        if topic_input:
            topic = topic_input
            print(f"📌 Sujet fourni manuellement : {topic}")
            if refine_angle and hasattr(brain, "refine_topic_angle"):
                topic = brain.refine_topic_angle(topic)
                print(f"🎯 Angle affine : {topic}")
        else:
            topic = brain.get_trending_topic(previous_stats_list=stats_historique)
            print(f"🔥 Sujet selectionne automatiquement : {topic}")

        print("🔍 Génération du mot-clé de recherche visuelle par l'IA...")
        dynamic_query = brain.generate_video_search_query(topic)
        print(f"🎯 Requête vidéo générée : '{dynamic_query}'")

    except Exception as e:
        print(f"❌ Brain Error (Sujet/Requête): {e}")
        return

    # --- 2. RECHERCHE DU FOND VIDÉO ---
    temp_dir = os.path.join(os.getcwd(), "assets", "temp")
    os.makedirs(temp_dir, exist_ok=True)
    bg_video_path = os.path.join(temp_dir, "current_bg.mp4")
    is_video_found = False

    try:
        is_video_found = asset_manager.fetch_background_video(dynamic_query, bg_video_path)
        if is_video_found:
            print("🎬 Fond vidéo validé et prêt pour le montage.")
        else:
            print("⚠️ Aucun fond vidéo trouvé. Le mode fallback images IA s'activera après la génération du script.")
            bg_video_path = None
    except Exception as e:
        print(f"⚠️ AssetManager Error: {e}")
        bg_video_path = None

    # --- 3. GÉNÉRATION DU SCRIPT ET HOOKS ---
    try:
        chosen_hook = None
        if use_hooks_ab_test:
            try:
                hooks = brain.generate_hook_variants(
                    topic,
                    n=5,
                    previous_stats_list=stats_historique,
                )
                chosen_hook = hooks[0]["text"]
                print(f"🧠 Hook retenu ({hooks[0]['pattern']}): {chosen_hook}")
            except Exception as e:
                print(f"⚠️ Generation des hooks alternatifs echouee : {e}")

        scene_count = estimate_scene_count(duration_target)
        print(f"⏱️ Duree cible: {duration_target}s -> {scene_count} scenes")

        script_payload = brain.generate_script_with_target(
            topic,
            scene_count,
            chosen_hook=chosen_hook,
        )

        validate_script_payload(script_payload)
        script = script_payload["scenes"]
        video_title = script_payload.get("title", topic)

    except Exception as e:
        print(f"❌ Brain Error (Script): {e}")
        return

    if not script:
        print("❌ Script generation failed.")
        return

    # --- 4. FALLBACK IMAGES (SI PAS DE VIDÉO) ---
    video_pairs = [None] * len(script)
    if not is_video_found:
        print("🎨 Mode fallback : Génération des visuels IA (Pollinations) en cours...")
        visual_id = script_payload.get("visual_identity", "Cinematic documentary")
        video_pairs = []
        for scene in script:
            img_path = os.path.join(temp_dir, f"scene_{scene['id']}.jpg")
            asset_manager.generate_image(scene["image_prompt"], img_path, visual_id)
            video_pairs.append(img_path)

    # --- 5. LÉGENDE, AUDIO ET SOUS-TITRES ---
    print("📝 Demande de légende à l'IA basée sur le script complet...")
    full_text = " ".join(scene["text"] for scene in script)
    legende_finale = generate_caption(full_text, video_title)
    save_caption(legende_finale)

    audio_engine = AudioEngine()

    try:
        print("🎙️ Generation audio...")
        script = await audio_engine.process_script(script)
    except Exception as e:
        print(f"❌ Audio Error: {e}")
        return

    subs_dir = os.path.join(os.getcwd(), "assets", "temp", "subs")
    os.makedirs(subs_dir, exist_ok=True)

    print("📝 Generation des sous-titres...")
    for scene in script:
        srt_path = os.path.join(subs_dir, f"scene_{scene['id']}.srt")
        scene["srt_path"] = generate_grouped_srt(
            text=scene["text"],
            duration=scene["duration"],
            output_path=srt_path,
            max_words_per_caption=3,
            min_caption_dur=0.45,
        )

    # --- 6. ASSEMBLAGE ET MONTAGE ---
    try:
        print("🎞️ Composition video...")
        composer = Composer()
        final_scene_paths = composer.render_all_scenes(
            script_data=script,
            video_pairs=video_pairs,
            bg_video_path=bg_video_path
        )
    except Exception as e:
        print(f"❌ Render Error: {e}")
        return

    if not final_scene_paths:
        print("❌ Failed to generate any scenes.")
        return

    try:
        final_path = composer.concatenate_with_transitions(final_scene_paths)
    except Exception as e:
        print(f"❌ Final assembly error: {e}")
        return

    # --- 7. UPLOAD ---
    if final_path:
        print(f"✅ Video finale prête : {final_path}")
        upload_to_huggingface(final_path, video_title)
        clean_cache()
    else:
        print("❌ L'assemblage final a échoué, upload annulé.")


if __name__ == "__main__":
    asyncio.run(main())