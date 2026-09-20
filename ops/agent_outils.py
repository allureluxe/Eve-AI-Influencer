#!/usr/bin/env python3
"""Les outils d'ACTION de l'agent Alluxe -- lire, ecrire, chercher, executer.

Demande de l'operateur le 19 sept. 2026 : « en gros cree-moi un clone de
Claude Code qui sera le mien », sur le moteur gratuit (Groq) plutot que
sur un abonnement payant. Ce module leve la limitation « lecture seule »
posee le 16 sept., qui etait explicitement conditionnee a une nouvelle
discussion sur le perimetre -- cette discussion a eu lieu.

CE QUI REND CA TENABLE. Le meme serveur heberge un robot qui engage de
l'argent reel, les cles d'API du compte Bitvavo, et l'historique des
trades. Un agent pilote par un modele de langage se trompe ; la question
n'est pas SI mais QUAND. La reponse de ce module n'est pas de brider sa
puissance -- il a le shell complet -- mais de rendre impossibles les
quelques gestes dont on ne revient pas :

  - les CLES ne se lisent ni ne s'ecrivent (`.env` et compagnie). Un
    agent qui peut lire `.env` peut le recopier dans sa reponse, donc
    dans une conversation, donc hors du serveur.
  - le ROBOT REEL ne s'arrete pas et ne se redemarre pas. Il porte des
    positions ouvertes avec de vrais euros dessus.
  - ce qui EFFACE sans retour est refuse : `rm -rf`, `git reset --hard`,
    `git push --force`, `git clean`, `mkfs`, `dd`.
  - tout se passe DANS le depot : aucun chemin hors de `RACINE`.

Tout le reste est permis, y compris ecrire du code, lancer les tests,
commiter, pousser, lire les journaux. C'est volontaire : un assistant
qui doit demander la permission pour chaque geste ne sert a rien.
"""
from __future__ import annotations

import os
import re
import subprocess

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

SORTIE_MAX = 4000        # caracteres rendus au modele, par appel
DELAI_MAX = 180          # secondes pour une commande


class ActionRefusee(RuntimeError):
    """Geste interdit. Le message explique pourquoi, en francais."""


# --------------------------------------------------------- les chemins

#: Fichiers dont le CONTENU ne doit jamais atteindre une conversation.
#: Cle Bitvavo, cle de service Supabase, jetons GitHub, compte de service
#: Firebase, cles SSH. Tout ce qui, recopie dans un message, donne a
#: quelqu'un d'autre les memes pouvoirs que l'operateur.
SECRETS = (
    re.compile(r"(^|/)\.env"),
    re.compile(r"\.(pem|key|p12|pfx)$"),
    re.compile(r"(^|/)id_(rsa|ed25519)"),
    re.compile(r"(^|/)(credentials|service[-_]?account)[^/]*\.json$"),
    re.compile(r"(^|/)\.git/config$"),
)


#: Les configurations de robot : LECTURE seule pour l'agent.
#:
#: Le 19 sept. a 12h20, a qui on demandait "continue a me trouver une
#: strategie payante sur le bot", l'agent a repondu en MODIFIANT
#: robot.demo.json -- risque par trade divise par deux (0,6 -> 0,3 %) --
#: puis s'est arrete en manquant de jetons, sans le dire. Le changement
#: n'a jamais tourne (le robot lit sa config au demarrage et n'avait pas
#: redemarre), mais il dormait dans le depot.
#:
#: Deux raisons de l'interdire, et la seconde est la plus grave :
#:  - AUCUNE MESURE. La regle premiere de ce depot est qu'un reglage ne
#:    change qu'apres un walk-forward, hors echantillon, frais doubles.
#:  - LA DEMO CESSE DE MESURER CE QU'ON CROIT. Elle existe pour tester la
#:    strategie ARMEE sur 500 EUR. Risque divise par deux, elle teste
#:    autre chose, et l'echantillon que Monsieur attend pour decider de
#:    son depot ne vaut plus rien -- sans que personne ne le voie.
CONFIGS_ROBOT = re.compile(r"^robot[.\w-]*\.json$")

#: LES COMPTES D'EXPERIENCE, eux, sont a lui.
#:
#: Demande de l'operateur le 20 sept. : « je veux que l'agent puisse
#: gerer les comptes demo, il me dit qu'il ne peut pas faire ce que je
#: lui demande ». Il a raison : l'interdiction ci-dessus etait trop
#: large.
#:
#: LA LIGNE EXACTE, et elle tient en une phrase : ce qui engage de
#: l'argent ou porte une mesure en cours est protege ; le reste est un
#: bac a sable.
#:
#:   robot.bitvavo.json  ARGENT REEL. Jamais. Aucune exception.
#:   robot.demo.json     le compte de REFERENCE -- il porte la
#:                       simulation de 48 h sur laquelle Monsieur
#:                       decide son depot du 28. Le modifier en cours
#:                       de route detruirait la mesure, et c'est
#:                       exactement ce qui s'est passe le 19 sept. a
#:                       12h20 : l'agent a divise le risque par deux
#:                       tout seul, puis s'est tu.
#:   robot.demo2.json    a lui.
#:   robot.demo3.json    a lui.
#:
#: Un compte d'experience ne coute rien quand il se trompe : c'est
#: precisement sa raison d'etre. L'interdire revenait a interdire
#: l'experimentation pour se proteger d'un risque qui n'existe pas la.
CONFIGS_EXPERIENCE = re.compile(r"^robot\.demo[23]\.json$")

