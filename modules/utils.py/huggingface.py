import os
from datetime import datetime
from huggingface_hub import HfApi


def upload_to_huggingface(video_path: str, topic: str) -> bool:
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

    try:
        api.upload_file(
            path_or_fileobj=video_path,
            path_in_repo=remote_filename,
            repo_id=repo_id,
            repo_type="dataset",
            commit_message=f"Add generated short: {safe_topic}"
        )
        print(f"✅ Video uploadee sur Hugging Face : {repo_id}/{remote_filename}")
        return True
    except Exception as e:
        print(f"❌ Echec upload Hugging Face : {e}")
        return False