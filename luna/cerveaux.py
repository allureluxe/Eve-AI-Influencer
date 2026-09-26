"""Les cerveaux consultes par l'Agent Alluxe : ChatGPT et Claude.

CE QUE CE MODULE EST, ET SURTOUT CE QU'IL N'EST PAS

Il expose deux fonctions qui posent une question et rendent du TEXTE.
Rien d'autre. Pas d'outils, pas d'acces au VPS, pas de cles Bitvavo,
pas de Supabase, pas de fichiers.

C'est la piece centrale de la securite, et elle est structurelle et non
declarative. Un cerveau qui n'a aucun outil ne PEUT PAS desarmer un
garde-fou, vider un compte ou contourner une limite de risque — quoi
qu'on lui ecrive, et quoi qu'il reponde. Il n'a pas de mains.

    Agent  --> question (texte)   -->  ChatGPT / Claude
    Agent  <-- analyse (texte)    <--
    Agent  --> decide, agit, verifie, journalise

L'Agent reste le seul a executer quoi que ce soit. C'est exactement
l'architecture demandee par l'operateur le 26 septembre : « ChatGPT et
Claude ne doivent pas etre deux agents concurrents qui prennent
directement le controle du VPS. Ils doivent etre des cerveaux appeles
par Alluxe Agent. »

POURQUOI DEUX ET PAS UN. Deux modeles independants se trompent rarement
de la meme facon. Sur une decision qui engage de l'argent, une seconde
analyse qui contredit la premiere est le signal le plus utile qu'on
puisse avoir — et ce depot en a l'usage : son CLAUDE.md recense sept
fois le meme piege, une formule juste dans un cadre et fausse dans un
autre, plausible des deux cotes.

CE QUE CE MODULE NE FAIT PAS NON PLUS : il ne decide pas. `consulter`
rend les deux reponses cote a cote, sans les fusionner. Une synthese
automatique masquerait justement le desaccord, qui est toute la valeur
de la manoeuvre.
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

from .moteurs import ENTETE_NAVIGATEUR, ErreurMoteur

#: Le cadre donne aux deux cerveaux. Il dit ce qu'ils sont et ce qu'ils
#: ne sont pas — utile parce qu'un modele a qui l'on demande une action
#: a tendance a repondre comme s'il allait l'executer.
CADRE = (
    "Tu es consulte comme expert par un agent logiciel appele Alluxe "
    "Agent, qui pilote un robot de trading en argent reel et une "
    "influenceuse virtuelle. Tu n'as AUCUN outil et AUCUN acces : tu ne "
    "peux ni lire ni modifier de fichier, ni executer de commande. Tu "
    "rends une analyse, l'agent decide et agit.\n"
    "Reponds en francais, de facon dense et concrete. Si l'information "
    "manque pour trancher, dis-le et nomme ce qui manque plutot que de "
    "supposer. Si tu penses que l'action envisagee est risquee, dis-le "
    "en premier."
)

DELAI = 90


class CerveauErreur(RuntimeError):
    pass


def _poster(url: str, corps: dict, entetes: dict) -> dict:
    requete = urllib.request.Request(
        url, data=json.dumps(corps).encode("utf-8"),
        headers={**entetes, **ENTETE_NAVIGATEUR}, method="POST")
    try:
        with urllib.request.urlopen(requete, timeout=DELAI) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "replace")[:400]
        raise CerveauErreur(f"HTTP {e.code} : {detail}") from e
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        raise CerveauErreur(f"reseau : {e}") from e


def _cle(nom: str) -> str:
    """Une cle d'environnement, ou rien si elle n'a jamais ete remplie."""
    v = os.getenv(nom, "").strip()
    return "" if v.lower().startswith("your_") else v


def chatgpt_disponible() -> bool:
    return bool(_cle("OPENAI_API_KEY"))


def claude_disponible() -> bool:
    return bool(_cle("ANTHROPIC_API_KEY"))


def demander_chatgpt(question: str, contexte: str = "",
                     max_jetons: int = 1200) -> str:
    """Une analyse de ChatGPT. Rend du texte, rien d'autre.

    `max_jetons` — voir `demander_claude` : une question longue qui
    demande une reponse structuree a besoin de place.
    """
    cle = _cle("OPENAI_API_KEY")
    if not cle:
        raise CerveauErreur("OPENAI_API_KEY absente")
    modele = os.getenv("CERVEAU_MODELE_CHATGPT", "gpt-5")
    contenu = f"{contexte}\n\n{question}".strip() if contexte else question
    rep = _poster(
        "https://api.openai.com/v1/chat/completions",
        {"model": modele,
         "messages": [{"role": "system", "content": CADRE},
                      {"role": "user", "content": contenu}],
         "max_completion_tokens": max_jetons},
        {"content-type": "application/json",
         "authorization": f"Bearer {cle}"})
    try:
        texte = rep["choices"][0]["message"]["content"].strip()
    except (KeyError, IndexError, AttributeError, TypeError) as e:
        raise CerveauErreur(f"reponse inattendue : {str(rep)[:200]}") from e
    if not texte:
        raise CerveauErreur("reponse vide")
    return texte


def demander_claude(question: str, contexte: str = "",
                    max_jetons: int = 1200) -> str:
    """Une analyse de Claude. Rend du texte, rien d'autre.

    `max_jetons` COMPTE LA REFLEXION, ET C'EST LE PIEGE. Le modele
    produit un bloc « thinking » avant son texte ; sur une question
    longue qui demande du JSON structure, ce bloc consomme le budget
    et le bloc texte ressort VIDE — avec un `stop_reason: end_turn`
    parfaitement normal, donc sans rien qui signale le probleme.

    Constate le 26 septembre sur la recherche du labo : les deux
    cerveaux rendaient « reponse vide » alors qu'ils avaient
    parfaitement compris la question.
    """
    cle = _cle("ANTHROPIC_API_KEY")
    if not cle:
        raise CerveauErreur("ANTHROPIC_API_KEY absente")
    modele = os.getenv("CERVEAU_MODELE_CLAUDE", "claude-sonnet-5")
    contenu = f"{contexte}\n\n{question}".strip() if contexte else question
    rep = _poster(
        "https://api.anthropic.com/v1/messages",
        {"model": modele, "max_tokens": max_jetons, "system": CADRE,
         "messages": [{"role": "user", "content": contenu}]},
        {"content-type": "application/json", "x-api-key": cle,
         "anthropic-version": "2023-06-01"})
    texte = "".join(b.get("text", "") for b in rep.get("content", [])
                    if b.get("type") == "text").strip()
    if not texte:
        raise CerveauErreur(f"reponse vide : {str(rep)[:200]}")
    return texte


CERVEAUX = {"chatgpt": demander_chatgpt, "claude": demander_claude}


def consulter(question: str, contexte: str = "",
              lesquels: tuple[str, ...] = ("chatgpt", "claude"),
              max_jetons: int = 1200) -> dict:
    """Interroge plusieurs cerveaux et rend leurs reponses COTE A COTE.

    IL NE FAIT PAS LA SYNTHESE, et c'est deliberе. Fusionner les deux
    reponses en une seule masquerait le desaccord — or le desaccord est
    exactement ce qu'on vient chercher. Deux modeles independants se
    trompent rarement de la meme facon ; quand ils divergent, c'est le
    signal le plus utile disponible avant d'engager de l'argent.

    La synthese appartient a l'Agent, qui seul connait l'etat reel du
    systeme et les garde-fous en vigueur.

    Un cerveau injoignable n'interrompt pas les autres : son erreur est
    rendue a sa place. Une analyse vaut mieux que zero.
    """
    resultats: dict[str, dict] = {}
    for nom in lesquels:
        fonction = CERVEAUX.get(nom)
        if fonction is None:
            resultats[nom] = {"ok": False, "erreur": f"cerveau inconnu : {nom}"}
            continue
        try:
            resultats[nom] = {"ok": True,
                              "reponse": fonction(question, contexte,
                                                  max_jetons)}
        except (CerveauErreur, ErreurMoteur) as e:
            resultats[nom] = {"ok": False, "erreur": str(e)[:300]}
    return resultats


def resume_consultation(resultats: dict) -> str:
    """Les avis mis en forme pour l'Agent, avec leur origine nommee.

    L'origine compte : un agent qui ne sait plus qui a dit quoi ne peut
    pas peser un desaccord.
    """
    morceaux = []
    for nom, r in resultats.items():
        titre = {"chatgpt": "ChatGPT", "claude": "Claude"}.get(nom, nom)
        if r.get("ok"):
            morceaux.append(f"--- AVIS DE {titre.upper()} ---\n{r['reponse']}")
        else:
            morceaux.append(f"--- {titre.upper()} INJOIGNABLE ---\n{r['erreur']}")
    return "\n\n".join(morceaux) if morceaux else "aucun cerveau consulte"
