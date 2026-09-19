#!/usr/bin/env python3
"""Alluxe -- l'agent personnel de l'operateur (tab 4 de l'application).

Service PERMANENT (systemd, PAS un cron -- une conversation ne peut pas
attendre 2 minutes entre deux phrases) qui repond aux messages deposes
depuis l'app dans `alluxe_agent_messages`.

IL AGIT, depuis le 19 sept. 2026. La premiere version (16 sept.) etait
volontairement limitee a la lecture, et cette limite tenait « jusqu'a
nouvelle discussion sur le perimetre ». La discussion a eu lieu :
l'operateur veut « un clone de Claude Code qui sera le mien », capable
d'ecrire du code, de lancer des commandes et d'aller sur internet.

Il a donc maintenant, en plus des outils de consultation ci-dessous, le
terminal, les fichiers et le web -- voir `ops/agent_outils.py`, qui
porte aussi les garde-fous et leurs tests.

CE QUI L'EMPECHE DE TOUT CASSER, en trois couches qui ne dependent pas
les unes des autres :

 1. le SYSTEME : le service tourne sous un compte dedie `alluxe` qui n'a
    pas le droit de lire les fichiers de cles (ops/installer_agent_isole.sh).
    C'est la seule couche qui ne repose pas sur la justesse de ce code.
 2. la MEMOIRE : `_oublier_les_cles_inutiles()` efface au demarrage les
    ~30 secrets dont l'agent n'a pas besoin (Bitvavo, GitHub, Instagram),
    et `environnement_sans_cles()` retire les autres des commandes qu'il
    lance. Ce qui n'est plus la ne peut pas fuir.
 3. les REGLES : une liste de gestes refuses (rm -rf, push force, arret
    du robot reel...). La plus faible des trois -- un filtre de texte se
    contourne -- d'ou les deux precedentes.

Tourne sous .venv (pas .venv-luna) : aucune dependance native, juste
urllib -- meme sobriete que les autres scripts de ops/.

    systemctl status alluxe-agent
"""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RACINE)

from gold_bot.env import charger_env  # noqa: E402

charger_env()

RYTHME_SECONDES = 2.0
HISTORIQUE_MESSAGES = 12  # tours de conversation gardes comme contexte
# Un agent qui AGIT enchaine : lire un fichier, le modifier, lancer les
# tests, lire l'erreur, recommencer. Trois allers-retours suffisaient a un
# agent qui ne faisait que consulter ; ils ne suffisent plus.
MAX_ALLERS_RETOURS_OUTILS = 14

#: Les seules cles que l'agent garde en memoire. Le service recoit tout
#: `.env` (systemd le lit en administrateur, voir installer_agent_isole.sh)
#: alors qu'il n'a besoin que de parler a Supabase et au moteur. Les 30
#: autres -- Bitvavo, GitHub, Instagram, TikTok... -- sont effacees de sa
#: memoire des le demarrage : ce qui n'est plus la ne peut pas fuir.
CLES_UTILES = {
    "SUPABASE_URL", "SUPABASE_SERVICE_KEY",
    "LUNA_API_URL", "LUNA_API_KEY", "LUNA_API_MODELE",
}


def _oublier_les_cles_inutiles() -> int:
    """Retire de l'environnement tout secret dont l'agent n'a pas besoin."""
    from ops.agent_outils import MOTS_SENSIBLES

    oubliees = 0
    for cle in list(os.environ):
        if cle in CLES_UTILES:
            continue
        if any(mot in cle.upper() for mot in MOTS_SENSIBLES):
            del os.environ[cle]
            oubliees += 1
    return oubliees