#: L'ATELIER : l'espace ou l'agent construit SES programmes.
#:
#: Demande de l'operateur le 19 sept. : « je veux qu'il puisse construire
#: et lire des codes qui fabriquent des programmes ». Le confiner au
#: depot du robot l'empechait de creer quoi que ce soit de neuf -- il ne
#: pouvait que retoucher l'existant.
#:
#: Un dossier a lui, hors du depot, regle les deux besoins d'un coup : il
#: y fait ce qu'il veut (nouveaux projets, environnements Python, essais
#: rates) sans qu'une erreur ne touche le robot, le code en production ou
#: le systeme. C'est son etabli, pas la maison entiere.
ATELIER = os.path.expanduser("~/atelier")


def _espaces_autorises() -> tuple[str, ...]:
    return (os.path.realpath(RACINE), os.path.realpath(ATELIER))


def chemin_sur(chemin: str, *, pour_ecriture: bool = False) -> str:
    """Rend le chemin absolu, ou leve `ActionRefusee`.

    Deux verrous : rester dans un espace autorise (le depot ou l'atelier
    -- pas de `../../etc/passwd`, pas de lien symbolique qui sort), et ne
    jamais toucher un secret.
    """
    if not chemin or not chemin.strip():
        raise ActionRefusee("chemin vide")
    chemin = chemin.strip()
    if chemin.startswith("~"):
        chemin = os.path.expanduser(chemin)
    base = ATELIER if os.path.isabs(chemin) else RACINE
    absolu = os.path.realpath(os.path.join(base, chemin))

    racine = None
    for espace in _espaces_autorises():
        if absolu == espace or absolu.startswith(espace + os.sep):
            racine = espace
            break
    if racine is None:
        os.makedirs(ATELIER, exist_ok=True)
        raise ActionRefusee(
            f"hors des espaces autorises : {chemin}. L'agent travaille "
            f"dans le depot ({RACINE}) et dans son atelier ({ATELIER}).")
    relatif = os.path.relpath(absolu, racine)
    for motif in SECRETS:
        if motif.search("/" + relatif.replace(os.sep, "/")):
            raise ActionRefusee(
                f"{relatif} contient des cles d'acces. Ni lecture ni "
                f"ecriture : recopiees dans une reponse, elles sortiraient "
                f"du serveur. Demande a Leny de le faire lui-meme.")
    if pour_ecriture and relatif.split(os.sep)[0] == ".git":
        raise ActionRefusee("on ne modifie pas .git a la main")
    nom = os.path.basename(relatif)
    if (pour_ecriture and CONFIGS_ROBOT.match(nom)
            and not CONFIGS_EXPERIENCE.match(nom)):
        raise ActionRefusee(
            f"{relatif} n'est pas un compte d'experience. "
            f"« robot.bitvavo.json » engage l'argent reel, et "
            f"« robot.demo.json » porte la simulation de reference sur "
            f"laquelle Monsieur decide son depot -- la modifier en cours "
            f"de route detruirait la mesure. "
            f"Tu peux en revanche modifier librement robot.demo2.json et "
            f"robot.demo3.json : ce sont des comptes d'experience, ils "
            f"existent pour ca. Pour les deux autres, propose le "
            f"changement et la mesure qui le justifie.")
    return absolu


# ------------------------------------------------------- les commandes

#: (motif, explication). Compares a la commande complete, minuscules.
COMMANDES_INTERDITES = (
    (re.compile(r"\brm\s+(-\w*[rf]\w*\s+)+"),
     "effacement recursif : irreversible, et une erreur de chemin coute "
     "le depot entier"),
    (re.compile(r"\bgit\s+push\b.*(--force|-f\b)"),
     "un push force reecrit l'historique distant : ce que quelqu'un "
     "d'autre a deja recupere devient faux"),
    (re.compile(r"\bgit\s+reset\s+--hard\b"),
     "git reset --hard jette le travail non commite sans confirmation"),
    (re.compile(r"\bgit\s+clean\b"),
     "git clean efface les fichiers non suivis, souvent du travail en cours"),
    (re.compile(r"\bgit\s+checkout\s+--\s"),
     "git checkout -- <fichier> ecrase les modifications non commitees"),
    (re.compile(r"\b(mkfs|fdisk|dd)\b"),
     "commande de disque : aucun usage legitime ici"),
    (re.compile(r"\bsudo\b"),
     "l'agent travaille sans privileges administrateur. Pour un service, "
     "demande a Leny ou a la session Claude Code du VPS."),
    (re.compile(r"\bsystemctl\s+(stop|restart|disable|kill)\b.*robot-dual-live"),
     "robot-dual-live porte de l'argent reel et des positions ouvertes : "
     "il ne se touche pas depuis un chat"),
    (re.compile(r"\.env\b"),
     "les fichiers .env portent les cles d'acces : jamais lus, jamais "
     "ecrits, jamais copies"),
    (re.compile(r"\b(curl|wget)\b.*(SUPABASE|BITVAVO|API_KEY|TOKEN|SECRET)"),
     "envoyer une cle vers l'exterieur"),
    (re.compile(r"\bcrontab\s+-r\b"),
     "crontab -r efface toutes les taches planifiees d'un coup"),
    # Le `\s*` doit venir APRES l'alternative de debut, pas dedans : la
    # commande est encadree d'espaces avant comparaison (voir
    # `commande_sure`), donc `^` est toujours suivi d'un espace et le
    # motif ne matchait JAMAIS un `printenv` seul. Trouve par les tests
    # le 19 sept., dans la barriere meme que j'avais annoncee comme
    # posee -- deuxieme fois dans la meme journee qu'un garde-fou de ce
    # module s'avere decoratif. D'ou la regle : ce qui protege vraiment
    # ici, c'est `environnement_sans_cles()`, pas ce filtre.
    (re.compile(r"(^|[;|&(])\s*(env|printenv|set)\s*($|[;|&)])"),
     "afficher l'environnement. Les commandes tournent deja sans les "
     "cles (voir environnement_sans_cles), ceci est une seconde barriere"),
    (re.compile(r"os\.environ|getenv|ENVIRON"),
     "lire l'environnement depuis un interpreteur"),
    (re.compile(r">\s*/dev/sd|\b:\(\)\s*\{"),
     "commande destructrice ou bombe a fork"),
)


