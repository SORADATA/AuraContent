import streamlit as st
import asyncio
import os
from modules.brain import ContentBrain
from modules.asset_manager import AssetManager
from modules.audio import AudioEngine
from modules.composer import Composer



# --- Injection des secrets Streamlit dans les variables d'environnement ---
# Permet a os.getenv("GROQ_API_KEY") etc. de fonctionner sans rien changer
# dans les autres modules (brain.py, audio.py, asset_manager.py...).
for key in ["GROQ_API_KEY", "GEMINI_API_KEY", "OPENAI_API_KEY"]:
    if key in st.secrets:
        os.environ[key] = st.secrets[key]

# --- DEBUG TEMPORAIRE : a retirer une fois le probleme confirme/resolu ---
st.write("Groq présent dans st.secrets :", "GROQ_API_KEY" in st.secrets)
st.write("Gemini présent dans st.secrets :", "GEMINI_API_KEY" in st.secrets)
st.write("Groq présent dans os.environ :", "GROQ_API_KEY" in os.environ)
st.write("Gemini présent dans os.environ :", "GEMINI_API_KEY" in os.environ)
# --- FIN DEBUG ---



def estimate_scene_count(duration_target):
    return max(6, min(14, round(duration_target / 5)))



def generate_word_by_word_srt(text, duration, output_path):
    words = text.split()
    if not words:
        return None


    per_word = duration / len(words)
    lines = []


    for i, word in enumerate(words):
        start = i * per_word
        end = start + per_word


        def fmt(t):
            h = int(t // 3600)
            m = int((t % 3600) // 60)
            s = t % 60
            return f"{h:02d}:{m:02d}:{s:06.3f}".replace(".", ",")


        lines.append(f"{i + 1}\n{fmt(start)} --> {fmt(end)}\n{word}\n")


    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


    return output_path



async def run_pipeline(topic_input, duration_target, refine_angle, progress_bar, status_placeholder):
    brain = ContentBrain()


    def update(pct, msg):
        progress_bar.progress(pct)
        status_placeholder.info(msg)


    update(0.05, "🧠 Recherche / preparation du sujet...")
    if topic_input and topic_input.strip():
        topic = topic_input.strip()
        if refine_angle:
            update(0.10, "🔧 Reformulation de l'angle du sujet...")
            topic = brain.refine_topic_angle(topic)
    else:
        topic = brain.get_trending_topic()


    scene_count = estimate_scene_count(duration_target)


    update(0.15, f"📝 Ecriture du script ({scene_count} scenes visees)...")
    script = brain.generate_script_with_target(topic, scene_count)


    update(0.35, "🗣️ Generation des voix off...")
    audio_engine = AudioEngine()
    script = await audio_engine.process_script(script)


    update(0.50, "💬 Generation des sous-titres...")
    subs_dir = os.path.join(os.getcwd(), "assets", "temp", "subs")
    os.makedirs(subs_dir, exist_ok=True)


    for scene in script:
        srt_path = os.path.join(subs_dir, f"scene_{scene['id']}.srt")
        scene["srt_path"] = generate_word_by_word_srt(scene["text"], scene["duration"], srt_path)


    update(0.65, "🎨 Generation des visuels IA...")
    asset_manager = AssetManager()
    assets_map = asset_manager.get_videos(script)


    update(0.80, "🎞️ Montage des scenes...")
    composer = Composer()
    final_scene_paths = composer.render_all_scenes(script, assets_map)


    if not final_scene_paths:
        return None, topic


    update(0.90, "🔗 Assemblage final avec transitions et musique...")
    final_path = composer.concatenate_with_transitions(final_scene_paths)


    update(1.0, "✅ Termine !")
    return final_path, topic



st.set_page_config(
    page_title="Generateur de Videos IA",
    page_icon="🎬",
    layout="wide"
)


st.markdown("""
<style>
.main .block-container {
    max-width: 1200px;
    padding-top: 2rem;
}
.stButton > button {
    height: 3.2rem;
    font-size: 1.1rem;
    font-weight: 600;
    border-radius: 10px;
}
div[data-testid="stVerticalBlockBorderWrapper"] {
    border-radius: 16px;
}
</style>
""", unsafe_allow_html=True)


st.title("🎬 Generateur de Videos IA")
st.caption("Cree une video courte a partir d'un sujet, ou laisse l'IA en choisir un.")


col_left, col_right = st.columns([5, 6], gap="large")


with col_left:
    with st.container(border=True):
        st.subheader("1. Sujet")


        topic_input = st.text_area(
            "Sujet de la video",
            placeholder="Colle un trend TikTok repere (ex: pourquoi les avions evitent l'Antarctique...), ou laisse vide pour un sujet choisi par l'IA",
            height=140
        )


        refine_angle = st.checkbox(
            "Laisser l'IA reformuler ce sujet en angle accrocheur avant d'ecrire le script",
            value=True,
            help="Utile si tu colles un trend brut ou vague repere sur TikTok"
        )


        st.subheader("2. Duree")


        duration_target = st.slider(
            "Duree souhaitee de la video (en secondes)",
            min_value=20, max_value=90, value=45, step=5
        )


        generate_clicked = st.button("🚀 Generer la video", type="primary", use_container_width=True)


with col_right:
    with st.container(border=True):
        st.subheader("Resultat")
        video_placeholder = st.empty()
        download_placeholder = st.empty()


if generate_clicked:
    with col_left:
        progress_bar = st.progress(0.0)
        status_placeholder = st.empty()


    try:
        final_path, used_topic = asyncio.run(
            run_pipeline(topic_input, duration_target, refine_angle, progress_bar, status_placeholder)
        )
    except Exception as e:
        st.error(f"❌ La generation a echoue : {e}")
        st.stop()


    if not final_path or not os.path.exists(final_path):
        st.error("❌ La generation a echoue. Verifie les logs / cles API.")
        st.stop()


    status_placeholder.success(f"✅ Video generee pour le sujet : {used_topic}")


    with col_right:
        video_placeholder.video(final_path)
        with open(final_path, "rb") as f:
            download_placeholder.download_button(
                "⬇️ Telecharger la video",
                data=f,
                file_name=os.path.basename(final_path),
                mime="video/mp4",
                use_container_width=True
            )