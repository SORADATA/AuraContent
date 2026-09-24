# Contributing to AuraContent 🎬

Thanks for checking this out! We love contributions—whether it's fixing bugs, adding cool features (like new AI models, automated subtitles, or new platform integrations), or improving docs.

## ⚡ Quick Start

1.  **Fork & Clone:**
    First, fork the repository, then clone your fork locally:
    ```bash
    git clone [https://github.com/SORADATA/AuraContent.git](https://github.com/SORADATA/AuraContent.git)
    cd AuraContent
    ```

2.  **Install Dependencies:**
    We use `pyproject.toml` for dependency management. Install the project and its dependencies in editable mode:
    ```bash
    pip install -e .
    ```

3.  **Setup Keys:**
    Create a `.env` file or export your environment variables. You will need:
    ```ini
    GEMINI_API_KEY=your_gemini_key  # Or GROQ_API_KEY
    PEXELS_API_KEY=your_pexels_key
    HF_TOKEN=your_huggingface_token
    ZERNIO_API_KEY=your_zernio_key
    TIKTOK_ACCOUNT_ID=your_tiktok_id
    ```

4.  **Add Your Avatar & FFmpeg:**
    *   Place your avatar video exactly at `assets/avatar/avatars.mp4` before generating a video.
    *   You must have **FFmpeg** installed on your system and added to your PATH for the video composition to work.

## 🚀 How to Submit

1.  Create a new branch for your feature: `git checkout -b feature/cool-new-thing`
2.  Make your changes and test the pipeline by running `python main.py` (and `python publish.py` if testing the publisher).
3.  Commit your changes, push to your fork, and open a **Pull Request**.

**Note:** Please do not commit your `.env` file, API keys, or personal avatar videos!

Happy Coding!