def commande_sure(commande: str) -> None:
    """Leve `ActionRefusee` si la commande touche a un interdit."""
    if not commande or not commande.strip():
        raise ActionRefusee("commande vide")
    aplatie = " " + " ".join(commande.lower().split()) + " "
    for motif, raison in COMMANDES_INTERDITES:
        if motif.search(aplatie):
            raise ActionRefusee(f"refuse -- {raison}.")


#: Noms de variables d'environnement qui ne doivent JAMAIS etre passees a
#: une commande lancee par l'agent.
#:
#: TROUVE EN CONSTRUISANT CE MODULE, le 19 sept. : le processus de l'agent
#: charge `.env` (il en a besoin pour parler a Supabase), donc **35
#: variables sensibles** vivaient dans son environnement -- cles Bitvavo
#: (argent reel), jetons GitHub en ecriture, mots de passe Instagram et
#: TikTok. Or un sous-processus HERITE de l'environnement de son parent.
#:
#: Le filtre sur les commandes ne servait a rien contre ca : il refusait
#: bien `cat .env`, mais pas `printenv`, pas `env`, et surtout pas
#: `python3 -c "import os; print(dict(os.environ))"`. La protection
#: annoncee etait decorative.
#:
#: Un filtre de texte se contourne toujours ; retirer la valeur de
#: l'environnement, non. Les commandes de l'agent tournent donc avec un
#: environnement MINIMAL. Prix a payer, assume : les diagnostics qui
#: lisent le compte Bitvavo (`etat.py`, `bilan_journee.py`) ne
#: fonctionneront pas depuis l'agent -- il faudra les lancer autrement.
MOTS_SENSIBLES = ("KEY", "TOKEN", "SECRET", "PASSWORD", "PASSWD", "MDP",
                  "SUPABASE", "BITVAVO", "PIONEX", "BINANCE", "MOONX",
                  "TELEGRAM", "INSTAGRAM", "TIKTOK", "EXPO", "CLOUDFLARE",
                  "HUGGINGFACE", "OPENAI", "GEMINI", "ANTHROPIC", "CLAUDE")

#: Ce qu'une commande a le droit de voir. Tout le reste est retire.
#:
#: VIRTUAL_ENV est volontairement ABSENT : s'il etait transmis, un
#: `pip install` lance par l'agent s'installerait dans le `.venv` du
#: ROBOT et pourrait casser une dependance en production. Pour ses
#: propres programmes, l'agent cree un environnement dans son atelier.
VARIABLES_GARDEES = ("PATH", "HOME", "LANG", "LC_ALL", "TERM", "USER",
                     "SHELL", "PWD", "TZ")


def environnement_sans_cles() -> dict:
    """L'environnement minimal passe aux commandes de l'agent."""
    propre = {c: v for c, v in os.environ.items() if c in VARIABLES_GARDEES}
    # Ceinture et bretelles : si une variable gardee portait malgre tout
    # un nom sensible, elle saute aussi.
    return {c: v for c, v in propre.items()
            if not any(m in c.upper() for m in MOTS_SENSIBLES)}


def _tronquer(texte: str) -> str:
    if len(texte) <= SORTIE_MAX:
        return texte
    reste = len(texte) - SORTIE_MAX
    return texte[:SORTIE_MAX] + f"\n[... {reste} caracteres coupes ...]"


# ----------------------------------------------------------- les outils

def lire_fichier(args: dict) -> dict:
    chemin = chemin_sur(str(args.get("chemin", "")))
    if not os.path.isfile(chemin):
        return {"erreur": f"{args.get('chemin')} n'existe pas"}
    with open(chemin, "r", encoding="utf-8", errors="replace") as f:
        lignes = f.readlines()
    debut = max(1, int(args.get("depuis_la_ligne") or 1))
    combien = int(args.get("nombre_de_lignes") or 400)
    extrait = lignes[debut - 1:debut - 1 + combien]
    numerotees = "".join(f"{debut + i:5d}  {l}" for i, l in enumerate(extrait))
    return {"chemin": os.path.relpath(chemin, RACINE),
            "lignes_totales": len(lignes),
            "contenu": _tronquer(numerotees)}


def ecrire_fichier(args: dict) -> dict:
    chemin = chemin_sur(str(args.get("chemin", "")), pour_ecriture=True)
    contenu = args.get("contenu")
    if contenu is None:
        return {"erreur": "contenu manquant"}
    os.makedirs(os.path.dirname(chemin) or RACINE, exist_ok=True)
    existait = os.path.isfile(chemin)
    with open(chemin, "w", encoding="utf-8") as f:
        f.write(str(contenu))
    return {"ok": True, "chemin": os.path.relpath(chemin, RACINE),
            "action": "remplace" if existait else "cree",
            "octets": len(str(contenu).encode("utf-8"))}


