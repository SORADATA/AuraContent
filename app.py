import subprocess
import os
import shutil

def get_duration(path):
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", path],
        capture_output=True, text=True
    )
    return float(result.stdout.strip())

def fusionner_deux_clips(clip_a, clip_b, sortie, duree_transition=0.5):
    duree_a = get_duration(clip_a)
    offset = max(duree_a - duree_transition, 0)

    filter_complex = (
        f"[0:v][1:v]xfade=transition=fade:duration={duree_transition}:offset={offset}[v];"
        f"[0:a][1:a]acrossfade=d={duree_transition}[a]"
    )
    cmd = [
        "ffmpeg", "-y",
        "-i", clip_a,
        "-i", clip_b,
        "-filter_complex", filter_complex,
        "-map", "[v]", "-map", "[a]",
        "-c:v", "libx264", "-crf", "18", "-preset", "medium",
        "-c:a", "aac",
        sortie
    ]
    subprocess.run(cmd, check=True, capture_output=True, text=True)

def monter_video_en_cascade(liste_scenes, dossier_temp, duree_transition=0.5):
    if len(liste_scenes) == 1:
        return liste_scenes[0]

    courant = liste_scenes[0]
    for i in range(1, len(liste_scenes)):
        suivant = liste_scenes[i]
        sortie = os.path.join(dossier_temp, f"merge_step_{i}.mp4")
        fusionner_deux_clips(courant, suivant, sortie, duree_transition)
        if i > 1:
            os.remove(courant)
        courant = sortie
    return courant


# ------------------------------------------------------------------
# Bloc à insérer à la place de votre ancienne commande ffmpeg unique
# (celle qui listait les 12 scenes en -i et un seul filter_complex
# avec 12 xfade/acrossfade enchaines)
# ------------------------------------------------------------------

base_dir = os.path.dirname(os.path.abspath(__file__))
dossier_temp = os.path.join(base_dir, "assets", "temp")
os.makedirs(dossier_temp, exist_ok=True)

nb_scenes = 12  # adaptez selon le nombre réel généré par votre script
chemins_scenes = [
    os.path.join(dossier_temp, f"scene{i}.mp4")
    for i in range(1, nb_scenes + 1)
    if os.path.exists(os.path.join(dossier_temp, f"scene{i}.mp4"))
]

video_finale_path = monter_video_en_cascade(chemins_scenes, dossier_temp, duree_transition=0.5)

final_output_path = os.path.join(dossier_temp, "final_short.mp4")
shutil.move(video_finale_path, final_output_path)

for i in range(1, nb_scenes + 1):
    p = os.path.join(dossier_temp, f"scene{i}.mp4")
    if os.path.exists(p) and p != final_output_path:
        os.remove(p)

with open(final_output_path, "rb") as f:
    video_bytes = f.read()

st.video(video_bytes)
st.download_button("Télécharger le short", video_bytes, "final_short.mp4", mime="video/mp4")

os.remove(final_output_path)