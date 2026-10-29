"""
Prompts du RAG juridique BAM — version fluide et répondante.
"""

SYSTEM_PROMPT = """Tu es un expert juridique spécialisé dans la réglementation bancaire marocaine et les textes de Bank Al-Maghrib.

Ton rôle : analyser les passages fournis et rédiger une réponse claire, structurée et utile.

INSTRUCTIONS :
- Utilise UNIQUEMENT les informations des passages fournis. Ne les ignore pas, même si tu penses qu'ils sont insuffisants.
- Si un passage contient une information pertinente, même partielle, exploite-la.
- Rédige en français fluide et professionnel, comme un juriste qui explique à un confrère.
- Structure ta réponse avec des paragraphes clairs. Tu peux utiliser des listes si pertinent.
- Cite les articles et textes entre guillemets quand tu reprends du texte verbatim.
- Indique toujours la source : (Article X, [Titre du texte]).
- Si les passages sont vraiment insuffisants pour répondre à la question précise, dis-le en une phrase courte, puis présente quand même ce que tu as trouvé d'approchant.
- Ne dis JAMAIS "je suis désolé, je ne peux pas répondre" si tu as des passages. Exploite-les.
- N'invente aucun chiffre, date, ou article qui n'est pas dans les passages.
- Termine par une ligne séparée : **Sources :** puis la liste des documents utilisés."""

INSUFFICIENT_SOURCES_MESSAGE = (
    "Les documents indexés ne contiennent pas d'information directement pertinente "
    "pour cette question. Consultez les textes officiels sur "
    "**[bkam.ma](https://www.bkam.ma/Supervision-bancaire/"
    "Recueil-des-textes-legislatifs-et-reglementaires)**."
)

CONTRADICTION_WARNING = (
    "⚠️ Plusieurs passages présentent des informations potentiellement différentes. "
    "Vérifiez la date et la version de chaque texte."
)


def build_rag_prompt(question: str, context_passages: list[dict]) -> str:
    if not context_passages:
        return (
            f"Question : {question}\n\n"
            "[Aucun passage trouvé.]\n"
            "Réponds que tu n'as pas trouvé d'information pertinente dans les documents indexés."
        )

    passages_text = ""
    for i, p in enumerate(context_passages, 1):
        cit = p.get("citation", {})
        parts = []
        if cit.get("article"):
            parts.append(cit["article"])
        if cit.get("title"):
            parts.append(cit["title"])
        if cit.get("page"):
            parts.append(f"p.{cit['page']}")
        ref = " | ".join(parts) if parts else f"Passage {i}"
        passages_text += f"\n[PASSAGE {i} — {ref}]\n{p['text']}\n"

    return (
        f"Voici les passages extraits des textes officiels de Bank Al-Maghrib :\n"
        f"{passages_text}\n"
        f"---\n"
        f"Question : {question}\n\n"
        f"Rédige une réponse complète et fluide basée sur ces passages."
    )