def modifier_fichier(args: dict) -> dict:
    """Remplacement exact, et UNIQUE -- comme l'outil d'edition de Claude
    Code. Un texte present deux fois est refuse : le modele doit donner
    assez de contexte pour viser sans ambiguite, sinon il modifie la
    mauvaise occurrence sans que personne ne le voie."""
    chemin = chemin_sur(str(args.get("chemin", "")), pour_ecriture=True)
    ancien = str(args.get("ancien_texte") or "")
    nouveau = str(args.get("nouveau_texte") or "")
    if not ancien:
        return {"erreur": "ancien_texte manquant"}
    if not os.path.isfile(chemin):
        return {"erreur": f"{args.get('chemin')} n'existe pas"}
    with open(chemin, "r", encoding="utf-8") as f:
        source = f.read()
    occurrences = source.count(ancien)
    if occurrences == 0:
        return {"erreur": "ancien_texte introuvable tel quel (attention aux "
                           "espaces et aux accents)"}
    if occurrences > 1:
        return {"erreur": f"ancien_texte apparait {occurrences} fois : donne "
                           f"plus de contexte autour pour viser une seule"}
    with open(chemin, "w", encoding="utf-8") as f:
        f.write(source.replace(ancien, nouveau))
    return {"ok": True, "chemin": os.path.relpath(chemin, RACINE)}


def lister(args: dict) -> dict:
    chemin = chemin_sur(str(args.get("chemin") or "."))
    if not os.path.isdir(chemin):
        return {"erreur": f"{args.get('chemin')} n'est pas un dossier"}
    entrees = []
    for nom in sorted(os.listdir(chemin))[:300]:
        complet = os.path.join(chemin, nom)
        entrees.append(nom + ("/" if os.path.isdir(complet) else ""))
    return {"dossier": os.path.relpath(chemin, RACINE), "entrees": entrees}


def chercher(args: dict) -> dict:
    """grep dans le depot. Les secrets sont exclus du resultat."""
    motif = str(args.get("motif") or "")
    if not motif:
        return {"erreur": "motif manquant"}
    dossier = chemin_sur(str(args.get("dossier") or "."))
    resultat = subprocess.run(
        ["grep", "-rn", "--binary-files=without-match",
         "--exclude-dir=.git", "--exclude-dir=node_modules",
         "--exclude-dir=.venv", "--exclude-dir=.venv-luna",
         "--exclude=.env*", "-e", motif, dossier],
        capture_output=True, text=True, timeout=60)
    lignes = [l.replace(RACINE + os.sep, "")
              for l in resultat.stdout.splitlines()[:200]]
    return {"motif": motif, "trouvailles": _tronquer("\n".join(lignes)) or "(rien)"}


def executer(args: dict) -> dict:
    """Une commande shell dans le depot. C'est l'outil le plus puissant :
    tests, git, python, npm... tout passe par la."""
    commande = str(args.get("commande") or "")
    commande_sure(commande)
    delai = min(int(args.get("delai_secondes") or 120), DELAI_MAX)
    try:
        resultat = subprocess.run(
            commande, shell=True, cwd=RACINE, capture_output=True,
            text=True, timeout=delai, env=environnement_sans_cles())
    except subprocess.TimeoutExpired:
        return {"erreur": f"la commande a depasse {delai} secondes et a ete arretee"}
    sortie = (resultat.stdout or "") + (
        ("\n[erreurs]\n" + resultat.stderr) if resultat.stderr else "")
    return {"commande": commande, "code_retour": resultat.returncode,
            "sortie": _tronquer(sortie.strip()) or "(aucune sortie)"}


# -------------------------------------------------------- la memoire

#: LE MODE APPRENTISSAGE, demande par l'operateur le 19 sept. : « plus
#: j'avance dans le temps avec lui, plus il devient fort et intelligent ».
#:
#: Soyons exacts sur ce qui se passe et ce qui ne se passe pas. Le
#: CERVEAU ne change pas : reentrainer un modele demande des cartes
#: graphiques que ce serveur n'a pas, et ce n'est pas ce qui manque ici.
#: Ce qui le rend reellement plus fort avec le temps, c'est la meme chose
#: qui rend un collegue plus fort qu'un inconnu : il se souvient.
#:
#: Trois choses s'accumulent, et elles suffisent :
#:  - ce qu'il apprend sur Monsieur (ses preferences, ses decisions) ;
#:  - ce qu'il apprend sur les projets (pourquoi tel reglage, quel piege) ;
#:  - ses propres erreurs, pour ne pas les refaire.
#:
#: Le tout en fichiers texte relus a chaque conversation. Rien de magique,
#: mais un agent qui sait deja que le robot reel est a l'arret et pourquoi
#: repond mieux qu'un agent brillant qui l'ignore.
MEMOIRE = os.path.join(ATELIER, "memoire")
INDEX_MEMOIRE = os.path.join(MEMOIRE, "MEMOIRE.md")


def _nom_de_fichier(titre: str) -> str:
    propre = re.sub(r"[^a-z0-9]+", "-", titre.lower().strip()).strip("-")
    return (propre or "note")[:60] + ".md"


