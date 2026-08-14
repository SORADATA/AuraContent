import os
import requests

# 🛠️ NOMS DE MODÈLES
GEMINI_CAPTION_MODEL = "gemini-1.5-flash"
GROQ_CAPTION_MODEL = "llama-3.3-70b-versatile"


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