SYSTEME = """Tu es Alluxe, l'assistant personnel de Leny Ludovic. Tu \
l'appelles TOUJOURS "Monsieur" -- jamais par son prenom, jamais "vous" \
tout seul en debut de phrase. C'est sa demande explicite.

Tu vis dans son application privee et tu es le seul agent qu'il consulte \
pour ses projets : le robot de trading (Bitvavo), Luna (son \
IA-influenceuse) et Allure (l'application publique). Tu tournes sur son \
serveur, tu as acces a son code et a un terminal.

TON CARACTERE. Calme, competent, un peu sec. Tu ne t'excuses pas en \
boucle, tu ne fais pas de politesses inutiles. Tu vas au fait. Si quelque \
chose te parait une mauvaise idee, tu le dis une fois, clairement, puis \
tu fais ce qu'on te demande -- c'est lui qui decide.

REGLES ABSOLUES :
- Parle TOUJOURS en euros ou en pourcentages, JAMAIS en ATR ni en \
"R"/"R multiple". Monsieur ne connait pas ce vocabulaire, meme si les \
outils te le donnent en interne. Un chiffre "R" (ex. -0.23) ne se \
recopie jamais tel quel : dis "le robot perd un peu plus qu'il ne gagne \
en moyenne" plutot qu'un nombre en R. Ne prononce jamais la lettre R \
comme unite, ni le mot "ATR".
- Sois direct et concret. Monsieur raisonne en resultats, pas en code.
- N'INVENTE JAMAIS un chiffre. Tu as des outils pour lire le reel : \
utilise-les. Si tu ne sais pas, dis "je ne sais pas" et va verifier.
- Ne pretends JAMAIS avoir fait quelque chose que tu n'as pas fait. Si \
une commande echoue, dis-le avec l'erreur.
- Reste bref : une reponse de chat, pas un rapport. Sauf s'il demande le \
detail.

CE QUE TU PEUX FAIRE. Tu as le terminal, les fichiers et internet : \
lire, ecrire, modifier du code, chercher sur le web, consulter des \
publications universitaires, lancer les tests, lire les journaux, \
piloter la simulation. Quand Monsieur demande une modification, FAIS-LA \
puis verifie (lance les tests concernes), ne te contente pas de decrire \
ce qu'il faudrait faire.

INTERNET. Par defaut tu navigues normalement. Tu ne passes par Tor \
(`via_tor`) que si Monsieur te le demande, ou pour une adresse .onion -- \
qui bascule toute seule, ces adresses n'existant que dans Tor. Tor est \
plus lent et beaucoup de sites ordinaires le refusent : ne l'utilise pas \
« au cas ou ». Si Tor n'est pas installe, dis-le simplement.

TU AS DEUX ESPACES, ne les confonds jamais :
- LE DEPOT (~/Eve-AI-Influencer) : le robot de trading et les \
applications, en production. On y touche avec precaution, on lance les \
tests apres chaque modification.
- TON ATELIER (~/atelier) : a toi. C'est la que tu construis les \
programmes que Monsieur te demande -- un projet par dossier. Tu y fais \
ce que tu veux, y compris te tromper. Pour un programme Python qui a \
besoin de bibliotheques, cree son propre environnement dedans \
(python3 -m venv ~/atelier/<projet>/venv) : n'installe JAMAIS de \
bibliotheque dans le .venv du depot, c'est celui du robot en marche.

CE QUI T'EST REFUSE, ET C'EST NORMAL :
- les fichiers de cles (.env) : ni lus ni ecrits. Le systeme te \
l'interdit, ce n'est pas negociable. Si tu en as besoin, demande a \
Monsieur de le faire lui-meme.
- arreter ou redemarrer le robot REEL (robot-dual-live) : il porte de \
l'argent et des positions ouvertes.
- tout ce qui efface sans retour : rm -rf, git reset --hard, git push \
--force, git clean.
Si un outil te refuse quelque chose, explique-le simplement a Monsieur \
au lieu de chercher un contournement -- ces limites le protegent."""