def noter_en_memoire(args: dict) -> dict:
    """Ecrit une note que l'agent relira dans ses prochaines conversations."""
    titre = str(args.get("titre") or "").strip()
    contenu = str(args.get("contenu") or "").strip()
    if not titre or not contenu:
        return {"erreur": "titre et contenu obligatoires"}
    categorie = str(args.get("categorie") or "projet").strip()

    os.makedirs(MEMOIRE, exist_ok=True)
    fichier = os.path.join(MEMOIRE, _nom_de_fichier(titre))
    import datetime as _dt
    aujourd_hui = _dt.date.today().isoformat()
    with open(fichier, "w", encoding="utf-8") as f:
        f.write(f"# {titre}\n\n"
                f"_categorie : {categorie} — note du {aujourd_hui}_\n\n"
                f"{contenu}\n")

    # L'index : une ligne par note, c'est lui qui est relu a chaque
    # conversation (les notes elles-memes ne sont ouvertes qu'au besoin).
    lignes = []
    if os.path.isfile(INDEX_MEMOIRE):
        with open(INDEX_MEMOIRE, "r", encoding="utf-8") as f:
            lignes = [l for l in f.read().splitlines()
                      if l.strip() and f"]({os.path.basename(fichier)})" not in l]
    resume = " ".join(contenu.split())[:130]
    lignes.append(f"- [{titre}]({os.path.basename(fichier)}) — {resume}")
    with open(INDEX_MEMOIRE, "w", encoding="utf-8") as f:
        f.write("\n".join(lignes) + "\n")
    return {"ok": True, "note": titre, "notes_en_memoire": len(lignes)}


def relire_memoire(args: dict) -> dict:
    """Relit une note complete, ou l'index si aucun titre n'est donne."""
    titre = str(args.get("titre") or "").strip()
    if not titre:
        if not os.path.isfile(INDEX_MEMOIRE):
            return {"memoire": "(vide pour l'instant)"}
        with open(INDEX_MEMOIRE, "r", encoding="utf-8") as f:
            return {"index": _tronquer(f.read())}
    fichier = os.path.join(MEMOIRE, _nom_de_fichier(titre))
    if not os.path.isfile(fichier):
        return {"erreur": f"aucune note nommee « {titre} »"}
    with open(fichier, "r", encoding="utf-8") as f:
        return {"titre": titre, "contenu": _tronquer(f.read())}


def oublier(args: dict) -> dict:
    """Retire une note devenue fausse. Une memoire perimee ment."""
    titre = str(args.get("titre") or "").strip()
    fichier = os.path.join(MEMOIRE, _nom_de_fichier(titre))
    if not os.path.isfile(fichier):
        return {"erreur": f"aucune note nommee « {titre} »"}
    os.remove(fichier)
    if os.path.isfile(INDEX_MEMOIRE):
        with open(INDEX_MEMOIRE, "r", encoding="utf-8") as f:
            lignes = [l for l in f.read().splitlines()
                      if l.strip() and f"]({os.path.basename(fichier)})" not in l]
        with open(INDEX_MEMOIRE, "w", encoding="utf-8") as f:
            f.write("\n".join(lignes) + ("\n" if lignes else ""))
    return {"ok": True, "oubliee": titre}


def index_memoire() -> str:
    """L'index, injecte dans le contexte a CHAQUE conversation -- c'est ce
    qui fait qu'il « se souvient » sans qu'on lui demande de chercher."""
    if not os.path.isfile(INDEX_MEMOIRE):
        return ""
    try:
        with open(INDEX_MEMOIRE, "r", encoding="utf-8") as f:
            return f.read().strip()[:3000]
    except OSError:
        return ""


# ------------------------------------------------------------- le web

#: Adresses que l'agent ne doit JAMAIS aller chercher.
#:
#: Ce n'est pas de la prudence excessive : sur un serveur loue, l'adresse
#: 169.254.169.254 rend les identifiants de l'hebergeur a qui la demande,
#: sans mot de passe. Et `localhost` donne acces aux services internes de
#: la machine. Un agent a qui on dit « va lire cette page » et qui recoit
#: une URL piegee -- depuis un resultat de recherche, une page web, un
#: message -- irait la chercher sans se poser de question. On coupe donc
#: a la source : seules les adresses publiques sont permises.
RESEAUX_INTERDITS = (
    re.compile(r"^https?://(localhost|127\.|0\.0\.0\.0|\[::1\])", re.I),
    re.compile(r"^https?://169\.254\."),                       # metadonnees cloud
    re.compile(r"^https?://10\."),                             # reseau prive
    re.compile(r"^https?://192\.168\."),                       # reseau prive
    re.compile(r"^https?://172\.(1[6-9]|2\d|3[01])\."),        # reseau prive
    re.compile(r"^(?!https?://)", re.I),                       # ni file://, ni ftp://
)


def url_sure(url: str) -> str:
    url = (url or "").strip()
    if not url:
        raise ActionRefusee("adresse vide")
    for motif in RESEAUX_INTERDITS:
        if motif.search(url):
            raise ActionRefusee(
                "adresse interne ou protocole non autorise. L'agent ne "
                "consulte que des sites publics en http/https.")
    return url


def _texte_depuis_html(html: str) -> str:
    """Rend le texte lisible d'une page. Pas de dependance : le depot
    tient a n'utiliser que la bibliotheque standard."""
    html = re.sub(r"(?is)<(script|style|noscript|svg)[^>]*>.*?</\1>", " ", html)
    html = re.sub(r"(?is)<br\s*/?>|</p>|</div>|</li>|</h[1-6]>", "\n", html)
    texte = re.sub(r"(?s)<[^>]+>", " ", html)
    for avant, apres in (("&nbsp;", " "), ("&amp;", "&"), ("&lt;", "<"),
                         ("&gt;", ">"), ("&quot;", '"'), ("&#39;", "'")):
        texte = texte.replace(avant, apres)
    texte = re.sub(r"[ \t]+", " ", texte)
    return re.sub(r"\n\s*\n\s*\n+", "\n\n", texte).strip()


