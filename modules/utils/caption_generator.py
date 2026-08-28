import os
import requests
from constants import OPENROUTER_FALLBACK_MODEL_1, OPENROUTER_FALLBACK_MODEL_2


def generate_caption_with_openrouter(prompt_legende, model_name):
    openrouter_key = os.getenv("OPENROUTER_API_KEY")
    if not openrouter_key:
        raise ValueError("Clé OPENROUTER_API_KEY introuvable.")

    headers = {
        "Authorization": f"Bearer {openrouter_key}",
        "Content-Type": "application/json",
    }
    
    payload = {
        "model": model_name,
        "messages": [{"role": "user", "content": prompt_legende}],
    }

    response = requests.post(
        "https://openrouter.ai/api/v1/chat/completions",
        headers=headers,
        json=payload,
        timeout=30,
    )
    response.raise_for_status()

    text = response.json()["choices"][0]["message"]["content"].strip()
    if not text:
        raise ValueError(f"Réponse OpenRouter ({model_name}) vide.")
    return text


def generate_caption(full_text, video_title):
    # 📌 PROMPT V3 : Optimisé pour la rétention, l'engagement et le mystère
    prompt_legende = f"""
Voici le texte exact d'un court documentaire mystère ({video_title}) :
"{full_text}"

Rédige une légende ultra-captivante pour TikTok/Shorts.
RÈGLES STRICTES DE RÉTENTION :
1. 1ère ligne très accrocheuse avec un emoji, qui agit comme un "Hook" textuel.
2. 1 ou 2 phrases courtes pour teaser le contenu, MAIS TU DOIS GARDER LE MYSTÈRE INTACT. Ne révèle SURTOUT PAS la conclusion, le twist ou le secret final de l'histoire.
3. Termine par une question courte pour inciter aux commentaires et prolonger la curiosité (ex: "Et toi, tu y crois ?").
4. Interdiction de demander de s'abonner (pas de "Abonne-toi").
5. Ajoute 4 hashtags pertinents dont #MinuteMystère.
Ne mets pas de guillemets autour de ta réponse.
"""

    # 📌 FALLBACK V3 : Plus dramatique et mystérieux
    fallback = f"{video_title} 🧠✨ L'histoire qu'ils ont essayé d'effacer... #MinuteMystère #HistoireVraie #Pourtoi #Secretscachés"

    try:
        print(f"🧠 Tentative de génération de la légende avec {OPENROUTER_FALLBACK_MODEL_1}...")
        return generate_caption_with_openrouter(prompt_legende, OPENROUTER_FALLBACK_MODEL_1)
    except Exception as e_llama:
        print(f"⚠️ Échec avec Llama ({e_llama}). Basculement sur Gemma...")

    try:
        print(f"🚀 Tentative de génération de la légende avec {OPENROUTER_FALLBACK_MODEL_2}...")
        return generate_caption_with_openrouter(prompt_legende, OPENROUTER_FALLBACK_MODEL_2)
    except Exception as e_gemma:
        print(f"⚠️ Échec avec Gemma également ({e_gemma}). Utilisation de la légende de secours.")
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