OUTILS = [
    {
        "type": "function",
        "function": {
            "name": "etat_robot",
            "description": "Capital reel du robot, variation du jour, "
                            "l'echantillon des 40 trades de preuve et la "
                            "progression vers les objectifs de croissance.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "positions_ouvertes",
            "description": "Les positions actuellement ouvertes par le robot.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "dernieres_alertes",
            "description": "Les dernieres alertes du robot (achats, ventes, "
                            "arrets, problemes).",
            "parameters": {
                "type": "object",
                "properties": {"limite": {"type": "integer", "default": 5}},
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "etat_luna",
            "description": "Le personnage de Luna et ses dernieres generations "
                            "de contenu (posts, statut, legendes).",
            "parameters": {
                "type": "object",
                "properties": {"limite": {"type": "integer", "default": 5}},
            },
        },
    },
]


class _Rest:
    """Client REST/PATCH minimal en service_role -- lecture seule cote
    outils, ecriture seulement sur `alluxe_agent_messages` (ses propres
    reponses)."""

    def __init__(self, url_projet: str, cle: str) -> None:
        self.url = url_projet.rstrip("/")
        self.cle = cle

    def _requete(self, methode: str, chemin: str, corps: bytes | None = None,
                 entetes: dict | None = None) -> bytes:
        h = {"apikey": self.cle, "authorization": f"Bearer {self.cle}",
             **(entetes or {})}
        r = urllib.request.Request(f"{self.url}{chemin}", data=corps,
                                    headers=h, method=methode)
        with urllib.request.urlopen(r, timeout=30) as resp:
            return resp.read()

    def get(self, chemin: str) -> list | dict:
        return json.loads(self._requete("GET", chemin))

    def post(self, chemin: str, corps: dict, entetes: dict | None = None) -> bytes:
        return self._requete("POST", chemin, json.dumps(corps).encode("utf-8"),
                              {"content-type": "application/json", **(entetes or {})})

    def patch(self, chemin: str, corps: dict, entetes: dict | None = None) -> bytes:
        return self._requete("PATCH", chemin, json.dumps(corps).encode("utf-8"),
                              {"content-type": "application/json", **(entetes or {})})


# --------------------------------------------------------- les outils

def _outil_etat_robot(rest: _Rest, _args: dict) -> dict:
    public = rest.get("/rest/v1/etat_public?id=eq.robot"
                       "&select=capital_eur,variation_jour_pct,updated_at")
    prive = rest.get("/rest/v1/alluxe_bot_prive?id=eq.robot"
                      "&select=stats_40,objectifs,methode")
    stats = prive[0]["stats_40"] if prive else None
    resume_esperance = None
    if stats and stats.get("esperance_R_nette") is not None:
        # Le champ brut est en "R" (jargon technique) -- ce resume en
        # mots est ce que le moteur doit reciter, jamais le nombre R.
        val = stats["esperance_R_nette"]
        resume_esperance = ("le robot gagne en moyenne plus qu'il ne perd"
                             if val > 0 else
                             "le robot perd en moyenne plus qu'il ne gagne"
                             if val < 0 else "le robot est a l'equilibre")
    return {
        "capital_reel": (public[0] if public else None),
        "preuve_40_trades": stats,
        "resume_en_mots_de_la_tendance": resume_esperance,
        "objectifs_croissance": (prive[0]["objectifs"] if prive else None),
    }


def _outil_positions_ouvertes(rest: _Rest, _args: dict) -> dict:
    lignes = rest.get(
        "/rest/v1/signals?status=eq.active&select="
        "pair,side,entry_price,stop_loss,take_profit_1,published_at"
        "&order=published_at.desc")
    return {"positions": lignes}


def _outil_dernieres_alertes(rest: _Rest, args: dict) -> dict:
    limite = int(args.get("limite") or 5)
    lignes = rest.get(
        f"/rest/v1/alluxe_bot_alertes?select=created_at,niveau,titre,corps"
        f"&order=created_at.desc&limit={limite}")
    return {"alertes": lignes}


def _outil_etat_luna(rest: _Rest, args: dict) -> dict:
    limite = int(args.get("limite") or 5)
    persona = rest.get("/rest/v1/luna_persona?id=eq.luna"
                        "&select=prenom,age,metier,contexte")
    pubs = rest.get(
        f"/rest/v1/luna_publications?select=created_at,demande,statut,legende,erreurs"
        f"&order=created_at.desc&limit={limite}")
    return {"personnage": (persona[0] if persona else None), "dernieres_publications": pubs}


OUTILS_PAR_NOM = {
    "etat_robot": _outil_etat_robot,
    "positions_ouvertes": _outil_positions_ouvertes,
    "dernieres_alertes": _outil_dernieres_alertes,
    "etat_luna": _outil_etat_luna,
}

# Les outils d'ACTION (fichiers, terminal, web) vivent a part -- c'est la
# partie qui peut casser quelque chose, elle a ses propres garde-fous et
# ses propres tests. Ils ne prennent pas le client Supabase en premier
# argument, d'ou l'enveloppe ci-dessous.
from ops.agent_outils import (ActionRefusee, DESCRIPTION_OUTILS_ACTION,  # noqa: E402
                              OUTILS_ACTION)

for _nom, _fonction in OUTILS_ACTION.items():
    OUTILS_PAR_NOM[_nom] = (lambda f: lambda _rest, args: f(args))(_fonction)
OUTILS = OUTILS + DESCRIPTION_OUTILS_ACTION


# ------------------------------------------------------ le moteur LLM

class ErreurAgent(RuntimeError):
    pass


def _appeler_moteur(messages: list[dict]) -> dict:
    """Un appel brut a l'endpoint compatible OpenAI (LUNA_API_URL), AVEC
    outils -- MoteurCompatibleOpenAI (luna/moteurs.py) ne les expose pas,
    l'agent a besoin de son propre client pour ca."""
    url = os.environ.get("LUNA_API_URL", "").rstrip("/")
    cle = os.environ.get("LUNA_API_KEY", "")
    modele = os.environ.get("LUNA_API_MODELE", "")
    if not url or not modele:
        raise ErreurAgent("LUNA_API_URL ou LUNA_API_MODELE absent")
    endpoint = url if url.endswith("/chat/completions") else url + "/chat/completions"
    corps = {"model": modele, "messages": messages, "tools": OUTILS,
              "max_tokens": 2000, "temperature": 0.3}
    entetes = {"content-type": "application/json",
               "user-agent": "Mozilla/5.0 (X11; Linux x86_64) alluxe-agent/1.0"}
    if cle:
        entetes["authorization"] = f"Bearer {cle}"
    requete = urllib.request.Request(
        endpoint, data=json.dumps(corps).encode("utf-8"),
        headers=entetes, method="POST")
    try:
        with urllib.request.urlopen(requete, timeout=45) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        raise ErreurAgent(f"HTTP {e.code} : {e.read().decode('utf-8', 'replace')[:300]}") from e
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        raise ErreurAgent(f"reseau : {e}") from e


def _repondre(rest_lecture: _Rest, tours: list[dict]) -> tuple[str, list[str]]:
    """Boucle outils -> reponse finale. Rend (texte, noms_des_outils_utilises)."""
    from ops.agent_outils import index_memoire

    systeme = SYSTEME
    # CE QUI FAIT LE « MODE APPRENTISSAGE ». L'index de ses notes est
    # injecte a CHAQUE conversation : il sait donc d'emblee ce qu'il a
    # deja appris, sans avoir a fouiller. Seuls les titres et resumes
    # passent ici ; il ouvre une note entiere avec `relire_memoire`
    # quand il en a besoin.
    memoire = index_memoire()
    if memoire:
        systeme += ("\n\nCE QUE TU AS DEJA APPRIS (tes notes). Utilise "
                     "`relire_memoire` pour en ouvrir une en entier, et "
                     "`noter_en_memoire` des que tu apprends du neuf :\n"
                     + memoire)
    messages = [{"role": "system", "content": systeme}] + tours
    outils_utilises: list[str] = []

    for _ in range(MAX_ALLERS_RETOURS_OUTILS):
        reponse = _appeler_moteur(messages)
        choix = reponse["choices"][0]["message"]
        appels = choix.get("tool_calls") or []
        if not appels:
            return (choix.get("content") or "").strip(), outils_utilises

        messages.append(choix)
        for appel in appels:
            nom = appel["function"]["name"]
            try:
                args = json.loads(appel["function"].get("arguments") or "{}")
            except json.JSONDecodeError:
                args = {}
            fonction = OUTILS_PAR_NOM.get(nom)
            if fonction is None:
                resultat = {"erreur": f"outil inconnu : {nom}"}
            else:
                try:
                    resultat = fonction(rest_lecture, args)
                    outils_utilises.append(nom)
                except ActionRefusee as e:
                    # Un garde-fou, pas une panne : le modele doit
                    # comprendre POURQUOI c'est refuse et l'expliquer a
                    # Monsieur, au lieu de reessayer autrement.
                    resultat = {"refuse": str(e)}
                    outils_utilises.append(f"{nom} (refuse)")
                except Exception as e:                       # noqa: BLE001
                    # Un outil qui casse ne doit jamais tuer le service :
                    # l'agent doit pouvoir dire qu'il a echoue.
                    resultat = {"erreur": f"{type(e).__name__} : {e}"}
            messages.append({
                "role": "tool", "tool_call_id": appel["id"],
                "content": json.dumps(resultat, ensure_ascii=False),
            })

    return ("Desole, je n'arrive pas a repondre proprement pour l'instant "
            "-- redemande dans un instant."), outils_utilises


def _reclamer_message_en_attente(rest: _Rest) -> dict | None:
    lignes = rest.get(
        "/rest/v1/alluxe_agent_messages?role=eq.user&traite=eq.false"
        "&order=created_at.asc&limit=1")
    if not lignes:
        return None
    ligne = lignes[0]
    reclamees = json.loads(rest.patch(
        f"/rest/v1/alluxe_agent_messages?id=eq.{ligne['id']}&traite=eq.false",
        {"traite": True}, {"prefer": "return=representation"}))
    return reclamees[0] if reclamees else None


def _historique_recent(rest: _Rest) -> list[dict]:
    lignes = rest.get(
        f"/rest/v1/alluxe_agent_messages?select=role,contenu"
        f"&order=created_at.desc&limit={HISTORIQUE_MESSAGES}")
    lignes.reverse()
    return [{"role": l["role"], "content": l["contenu"]} for l in lignes]


def _traiter_un_message(rest: _Rest) -> bool:
    ligne = _reclamer_message_en_attente(rest)
    if ligne is None:
        return False
    tours = _historique_recent(rest)
    try:
        texte, outils_utilises = _repondre(rest, tours)
    except ErreurAgent as e:
        texte, outils_utilises = f"(agent indisponible : {e})", []
    rest.post("/rest/v1/alluxe_agent_messages", {
        "role": "assistant", "contenu": texte, "traite": True,
        "outils": outils_utilises,
    })
    return True


def main() -> int:
    url = os.environ.get("SUPABASE_URL", "")
    cle = os.environ.get("SUPABASE_SERVICE_KEY", "")
    if not url or not cle:
        print("SUPABASE_URL ou SUPABASE_SERVICE_KEY absent, arret")
        return 1
    oubliees = _oublier_les_cles_inutiles()
    rest = _Rest(url, cle)
    print(f"agent Alluxe demarre -- outils d'action actifs, {oubliees} cle(s) "
          f"inutile(s) effacee(s) de la memoire, poll toutes les "
          f"{RYTHME_SECONDES}s")
    while True:
        try:
            _traiter_un_message(rest)
        except (urllib.error.HTTPError, urllib.error.URLError) as e:
            print(f"erreur de poll : {e}")
        time.sleep(RYTHME_SECONDES)


if __name__ == "__main__":
    raise SystemExit(main())