#: Proxy pour la navigation de l'agent UNIQUEMENT (variable `PROXY_WEB`).
#:
#: Demande de l'operateur le 19 sept. : « mets-lui un VPN, je veux pas
#: qu'il soit tracable ». Le point important est le mot UNIQUEMENT : on
#: ne fait pas passer tout le serveur par un VPN, parce que le robot
#: parle a Bitvavo depuis cette machine. Une cle d'API qui se met
#: soudain a arriver d'un autre pays, c'est au mieux un blocage, au pire
#: un compte gele -- avec de l'argent dessus.
#:
#: Ici, seules les pages que l'agent consulte passent par le proxy. Le
#: robot, lui, continue de sortir normalement.
#:
#:     PROXY_WEB=http://127.0.0.1:8118   (Tor via privoxy, gratuit)
#:     PROXY_WEB=http://utilisateur:motdepasse@serveur-vpn:port
#:
#: Absent : l'agent sort en direct, comme aujourd'hui.
def _proxy_web() -> str:
    return os.environ.get("PROXY_WEB", "").strip()


#: Passerelle vers Tor. `tor` parle SOCKS5, qu'urllib ne sait pas
#: utiliser ; `privoxy` traduit du HTTP vers SOCKS et sait transmettre
#: les noms en .onion a Tor au lieu d'essayer de les resoudre lui-meme
#: (sans quoi aucune adresse .onion ne s'ouvre). Voir
#: ops/installer_tor.sh.
PROXY_TOR_DEFAUT = "http://127.0.0.1:8118"


def _proxy_tor() -> str:
    return os.environ.get("PROXY_TOR", PROXY_TOR_DEFAUT).strip()


def tor_disponible() -> bool:
    import socket
    import urllib.parse

    cible = urllib.parse.urlparse(_proxy_tor())
    try:
        with socket.create_connection(
                (cible.hostname or "127.0.0.1", cible.port or 8118), timeout=3):
            return True
    except OSError:
        return False


def _telecharger(url: str, delai: int = 25, via_tor: bool = False) -> str:
    import urllib.error
    import urllib.request

    requete = urllib.request.Request(url, headers={
        "user-agent": "Mozilla/5.0 (X11; Linux x86_64) alluxe-agent/2.0",
        "accept-language": "fr,en;q=0.8",
    })
    # Une adresse .onion n'existe que dans Tor : la router autrement ne
    # rate pas seulement, ca fait fuiter la demande vers le DNS public.
    if ".onion" in url.lower():
        via_tor = True
    if via_tor and not tor_disponible():
        raise ActionRefusee(
            "Tor n'est pas installe ou pas demarre sur ce serveur. "
            "Demande a Monsieur de lancer ops/installer_tor.sh.")

    proxy = _proxy_tor() if via_tor else _proxy_web()
    ouvrir = urllib.request.urlopen
    if proxy:
        gestionnaire = urllib.request.ProxyHandler({"http": proxy, "https": proxy})
        ouvrir = urllib.request.build_opener(gestionnaire).open
    try:
        with ouvrir(requete, timeout=delai) as reponse:
            # Borne dure : une page de 200 Mo ne doit pas remplir la memoire.
            brut = reponse.read(3_000_000)
    except urllib.error.HTTPError as e:
        raise ActionRefusee(f"le site a repondu {e.code}") from e
    except Exception as e:                                   # noqa: BLE001
        raise ActionRefusee(f"page injoignable : {e}") from e
    return brut.decode("utf-8", errors="replace")


def lire_page_web(args: dict) -> dict:
    """Lit une page et rend son texte. `via_tor` pour passer par Tor."""
    url = url_sure(str(args.get("url", "")))
    via_tor = bool(args.get("via_tor"))
    texte = _texte_depuis_html(_telecharger(url, via_tor=via_tor))
    return {"url": url,
            "reseau": "Tor" if (via_tor or ".onion" in url.lower()) else "direct",
            "texte": _tronquer(texte) or "(page vide)"}


def chercher_sur_le_web(args: dict) -> dict:
    """Recherche web, sans cle d'API (DuckDuckGo)."""
    import urllib.parse

    question = str(args.get("question") or "").strip()
    if not question:
        return {"erreur": "question manquante"}
    # Le point d'entree "lite" plutot que "html" : le second ne rend plus
    # aucun resultat exploitable (verifie le 19 sept., 0 lien trouve).
    # Et les attributs y sont en guillemets SIMPLES -- un motif ecrit pour
    # des guillemets doubles trouve zero resultat sans rien signaler.
    via_tor = bool(args.get("via_tor"))
    url = "https://lite.duckduckgo.com/lite/?q=" + urllib.parse.quote(question)
    html = _telecharger(url, via_tor=via_tor)
    resultats = []
    for lien, titre in re.findall(
            r"""(?is)<a[^>]+href=["']([^"']*uddg=[^"']+)["'][^>]*>(.*?)</a>""",
            html)[:8]:
        correspondance = re.search(r"uddg=([^&\"']+)", lien)
        if correspondance:
            lien = urllib.parse.unquote(correspondance.group(1))
        titre_propre = _texte_depuis_html(titre).strip()
        if titre_propre:
            resultats.append({"titre": titre_propre, "lien": lien})
    return {"question": question,
            "reseau": "Tor" if via_tor else "direct",
            "resultats": resultats or "(rien trouve)"}


