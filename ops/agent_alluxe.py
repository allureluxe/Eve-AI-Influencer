#!/usr/bin/env python3
"""Alluxe -- l'agent personnel de l'operateur (tab 4 de l'application).

Service PERMANENT (systemd, PAS un cron -- une conversation ne peut pas
attendre 2 minutes entre deux phrases) qui repond aux messages deposes
depuis l'app dans `alluxe_agent_messages`.

PREMIERE VERSION, VOLONTAIREMENT LIMITEE A LA LECTURE. L'agent peut
consulter l'etat du robot, les 40 trades de preuve, les alertes et
Luna -- via les MEMES tables Supabase que le reste de l'application,
jamais un acces direct au depot, a gold_bot, ou a un shell. Il ne peut
RIEN changer. Donner un pouvoir d'action (redemarrer le robot, changer
un reglage) est une decision distincte, avec ses propres garde-fous --
voir la memoire du projet, ne pas l'ajouter ici sans en reparler avec
l'operateur.

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
MAX_ALLERS_RETOURS_OUTILS = 3  # borne dure : jamais de boucle infinie

SYSTEME = """Tu es Alluxe, l'assistant personnel de Leny Ludovic. Tu vis \
dans son application privee (le meme telephone qu'Alluxe Bot), et tu es \
le seul agent qu'il consulte pour ses projets : le robot de trading \
(Bitvavo), Luna (son IA-influenceuse) et Allure (l'application publique).

Regles absolues :
- Reponds TOUJOURS en euros ou en pourcentages, JAMAIS en ATR ni en \
"R"/"R multiple" -- Leny ne connait pas ce vocabulaire, meme si les \
outils te les donnent en interne. Un chiffre "R" (ex. -0.23) ne se \
recopie jamais tel quel : dis "en ce moment le robot perd legerement \
plus qu'il ne gagne en moyenne" plutot qu'un nombre en R. Ne prononce \
jamais la lettre R comme unite, ni le mot "ATR".
- Sois direct et concret. Leny raisonne en resultats, pas en code : \
pas de jargon technique inutile.
- Tu ne PEUX RIEN changer pour l'instant -- ni redemarrer le robot, ni \
modifier un reglage, ni toucher au code. Tu lis seulement. Si Leny te \
demande d'agir, dis-le clairement et propose de le faire lui-meme (ou \
qu'il en parle a la session Claude Code sur le VPS), sans jamais \
pretendre avoir agi.
- Utilise les outils fournis pour repondre avec des chiffres reels, \
jamais invente. Si tu ne sais pas, dis-le.
- Reste bref : une reponse de chat, pas un rapport."""

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
              "max_tokens": 700, "temperature": 0.4}
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
    messages = [{"role": "system", "content": SYSTEME}] + tours
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
                except (urllib.error.HTTPError, urllib.error.URLError) as e:
                    resultat = {"erreur": str(e)}
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
    rest = _Rest(url, cle)
    print("agent Alluxe demarre, lecture seule, poll toutes les "
          f"{RYTHME_SECONDES}s")
    while True:
        try:
            _traiter_un_message(rest)
        except (urllib.error.HTTPError, urllib.error.URLError) as e:
            print(f"erreur de poll : {e}")
        time.sleep(RYTHME_SECONDES)


if __name__ == "__main__":
    raise SystemExit(main())
