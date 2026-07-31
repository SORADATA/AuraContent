import os
import shutil


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