def chercher_articles_scientifiques(args: dict) -> dict:
    """Publications universitaires : arXiv (physique, maths, finance
    quantitative) puis Semantic Scholar. Les deux sont gratuits et sans
    cle -- c'est la 'bibliotheque universitaire' demandee par l'operateur
    le 19 sept., utile en particulier pour chercher des strategies de
    trading publiees et mesurees."""
    import urllib.parse

    sujet = str(args.get("sujet") or "").strip()
    if not sujet:
        return {"erreur": "sujet manquant"}
    combien = min(int(args.get("combien") or 6), 15)

    articles = []
    try:
        flux = _telecharger(
            "http://export.arxiv.org/api/query?search_query=all:"
            + urllib.parse.quote(sujet)
            + f"&start=0&max_results={combien}&sortBy=relevance")
        for entree in re.findall(r"(?s)<entry>(.*?)</entry>", flux):
            titre = re.search(r"(?s)<title>(.*?)</title>", entree)
            resume = re.search(r"(?s)<summary>(.*?)</summary>", entree)
            lien = re.search(r'<id>(.*?)</id>', entree)
            articles.append({
                "source": "arXiv",
                "titre": " ".join((titre.group(1) if titre else "").split()),
                "resume": " ".join((resume.group(1) if resume else "").split())[:600],
                "lien": lien.group(1) if lien else "",
            })
    except ActionRefusee as e:
        articles.append({"source": "arXiv", "erreur": str(e)})

    if len(articles) < combien:
        try:
            brut = _telecharger(
                "https://api.semanticscholar.org/graph/v1/paper/search?query="
                + urllib.parse.quote(sujet)
                + f"&limit={combien}&fields=title,abstract,year,url")
            import json as _json
            for p in (_json.loads(brut).get("data") or []):
                articles.append({
                    "source": f"Semantic Scholar {p.get('year') or ''}".strip(),
                    "titre": p.get("title") or "",
                    "resume": (p.get("abstract") or "")[:600],
                    "lien": p.get("url") or "",
                })
        except Exception:                                    # noqa: BLE001
            pass

    return {"sujet": sujet, "articles": articles[:combien] or "(rien trouve)"}


#: Les seuls services que l'agent peut demarrer ou arreter.
#:
#: Demande de l'operateur le 20 sept. : « je veux que l'agent puisse
#: gerer les comptes demo ». Modifier leur reglage sans pouvoir les
#: relancer ne servirait a rien -- un robot lit sa configuration AU
#: DEMARRAGE, et seulement la.
#:
#: Ce qui reste hors de sa portee, et pourquoi :
#:   robot-dual-live  ARGENT REEL.
#:   robot-demo       la simulation de REFERENCE, celle sur laquelle
#:                    Monsieur decide son depot du 28. L'arreter ou la
#:                    relancer en pleine mesure la detruirait.
#:   alluxe-agent     lui-meme. Se redemarrer en pleine reponse le
#:                    ferait disparaitre au milieu d'une phrase.
SIMULATIONS_PILOTABLES = ("robot-demo2", "robot-demo3")


def piloter_simulation(args: dict) -> dict:
    """Demarre, arrete ou relance un compte d'EXPERIENCE.

    Un robot ne relit sa configuration qu'au demarrage : changer
    `robot.demo2.json` sans relancer le service ne change rien, et
    croire le contraire ferait mesurer l'ancien reglage en pensant
    mesurer le nouveau. C'est exactement le piege que CLAUDE.md decrit
    trois fois -- « verifier qu'un reglage est LU ne prouve rien, il
    faut verifier qu'il s'EXECUTE ».
    """
    service = str(args.get("service") or "").strip()
    action = str(args.get("action") or "").strip().lower()

    if service not in SIMULATIONS_PILOTABLES:
        raise ActionRefusee(
            f"« {service} » n'est pas pilotable depuis ici. Seuls "
            f"{', '.join(SIMULATIONS_PILOTABLES)} le sont : ce sont des "
            f"comptes d'experience, ils ne coutent rien quand ils se "
            f"trompent. robot-dual-live engage l'argent reel et "
            f"robot-demo porte la mesure de reference.")
    if action not in ("start", "stop", "restart"):
        raise ActionRefusee(
            "action inconnue : start, stop ou restart uniquement.")

    # LA MEMOIRE EST LA VRAIE LIMITE DE CE SERVEUR.
    #
    # Mesure le 20 sept. : chaque robot reclame 1 200 a 1 900 Mo, la
    # machine en a 3 800 au total. Un demarrage de trop, et le noyau tue
    # un processus au hasard -- possiblement la simulation de reference.
    # C'est deja arrive DEUX fois le 19 septembre.
    if action in ("start", "restart"):
        libre = _memoire_disponible_mo()
        if libre is not None and libre < 1300:
            raise ActionRefusee(
                f"pas assez de memoire : {libre} Mo disponibles, il en "
                f"faut environ 1 300. Demarrer maintenant risque de tuer "
                f"une simulation en cours. Dis-le a Monsieur : ce serveur "
                f"ne tient pas trois robots.")

    r = subprocess.run(["sudo", "-n", "systemctl", action, service],
                       capture_output=True, text=True, timeout=90)
    if r.returncode != 0:
        return {"erreur": (r.stderr or r.stdout).strip()[:300]}
    etat = subprocess.run(["systemctl", "is-active", service],
                          capture_output=True, text=True, timeout=15)
    return {"service": service, "action": action,
            "etat": etat.stdout.strip() or "inconnu"}


def _memoire_disponible_mo() -> "int | None":
    try:
        with open("/proc/meminfo") as fh:
            for ligne in fh:
                if ligne.startswith("MemAvailable:"):
                    return int(ligne.split()[1]) // 1024
    except OSError:
        return None
    return None


