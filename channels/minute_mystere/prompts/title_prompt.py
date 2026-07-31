MINUTE_MYSTERE_TITLE_PROMPT = """
Génère 5 titres pour Minute Mystère.

Contraintes :
- intrigue immédiate
- court et clair
- pas de mensonge clickbait
- fort potentiel de curiosité
- moins de 70 caractères
""".strip()


def build_prompt() -> str:
    return MINUTE_MYSTERE_TITLE_PROMPT