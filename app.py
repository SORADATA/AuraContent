import gradio as gr
import asyncio
import os
from modules.brain import ContentBrain
from modules.asset_manager import AssetManager
from modules.audio import AudioEngine
from modules.composer import Composer


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


async def run_pipeline(topic_input, duration_target, refine_angle, progress_callback):
    brain = ContentBrain()

    progress_callback(0.05, "🧠 Recherche / preparation du sujet...")
    if topic_input and topic_input.strip():
        topic = topic_input.strip()
        if refine_angle:
            progress_callback(0.10, "🔧 Reformulation de l'angle du sujet...")
            topic = brain.refine_topic_angle(topic)
    else:
        topic = brain.get_trending_topic()

    scene_count = estimate_scene_count(duration_target)

    progress_callback(0.15, f"📝 Ecriture du script ({scene_count} scenes visees)...")
    script = brain.generate_script_with_target(topic, scene_count)

    progress_callback(0.35, "🗣️ Generation des voix off...")
    audio_engine = AudioEngine()
    script = await audio_engine.process_script(script)

    progress_callback(0.50, "💬 Generation des sous-titres...")
    subs_dir = os.path.join(os.getcwd(), "assets", "temp", "subs")
    os.makedirs(subs_dir, exist_ok=True)

    for scene in script:
        srt_path = os.path.join(subs_dir, f"scene_{scene['id']}.srt")
        scene["srt_path"] = generate_word_by_word_srt(scene["text"], scene["duration"], srt_path)

    progress_callback(0.65, "🎨 Generation des visuels IA...")
    asset_manager = AssetManager()
    assets_map = asset_manager.get_videos(script)

    progress_callback(0.80, "🎞️ Montage des scenes...")
    composer = Composer()
    final_scene_paths = composer.render_all_scenes(script, assets_map)

    if not final_scene_paths:
        return None, topic

    progress_callback(0.90, "🔗 Assemblage final avec transitions et musique...")
    final_path = composer.concatenate_with_transitions(final_scene_paths)

    progress_callback(1.0, "✅ Termine !")
    return final_path, topic


def generate_video(topic_input, duration_target, refine_angle, progress=gr.Progress()):
    def progress_callback(percent, message):
        progress(percent, desc=message)

    try:
        final_path, used_topic = asyncio.run(
            run_pipeline(topic_input, duration_target, refine_angle, progress_callback)
        )
    except Exception as e:
        raise gr.Error(f"❌ La generation a echoue : {e}")

    if not final_path or not os.path.exists(final_path):
        raise gr.Error("❌ La generation a echoue. Verifie les logs / cles API.")

    status = f"✅ Video generee pour le sujet : {used_topic}"
    return final_path, final_path, status


CUSTOM_CSS = """
.gradio-container {
    max-width: 1200px !important;
    margin: auto !important;
}
#header {
    text-align: center;
    padding: 24px 16px 8px 16px;
}
#header h1 {
    font-size: 2rem;
    margin-bottom: 4px;
}
#header p {
    color: var(--body-text-color-subdued);
    font-size: 1rem;
    margin-top: 0;
}
.card {
    background: var(--block-background-fill);
    border: 1px solid var(--border-color-primary);
    border-radius: 16px;
    padding: 20px;
}
#topic_box textarea {
    font-size: 1.05rem !important;
    min-height: 110px !important;
}
#generate_btn {
    height: 52px;
    font-size: 1.1rem !important;
    font-weight: 600 !important;
}
#status_box {
    text-align: center;
    font-size: 1rem;
    padding-top: 4px;
}
"""

with gr.Blocks(title="Generateur de Videos IA", theme=gr.themes.Soft(primary_hue="violet"), css=CUSTOM_CSS) as demo:

    with gr.Column(elem_id="header"):
        gr.Markdown("# 🎬 Generateur de Videos IA")
        gr.Markdown("Cree une video courte a partir d'un sujet, ou laisse l'IA en choisir un.")

    with gr.Row(equal_height=False):
        with gr.Column(scale=5, elem_classes="card"):
            gr.Markdown("### 1. Sujet")

            topic_input = gr.Textbox(
                label="Sujet de la video",
                placeholder="Colle un trend TikTok repere (ex: pourquoi les avions evitent l'Antarctique...), ou laisse vide pour un sujet choisi par l'IA",
                lines=4,
                elem_id="topic_box"
            )

            refine_angle = gr.Checkbox(
                label="Laisser l'IA reformuler ce sujet en angle accrocheur avant d'ecrire le script",
                value=True,
                info="Utile si tu colles un trend brut ou vague repere sur TikTok"
            )

            gr.Markdown("### 2. Duree")

            duration_target = gr.Slider(
                label="Duree souhaitee de la video (en secondes)",
                minimum=20, maximum=90, value=45, step=5
            )

            generate_btn = gr.Button("🚀 Generer la video", variant="primary", elem_id="generate_btn")
            status_text = gr.Markdown("", elem_id="status_box")

        with gr.Column(scale=6, elem_classes="card"):
            gr.Markdown("### Resultat")
            video_output = gr.Video(label="Video generee")
            download_output = gr.File(label="⬇️ Telecharger la video")

    generate_btn.click(
        fn=generate_video,
        inputs=[topic_input, duration_target, refine_angle],
        outputs=[video_output, download_output, status_text]
    )


if __name__ == "__main__":
    root_path = os.environ.get("GRADIO_ROOT_PATH", "")

    demo.queue().launch(
        server_name="0.0.0.0",
        server_port=7860,
        root_path=root_path,
        show_error=True
    )