def etat_services(_args: dict) -> dict:
    """Lecture seule : qui tourne, qui ne tourne pas."""
    services = ("robot-dual-live", "robot-demo", "robot-demo2",
                "robot-demo3", "alluxe-agent")
    etats = {}
    for s in services:
        r = subprocess.run(["systemctl", "is-active", s],
                           capture_output=True, text=True, timeout=15)
        etats[s] = r.stdout.strip() or "inconnu"
    return {"services": etats,
            "memoire_disponible_mo": _memoire_disponible_mo(),
            "note": "robot-dual-live est volontairement a l'arret tant que "
                    "Leny n'a pas redepose d'argent. robot-demo2 et "
                    "robot-demo3 sont des comptes d'experience : tu peux "
                    "les piloter et modifier leur configuration."}


OUTILS_ACTION = {
    "lire_fichier": lire_fichier,
    "ecrire_fichier": ecrire_fichier,
    "modifier_fichier": modifier_fichier,
    "lister": lister,
    "chercher": chercher,
    "executer": executer,
    "etat_services": etat_services,
    "piloter_simulation": piloter_simulation,
    "chercher_sur_le_web": chercher_sur_le_web,
    "lire_page_web": lire_page_web,
    "chercher_articles_scientifiques": chercher_articles_scientifiques,
    "noter_en_memoire": noter_en_memoire,
    "relire_memoire": relire_memoire,
    "oublier": oublier,
}


def _p(requis=None, **proprietes):
    """Le schema d'un outil. `requis` liste les parametres obligatoires.

    Sans lui, un parametre passe en mot-cle devenait une PROPRIETE du
    schema : l'outil aurait annonce au modele un argument « requis »
    qu'il n'attend pas, et le modele aurait pu le remplir. Un schema qui
    decrit mal l'outil est pire qu'un schema absent.
    """
    schema = {"type": "object", "properties": proprietes}
    if requis:
        schema["required"] = list(requis)
    return schema


DESCRIPTION_OUTILS_ACTION = [
    {"type": "function", "function": {
        "name": "lire_fichier",
        "description": "Lit un fichier, avec numeros de ligne.",
        "parameters": _p(
            chemin={"type": "string", "description": "chemin relatif au depot"},
            depuis_la_ligne={"type": "integer"},
            nombre_de_lignes={"type": "integer"}),
    }},
    {"type": "function", "function": {
        "name": "ecrire_fichier",
        "description": "Cree un fichier ou remplace tout son contenu.",
        "parameters": _p(chemin={"type": "string"}, contenu={"type": "string"}),
    }},
    {"type": "function", "function": {
        "name": "modifier_fichier",
        "description": "Remplace un extrait exact (unique) dans un fichier.",
        "parameters": _p(chemin={"type": "string"},
                          ancien_texte={"type": "string"},
                          nouveau_texte={"type": "string"}),
    }},
    {"type": "function", "function": {
        "name": "lister",
        "description": "Liste un dossier.",
        "parameters": _p(chemin={"type": "string"}),
    }},
    {"type": "function", "function": {
        "name": "chercher",
        "description": "Cherche un texte dans le depot (grep).",
        "parameters": _p(motif={"type": "string"}, dossier={"type": "string"}),
    }},
    {"type": "function", "function": {
        "name": "executer",
        "description": "Commande shell : tests, git, python3, npm, journalctl. L'outil principal.",
        "parameters": _p(commande={"type": "string"},
                          delai_secondes={"type": "integer"}),
    }},
    {"type": "function", "function": {
        "name": "etat_services",
        "description": "Quels services tournent.",
        "parameters": _p(),
    }},
    {"type": "function", "function": {
        "name": "piloter_simulation",
        "description": ("Demarre, arrete ou relance un compte d'EXPERIENCE "
                        "(robot-demo2, robot-demo3). Indispensable apres "
                        "avoir modifie robot.demo2.json ou "
                        "robot.demo3.json : un robot ne relit sa "
                        "configuration qu'au demarrage. Refuse pour le "
                        "robot reel et pour la simulation de reference."),
        "parameters": _p(
            service={"type": "string",
                     "enum": ["robot-demo2", "robot-demo3"]},
            action={"type": "string",
                    "enum": ["start", "stop", "restart"]},
            requis=["service", "action"]),
    }},
    {"type": "function", "function": {
        "name": "chercher_sur_le_web",
        "description": "Recherche web. Des qu'une question sort du serveur.",
        "parameters": _p(
            question={"type": "string"},
            via_tor={"type": "boolean",
                     "description": "passer par Tor (anonyme, plus lent, "
                                    "certains sites le refusent). Par defaut non."}),
    }},
    {"type": "function", "function": {
        "name": "lire_page_web",
        "description": "Ouvre une page web et rend son texte.",
        "parameters": _p(
            url={"type": "string"},
            via_tor={"type": "boolean",
                     "description": "passer par Tor. Force automatiquement "
                                    "pour une adresse .onion."}),
    }},
    {"type": "function", "function": {
        "name": "chercher_articles_scientifiques",
        "description": "Publications universitaires (arXiv, Semantic Scholar).",
        "parameters": _p(sujet={"type": "string"},
                          combien={"type": "integer"}),
    }},
    {"type": "function", "function": {
        "name": "noter_en_memoire",
        "description": "Retient pour les prochaines conversations : preference de Monsieur, decision, piege. Des que tu apprends du neuf.",
        "parameters": _p(titre={"type": "string"},
                          contenu={"type": "string"},
                          categorie={"type": "string",
                                     "description": "monsieur, projet, piege, methode"}),
    }},
    {"type": "function", "function": {
        "name": "relire_memoire",
        "description": "Relit une note (avec titre) ou la liste (sans titre).",
        "parameters": _p(titre={"type": "string"}),
    }},
    {"type": "function", "function": {
        "name": "oublier",
        "description": "Efface une note perimee.",
        "parameters": _p(titre={"type": "string"}),
    }},
]
