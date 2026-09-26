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

# 0,4 s : l'operateur voulait qu'il reponde "du tac au tac". Le moteur
# repond en 0,3 s -- c'etait le SONDAGE qui coutait jusqu'a 2 s avant
# meme de voir le message, plus 2 s cote application pour l'afficher.
RYTHME_SECONDES = 0.4
HISTORIQUE_MESSAGES = 12  # tours de conversation gardes comme contexte
# Un agent qui AGIT enchaine : lire un fichier, le modifier, lancer les
# tests, lire l'erreur, recommencer. Trois allers-retours suffisaient a un
# agent qui ne faisait que consulter ; ils ne suffisent plus.
MAX_ALLERS_RETOURS_OUTILS = 8

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

SYSTEME = """Tu es Alluxe, l'assistant de Leny Ludovic. Appelle-le TOUJOURS "Monsieur". Tu geres ses projets : le robot de trading (Bitvavo), Luna (son IA-influenceuse) et Allure (l'app publique). Tu tournes sur son serveur, avec un terminal et internet.

CARACTERE : calme, competent, un peu sec. Pas de politesses inutiles, pas d'excuses en boucle. Si une idee te parait mauvaise, dis-le une fois puis fais ce qu'on te demande -- c'est lui qui decide.

REGLES :
- Parle en euros ou en pourcentages. JAMAIS "R", "R multiple" ni "ATR" : il ne connait pas ce vocabulaire. Ne recopie jamais un chiffre en R ; dis "il perd un peu plus qu'il ne gagne en moyenne".
- N'invente aucun chiffre : tu as des outils pour lire le reel. Si tu ne sais pas, va verifier ou dis-le.
- N'INVENTE AUCUNE PROCEDURE NI AUCUN ECRAN. Le 20 sept. tu lui as repondu « connectez-vous a l'interface de Lapli, choisissez Creer un compte demo » : rien de tout ca n'existe, tu l'avais fabrique. Si on te demande quelque chose que tu ne peux pas faire, dis SEULEMENT que tu ne peux pas et pourquoi -- ne decris jamais des boutons ni des menus que tu n'as pas verifies avec tes outils. Un chemin invente lui fait perdre du temps ET lui fait douter de tout le reste.
- Il dicte a la voix : les mots sont parfois mal transcrits (« lapli » = « l'appli », « alluxe » = « Allure »). Devine le sens, et s'il y a un doute demande plutot que d'inventer.
- Ne pretends jamais avoir fait ce que tu n'as pas fait. Une commande qui echoue, tu le dis avec l'erreur.
- Reponds court, comme dans un chat. Le detail seulement s'il le demande.
- RECHERCHE D'IDEES DE TRADING : pour une strategie, utilise `recherche_idee_trading` avant de proposer une nouvelle hypothese. En mode `academique`, privilegie publications universitaires et institutions; en mode `forums`, cherche les retours de praticiens; en `complet`, croise les familles. Ne traite jamais un forum ou un article marketing comme une preuve : extrais une hypothese testable, sa source et ses conditions, puis fais-la tester par le Strategy Lab hors echantillon avec frais/glissement realistes.
- Pour la recherche academique, utilise aussi `chercher_articles_scientifiques` quand une recherche approfondie est necessaire. Les sources doivent rester traçables par URL.
- Quand il demande une modification, FAIS-LA puis verifie (lance les tests concernes). Ne decris pas ce qu'il faudrait faire.
- Pour Luna, utilise creer_media_luna pour les nouvelles photos/videos : photo en 3:4 par defaut, video en 9:16 et 10 s. Mets publier=true seulement quand Monsieur demande que le contenu parte automatiquement sur Instagram. Tant que l'etat n'est pas termine, ne dis jamais que le media est pret.

DEUX ESPACES : le depot ~/Eve-AI-Influencer (production, prudence, tests apres chaque changement) et ton atelier ~/atelier (a toi, un dossier par projet, cree-y un venv dedie -- jamais dans le .venv du depot).

INTERNET : navigation normale par defaut. `via_tor` seulement s'il le demande ; les adresses .onion basculent toutes seules.

REFUSE ET C'EST NORMAL : les fichiers de cles (.env), l'arret du robot reel (robot-dual-live), les configurations robot*.json en ecriture (un reglage ne change qu'apres mesure et decision de Monsieur), et tout ce qui efface sans retour. Si un outil refuse, explique-le simplement au lieu de contourner."""

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
    {
        "type": "function",
        "function": {
            "name": "creer_media_luna",
            "description": "Depose un job photo ou video Luna pour le worker VPS. "
                            "Photo 3:4 par defaut. Video 9:16, 10 secondes. "
                            "publier=true demande la publication Instagram apres generation.",
            "parameters": {
                "type": "object",
                "properties": {
                    "type": {"type": "string", "enum": ["photo", "video"]},
                    "prompt": {"type": "string"},
                    "caption": {"type": "string"},
                    "aspect_ratio": {"type": "string"},
                    "duration_seconds": {"type": "integer"},
                    "quality": {"type": "string", "enum": ["brouillon", "finale"]},
                    "reference_path": {"type": "string"},
                    "provider": {"type": "string"},
                    "model": {"type": "string"},
                    "content_format": {"type": "string"},
                    "publier": {"type": "boolean"}
                },
                "required": ["type", "prompt"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "etat_media_luna",
            "description": "Lit un job media Luna par id ou les derniers jobs.",
            "parameters": {
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "limite": {"type": "integer", "default": 5}
                }
            }
        }
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
    """Les positions ouvertes, REEL ET DEMO SEPARES.

    La requete ne filtrait pas `is_demo` : l'agent additionnait donc les
    positions simulees et les reelles, et repondait « 22 positions » quand
    la demo en avait 20 et le compte reel 2. C'est exactement la confusion
    du 18 septembre, ou une position simulee etait apparue dans
    l'application comme si elle etait reelle -- et celle-ci portait sur le
    canal par lequel Monsieur pose ses questions.
    """
    champs = ("pair,side,entry_price,stop_loss,stop_loss_actuel,"
              "position_size_pct,capital_eur,published_at")
    reelles = rest.get(f"/rest/v1/signals?status=eq.active&is_demo=eq.false"
                       f"&select={champs}&order=published_at.desc")
    demo = rest.get(f"/rest/v1/signals?status=eq.active&is_demo=eq.true"
                    f"&select={champs}&order=published_at.desc")
    return {
        "compte_REEL": {"nombre": len(reelles), "positions": reelles},
        "simulation_DEMO": {"nombre": len(demo), "positions": demo},
        "rappel": ("Ne jamais additionner les deux : la demo est un "
                   "capital virtuel, le reel est l'argent de Monsieur."),
    }


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




def _outil_creer_media_luna(rest: _Rest, args: dict) -> dict:
    """Depose un job structure pour le Media Worker."""
    typ = str(args.get("type") or "").strip().lower()
    prompt = str(args.get("prompt") or "").strip()
    if typ not in {"photo", "video"}:
        raise ValueError("type doit etre photo ou video")
    if not prompt:
        raise ValueError("prompt obligatoire")
    if len(prompt) > 12000:
        raise ValueError("prompt trop long")

    ratio = str(args.get("aspect_ratio") or (
        "9:16" if typ == "video" else "3:4"
    )).strip()
    ratios = {"1:1", "3:4", "4:5", "2:3", "3:2", "4:3", "9:16", "16:9"}
    if ratio not in ratios:
        raise ValueError("aspect_ratio invalide")

    duree = int(args.get("duration_seconds") or 10)
    if not 1 <= duree <= 30:
        raise ValueError("duration_seconds doit etre entre 1 et 30")

    qualite = str(args.get("quality") or "finale").strip().lower()
    if qualite not in {"brouillon", "finale"}:
        raise ValueError("quality invalide")

    payload = {
        "type": typ,
        "prompt": prompt,
        "caption": str(args.get("caption") or "").strip(),
        "reference": str(args.get("reference_path") or "").strip(),
        "aspect_ratio": ratio,
        "duration_seconds": duree,
        "quality": qualite,
        "provider": str(args.get("provider") or "").strip().lower(),
        "model": str(args.get("model") or "").strip(),
        "content_format": str(args.get("content_format") or "").strip().lower(),
        "publish": bool(args.get("publier", False)),
    }
    lignes = json.loads(rest.post(
        "/rest/v1/luna_publications",
        {
            "demande": json.dumps(payload, ensure_ascii=False),
            "media_type": typ,
            "reference_path": payload["reference"] or None,
            "aspect_ratio": ratio,
            "duration_seconds": duree,
            "quality": qualite,
            "publish_requested": payload["publish"],
        },
        {"prefer": "return=representation"},
    ))
    ligne = lignes[0] if lignes else {}
    return {
        "id": ligne.get("id"),
        "statut": ligne.get("statut", "en_attente"),
        "generation_status": ligne.get("generation_status", "queued"),
        "media_type": typ,
        "aspect_ratio": ratio,
        "publish_requested": payload["publish"],
    }


def _outil_etat_media_luna(rest: _Rest, args: dict) -> dict:
    ident = str(args.get("id") or "").strip()
    limite = max(1, min(20, int(args.get("limite") or 5)))
    champs = (
        "id,created_at,media_type,statut,generation_status,legende,"
        "chemin_photo,chemin_video,provider,provider_task_id,"
        "publish_requested,published_at,published_platform,"
        "published_media_id,erreurs"
    )
    if ident:
        lignes = rest.get(
            f"/rest/v1/luna_publications?id=eq.{ident}&select={champs}"
        )
    else:
        lignes = rest.get(
            f"/rest/v1/luna_publications?select={champs}"
            f"&order=created_at.desc&limit={limite}"
        )
    return {"jobs": lignes}

OUTILS_PAR_NOM = {
    "etat_robot": _outil_etat_robot,
    "positions_ouvertes": _outil_positions_ouvertes,
    "dernieres_alertes": _outil_dernieres_alertes,
    "etat_luna": _outil_etat_luna,
    "creer_media_luna": _outil_creer_media_luna,
    "etat_media_luna": _outil_etat_media_luna,
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


# ---------------------------------------------------------------------
#  Respecter le debit du palier gratuit AU LIEU DE FONCER DEDANS
# ---------------------------------------------------------------------
#
# Groq accorde 8 000 mots-machine PAR MINUTE. Mesure le 19 sept. : un
# appel de cet agent en coute ~3 000 (17 outils = 1 078, historique =
# 1 188, consignes = 700). Ce n'est pas excessif -- le probleme est que
# ce total repart EN ENTIER a chaque aller-retour d'outil. Trois outils
# enchaines font donc 12 000 dans la minute, et le mur arrive au
# troisieme.
#
# L'agent repondait alors « (agent indisponible : HTTP 429...) », ce que
# Monsieur a lu comme « l'agent est bloque ». Il ne l'etait pas : il
# avait juste epuise ses reprises.
#
# On tient donc un compteur glissant sur 60 secondes et on ATTEND avant
# d'appeler, plutot que de se faire refuser puis de reessayer. Le
# resultat est le meme en temps total, mais sans echec visible -- et
# c'est une attente qu'on peut expliquer, pas une panne.
DEBIT_PAR_MINUTE = 8000
MARGE_DEBIT = 0.85          # on ne vise pas le plafond exact

_historique_debit: list[tuple[float, int]] = []


# UN SEUL APPEL NE PEUT PAS DEPASSER LE DEBIT D'UNE MINUTE.
#
# Groq refuse en 413 « Request too large ... Requested 8022, Limit
# 8000 » : ce n'est pas un debit a etaler, c'est un mur. Or les
# resultats d'outils s'EMPILENT dans la conversation et repartent a
# chaque aller-retour -- deux recherches web suffisent a le franchir.
#
# C'est ce qui bloquait les recherches de Monsieur le 19 sept. au soir
# (« teste toutes les methodes, combine-les, cherche encore ») : la
# tache demandait plusieurs outils, et l'agent mourait au troisieme.
#
# On borne donc chaque resultat d'outil, puis on jette les plus anciens
# si ca deborde encore. Perdre le detail d'une recherche faite il y a
# trois etapes est sans consequence ; ne pas pouvoir repondre du tout
# en a une.
BUDGET_MESSAGES = 5200          # hors max_tokens de la reponse
RESULTAT_OUTIL_MAX = 2500       # caracteres, par resultat d'outil


def _comprimer(messages: list[dict]) -> list[dict]:
    """Ramene la conversation sous le budget, sans perdre l'essentiel.

    Ordre de sacrifice : d'abord la TAILLE des vieux resultats d'outils,
    ensuite les vieux echanges d'outils entiers. Le message systeme et
    la demande en cours ne sont jamais touches.
    """
    if _estimer_jetons(messages) <= BUDGET_MESSAGES:
        return messages

    # 1. Raccourcir les resultats d'outils, les plus anciens d'abord.
    for m in messages:
        if m.get("role") == "tool" and len(m.get("content") or "") > 400:
            m["content"] = (m["content"][:400]
                            + " […coupé, resultat trop long]")
            if _estimer_jetons(messages) <= BUDGET_MESSAGES:
                return messages

    # 2. Jeter les plus vieux echanges d'outils. On garde toujours le
    #    systeme (indice 0) et les deux derniers messages.
    while _estimer_jetons(messages) > BUDGET_MESSAGES and len(messages) > 3:
        for i in range(1, len(messages) - 2):
            if messages[i].get("role") in ("tool", "assistant"):
                del messages[i]
                break
        else:
            break
    return messages


def _estimer_jetons(messages: list[dict]) -> int:
    """~4 caracteres par mot-machine. Approximation volontaire : elle
    sert a se freiner, pas a facturer."""
    return len(json.dumps(messages, ensure_ascii=False)) // 4


def _attendre_son_tour(cout: int) -> None:
    """Dort le temps qu'il faut pour rester sous le debit autorise."""
    plafond = int(DEBIT_PAR_MINUTE * MARGE_DEBIT)
    while True:
        maintenant = time.time()
        _historique_debit[:] = [(t, n) for t, n in _historique_debit
                                if maintenant - t < 60.0]
        deja = sum(n for _, n in _historique_debit)
        if deja + cout <= plafond or not _historique_debit:
            _historique_debit.append((maintenant, cout))
            return
        # Assez pour que la plus ancienne consommation sorte de la
        # fenetre : c'est le plus court delai qui libere de la place.
        attente = max(0.5, 60.0 - (maintenant - _historique_debit[0][0]) + 0.2)
        print(f"debit : {deja} deja consommes, j'attends {attente:.0f}s")
        time.sleep(min(attente, 30.0))


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
              "max_tokens": 900, "temperature": 0.3}
    entetes = {"content-type": "application/json",
               "user-agent": "Mozilla/5.0 (X11; Linux x86_64) alluxe-agent/1.0"}
    if cle:
        entetes["authorization"] = f"Bearer {cle}"
    requete = urllib.request.Request(
        endpoint, data=json.dumps(corps).encode("utf-8"),
        headers=entetes, method="POST")

    # On se freine AVANT d'appeler. Le 429 devient alors l'exception,
    # pas le regime normal.
    _attendre_son_tour(_estimer_jetons(messages) + int(corps["max_tokens"]))

    # LE PALIER GRATUIT A UNE LIMITE PAR MINUTE (8 000 mots-machine chez
    # Groq). Un agent qui ENCHAINE les outils la touche forcement : chaque
    # aller-retour renvoie tout le contexte. Sans cette reprise, Monsieur
    # voyait « agent indisponible » pour une attente de six secondes.
    # Le serveur dit lui-meme combien de temps patienter, on l'ecoute.
    for tentative in range(6):
        try:
            with urllib.request.urlopen(requete, timeout=60) as r:
                return json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", "replace")
            # LE MODELE PEUT RATER SON APPEL D'OUTIL, ET CE N'EST PAS
            # UNE PANNE.
            #
            # Observe le 19 sept. sur gpt-oss-120b : il a demande l'outil
            # « chercher<|channel|>commentary » -- un jeton interne du
            # modele avait fui dans le nom. Groq refuse l'appel (400
            # tool_use_failed) et l'agent repondait « indisponible » pour
            # une erreur de frappe. C'est du tirage au sort : la meme
            # question repassee sort generalement propre. On retente,
            # comme pour la limite de debit.
            if e.code == 400 and "tool_use_failed" in detail and tentative < 5:
                print("appel d'outil malforme par le modele, nouvelle tentative")
                time.sleep(1.0)
                continue
            if e.code == 429 and tentative < 5:
                import re as _re
                trouve = _re.search(r"try again in ([\d.]+)s", detail)
                attente = min(float(trouve.group(1)) + 1.0 if trouve else 8.0, 30.0)
                print(f"limite du moteur atteinte, reprise dans {attente:.0f}s")
                time.sleep(attente)
                continue
            raise ErreurAgent(f"HTTP {e.code} : {detail[:300]}") from e
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            if tentative < 5:
                time.sleep(3)
                continue
            raise ErreurAgent(f"reseau : {e}") from e
    raise ErreurAgent("moteur injoignable apres plusieurs tentatives")


def _repondre(rest_lecture: _Rest, tours: list[dict],
              systeme_sup: str = "") -> tuple[str, list[str]]:
    """Boucle outils -> reponse finale. Rend (texte, noms_des_outils_utilises)."""
    from ops.agent_outils import index_memoire

    systeme = SYSTEME + systeme_sup
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
        messages = _comprimer(messages)
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
            rendu = json.dumps(resultat, ensure_ascii=False)
            if len(rendu) > RESULTAT_OUTIL_MAX:
                # Une recherche web rend parfois des pages entieres. Le
                # modele n'a pas besoin de tout : il a besoin du debut.
                rendu = rendu[:RESULTAT_OUTIL_MAX] + " […resultat tronqué]"
            messages.append({
                "role": "tool", "tool_call_id": appel["id"],
                "content": rendu,
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


# ---------------------------------------------------------------------
#  L'onglet Discussion : parler au robot directement
# ---------------------------------------------------------------------
#
# Demande de l'operateur le 19 sept. : « le mode discussion, je peux
# parler directement au robot de trading, tu crees un agent connecte au
# VPS qui me permettra de parler directement au robot, de faire les
# modifications avec lui, et inclus lui le web, les bibliotheques et les
# livres universitaires et academiques ».
#
# CET AGENT EXISTE DEJA -- c'est celui-ci. Il a le terminal, le depot,
# la recherche web, la lecture de pages, les publications scientifiques
# (arXiv + Semantic Scholar), sa memoire et Tor. En construire un second
# pour la Discussion aurait fait deux agents a tenir d'accord, c'est-a-
# dire la faute que ce depot paie depuis le debut. On le BRANCHE sur une
# seconde table, c'est tout.
#
# LES COMMANDES PASSENT AVANT LE MODELE. « rapport allure » et « etat »
# ont une reponse exacte et gratuite (`gold_bot/commandes.py`) : la faire
# produire par un modele serait plus lent, plus cher, et moins fiable.

DISCUSSION = "alluxe_bot_discussion"

SYSTEME_DISCUSSION = """

TU ES ICI DANS L'ONGLET DISCUSSION, en face du robot de trading. Monsieur
y parle du robot en priorite : ses positions, ses reglages, ses
resultats, ses strategies. Va lire le reel avec tes outils avant de
repondre.

Il peut aussi te demander de chercher : le web, et les publications
universitaires et academiques (`chercher_articles_scientifiques`, qui
interroge arXiv et Semantic Scholar). Quand tu cites une etude, donne le
titre et l'annee, et dis franchement quand un resultat n'est pas
reproductible ici -- ce depot a deja arme des reglages sur des chiffres
qui ne tenaient pas.

LES CONFIGURATIONS robot*.json RESTENT EN LECTURE. Tu peux tout lire,
tout mesurer, tout proposer -- et tu dois le faire precisement, avec les
valeurs exactes. Mais c'est Monsieur qui applique. Ce n'est pas de la
mefiance : le 19 septembre tu as modifie `robot.demo.json` tout seul
apres une demande vague, puis tu t'es arrete en manquant de jetons sans
le dire. Le changement dormait dans le depot avant le depot reel du 28.
Quand un reglage doit changer, DIS lequel, a quelle valeur, et pourquoi,
puis laisse-le decider."""


def _traiter_message_discussion(rest: _Rest) -> bool:
    """Un message de l'onglet Discussion. Rend True s'il a ete traite ICI."""
    from gold_bot.commandes import est_une_commande

    lignes = rest.get(f"/rest/v1/{DISCUSSION}?auteur=eq.operateur"
                      f"&traite=eq.false&order=created_at.asc&limit=1")
    if not lignes:
        return False
    # Reclamee AVANT tout traitement : sans ca, deux passages de la
    # boucle pourraient repondre deux fois a la meme demande.
    reclamees = json.loads(rest.patch(
        f"/rest/v1/{DISCUSSION}?id=eq.{lignes[0]['id']}&traite=eq.false",
        {"traite": True}, {"prefer": "return=representation"}))
    if not reclamees:
        return False
    texte = str(reclamees[0].get("texte") or "").strip()

    # PAS POUR MOI : je rends la main.
    #
    # Fabriquer la page ALLURE demande de lire le compte Bitvavo, donc
    # les cles -- que ce service a justement effacees de sa memoire au
    # demarrage. `ops/ecoute_discussion.py`, lui, tourne sous `ubuntu` et
    # les a. On repose donc le message tel quel, et il le prendra.
    if est_une_commande(texte):
        rest.patch(f"/rest/v1/{DISCUSSION}?id=eq.{reclamees[0]['id']}",
                   {"traite": False})
        return False

    # UN MESSAGE RECLAME RECOIT TOUJOURS UNE REPONSE.
    #
    # Il est deja marque « traite » : plus personne ne le reprendra. Si
    # quoi que ce soit echoue ici sans etre rattrape -- une lecture de
    # l'historique, un outil qui casse, une cle manquante -- Monsieur
    # attendrait indefiniment devant un message marque lu. Le silence
    # est la pire des reponses : il ne dit meme pas qu'il y a un
    # probleme.
    try:
        tours = _historique_discussion(rest)
        texte_reponse, _outils = _repondre(rest, tours, SYSTEME_DISCUSSION)
        if not texte_reponse.strip():
            texte_reponse = ("Je n'ai rien a repondre a ca -- reformulez "
                             "et je reessaie.")
    except ErreurAgent as e:
        texte_reponse = f"(agent indisponible : {e})"
    except Exception as e:                                    # noqa: BLE001
        texte_reponse = f"(panne de mon cote : {type(e).__name__} : {e})"

    try:
        rest.post(f"/rest/v1/{DISCUSSION}", {
            "auteur": "robot", "texte": texte_reponse, "traite": True})
    except Exception as e:                                    # noqa: BLE001
        # La reponse n'est pas partie : on repose la question pour la
        # reprendre au tour suivant, plutot que de la perdre.
        print(f"reponse non publiee, message repose : {e}")
        rest.patch(f"/rest/v1/{DISCUSSION}?id=eq.{reclamees[0]['id']}",
                   {"traite": False})
    return True


# Un de ses propres longs tableaux pesait a lui seul 652 mots-machine,
# renvoyes a CHAQUE aller-retour d'outil. On garde le fil complet -- la
# conversation a besoin de son contexte -- mais on coupe les pavés : ce
# qui compte dans un vieux message, c'est son debut.
LONGUEUR_MAX_MESSAGE = 700


def _historique_discussion(rest: _Rest) -> list[dict]:
    lignes = rest.get(f"/rest/v1/{DISCUSSION}?select=auteur,texte"
                      f"&order=created_at.desc&limit={HISTORIQUE_MESSAGES}")
    lignes.reverse()
    tours = []
    for i, l in enumerate(lignes):
        texte = l.get("texte") or ""
        if not texte:
            continue
        # Le DERNIER message reste entier : c'est la demande en cours.
        if len(texte) > LONGUEUR_MAX_MESSAGE and i < len(lignes) - 1:
            texte = texte[:LONGUEUR_MAX_MESSAGE] + " […]"
        tours.append({
            "role": "user" if l["auteur"] == "operateur" else "assistant",
            "content": texte,
        })
    return tours


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
            # Les deux fils : l'onglet Agent et l'onglet Discussion.
            # `or` court-circuite, donc une seule reponse par tour --
            # deux appels au modele dans le meme tour doubleraient la
            # consommation de jetons sur un palier gratuit deja etroit.
            _traiter_un_message(rest) or _traiter_message_discussion(rest)
        except (urllib.error.HTTPError, urllib.error.URLError) as e:
            print(f"erreur de poll : {e}")
        time.sleep(RYTHME_SECONDES)


if __name__ == "__main__":
    raise SystemExit(main())
