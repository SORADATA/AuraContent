# Gloables variables

API_URL = "https://huggingface.co/api/datasets/soradata/AIShortvideos/tree/main/videos"
DIRECT_URL = "https://huggingface.co/datasets/soradata/AIShortvideos/resolve/main/"
API_URL_FINANCE = "https://huggingface.co/api/datasets/soradata/ai_videos_Finance/tree/main/videos"
DIRECT_URL_FINANCE = "https://huggingface.co/datasets/soradata/ai_videos_Finance/resolve/main/"

# 🛠️ NOMS DE MODÈLES
GEMINI_MODEL = "gemini-3.6-flash"
#GROQ_MODEL = "openai/gpt-oss-120b"
#GROQ_MODEL = "llama3-70b-8192"

# ============================================================
# OPENROUTER FALLBACKS
# ============================================================

OPENROUTER_FALLBACK_MODEL_1 = "meta-llama/llama-3.3-70b-instruct"

OPENROUTER_FALLBACK_MODEL_2 = "google/gemma-3-27b-it:free"


# ============================================================
# CONFIGURATION BRAIN
# ============================================================

BRAIN_MAX_RETRIES_PER_PROVIDER = 2

BRAIN_RETRY_DELAY = 1.5

BRAIN_PROVIDER_COOLDOWN = 30

BRAIN_HARD_TOKEN_CAP = 7500

BRAIN_SAFETY_MARGIN_TOKENS = 400
