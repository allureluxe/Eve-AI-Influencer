#!/usr/bin/env python3
"""Le labo demande des idees a ChatGPT et a Claude, et les range pour test.

POURQUOI CE SCRIPT EXISTE

Le 26 septembre au soir, le Strategy Lab affichait **108 strategies
testees, 108 rejetees**, toutes avec le meme motif : « barre backtest
non franchie ». Le service tournait parfaitement. Le probleme etait
ailleurs.

`gold_bot/lab.py` est une BOUCLE FERMEE : six familles ecrites en dur
(momentum, cassure, filtre ADX, risque, volatilite, unite de temps),
puis une variation d'UN reglage par tour — momentum 14 ou 28, ADX 16 ou
20. Aucune idee exterieure ne peut y entrer. Il pouvait tourner un an
sans jamais essayer autre chose.

Or `BotConfig` expose **129 reglages** applicables. Le labo en explorait
six.

CE QUE FAIT CE SCRIPT. Il pose la question a ChatGPT et a Claude —
separement — et range leurs hypotheses dans `lab_research`, d'ou le labo
les tirera. Les deux cerveaux n'ont toujours AUCUN acces au systeme : ils
recoivent la liste des reglages disponibles et rendent du texte.

    python3 ops/labo_recherche.py
    python3 ops/labo_recherche.py --sujet "sorties" --combien 4
    python3 ops/labo_recherche.py --veille

LE PIEGE PRINCIPAL, ET IL EST SILENCIEUX. Une hypothese dont les
reglages ne figurent pas dans `BotConfig` produit un backtest qui teste
**exactement la configuration par defaut** : `_apply` ignore les cles
inconnues sans rien dire. On croirait tester une idee neuve et on
remesurerait le temoin, indefiniment. D'ou la validation stricte
ci-dessous : une hypothese dont aucun reglage n'est reconnu est REFUSEE,
et on dit lesquels ont ete rejetes.
"""
from __future__ import annotations

import argparse
import dataclasses
import json
import os
import re
import sys
import urllib.error
import urllib.request

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RACINE)

from gold_bot.env import charger_env  # noqa: E402

charger_env()

from gold_bot.settings import BotConfig  # noqa: E402
from luna.cerveaux import CerveauErreur, consulter  # noqa: E402


def reglages_connus() -> set[str]:
    """Les noms que `lab._apply` sait REELLEMENT poser sur la config.

    Lu dans les dataclasses, jamais recopie a la main : une liste figee
    ici se desynchroniserait du moteur au premier ajout de reglage, et
    on refuserait des hypotheses valides sans comprendre pourquoi.
    """
    cfg = BotConfig.load(os.getenv("GB_CONFIG", "robot.bitvavo.json"))
    noms: set[str] = set()
    for section in (cfg.strategy, cfg.trade, cfg.risk):
        noms |= {f.name for f in dataclasses.fields(section)}
    return noms


QUESTION = """Le robot teste des strategies de trading crypto au comptant
(achat seul, pas de vente a decouvert), sur des bougies journalieres ou
intrajournalieres, avec des frais de 0,25 % par cote.

Son laboratoire n'explore que six familles depuis des semaines : momentum,
cassure de canal Donchian, filtre ADX, ratio rendement/risque, multiple
d'ATR pour le stop, et unite de temps. 108 configurations testees, 108
rejetees. Il tourne en rond.

SUJET DEMANDE : {sujet}

Propose {combien} hypotheses TESTABLES et VRAIMENT DIFFERENTES de ces six
familles. Chacune doit :
  - reposer sur un mecanisme de marche que tu peux nommer, pas sur un
    reglage au hasard ;
  - s'exprimer avec les reglages disponibles ci-dessous, et UNIQUEMENT
    ceux-la ;
  - dire a quelle condition elle serait FAUSSE.

Reglages disponibles (tout autre nom sera rejete) :
{reglages}

Reponds UNIQUEMENT par un tableau JSON, sans texte autour :
[
  {{"titre": "...",
    "famille": "momentum|reversion|volatilite|sortie|risque|filtre",
    "hypothese": "le mecanisme, en une ou deux phrases",
    "conditions": "ce qui la rendrait fausse",
    "params": {{"nom_du_reglage": valeur, ...}}}}
]"""

VEILLE = """Quelles approches, outils ou agents d'IA appliques au trading
algorithmique sont apparus recemment et meriteraient d'etre regardes par
un petit laboratoire autonome qui teste des strategies crypto au comptant ?

Ne cite que ce dont tu es raisonnablement sur, avec le nom exact. Pour
chacun : ce qu'il apporte, et ce qu'il faudrait verifier avant de s'en
servir. Si tu n'es pas sur qu'une chose existe encore, dis-le.

Reponds en texte, dense, sans flatterie."""


def _extraire_json(texte: str) -> list:
    """Le tableau JSON, meme bavarde, meme TRONQUE.

    Trois tolerances, chacune pour une panne observee le 26 septembre :

    1. LES BALISES ET LE BAVARDAGE. Les modeles ajoutent « Voici les
       hypotheses : » et des ```json. Exiger une reponse propre ferait
       echouer une analyse par ailleurs bonne.

    2. LA TRONCATURE, et c'est la plus couteuse. A trois hypotheses, la
       reponse de Claude depasse le budget de jetons et le tableau se
       coupe EN PLEIN MILIEU d'un objet. `json.loads` echoue alors sur
       la totalite, et on jette deux hypotheses parfaitement valides
       avec la troisieme. On recupere donc objet par objet, en comptant
       les accolades.

    3. UN SEUL OBJET au lieu d'un tableau, quand le modele n'en a
       propose qu'un.
    """
    texte = re.sub(r"^```(?:json)?|```$", "", texte.strip(),
                   flags=re.MULTILINE).strip()
    try:
        d = json.loads(texte)
        return d if isinstance(d, list) else [d]
    except json.JSONDecodeError:
        pass
    debut, fin = texte.find("["), texte.rfind("]")
    if debut >= 0 and fin > debut:
        try:
            return json.loads(texte[debut:fin + 1])
        except json.JSONDecodeError:
            pass

    # RECUPERATION OBJET PAR OBJET. On avance en comptant les accolades,
    # en ignorant celles qui sont dans une chaine, et on garde chaque
    # objet complet. Un objet tronque en fin de texte est simplement
    # abandonne — les precedents, eux, sont sauves.
    objets: list = []
    profondeur = 0
    depart = -1
    dans_chaine = False
    echappe = False
    for i, ch in enumerate(texte):
        if dans_chaine:
            if echappe:
                echappe = False
            elif ch == "\\":
                echappe = True
            elif ch == '"':
                dans_chaine = False
            continue
        if ch == '"':
            dans_chaine = True
        elif ch == "{":
            if profondeur == 0:
                depart = i
            profondeur += 1
        elif ch == "}":
            profondeur -= 1
            if profondeur == 0 and depart >= 0:
                try:
                    objets.append(json.loads(texte[depart:i + 1]))
                except json.JSONDecodeError:
                    pass
                depart = -1
    return objets


def valider(idee: dict, connus: set[str]) -> tuple[dict | None, str]:
    """Rend l'idee nettoyee, ou None et la raison du refus."""
    params = idee.get("params")
    if not isinstance(params, dict) or not params:
        return None, "aucun reglage propose"
    gardes = {k: v for k, v in params.items() if k in connus}
    rejetes = sorted(set(params) - set(gardes))
    if not gardes:
        return None, f"aucun reglage reconnu (proposes : {', '.join(rejetes)})"
    idee = dict(idee)
    idee["params"] = gardes
    if rejetes:
        idee["conditions"] = (str(idee.get("conditions", "")) +
                              f" [reglages ignores : {', '.join(rejetes)}]").strip()
    return idee, ""


def deposer(idees: list[dict], mode: str) -> int:
    url = os.environ.get("SUPABASE_URL", "").rstrip("/")
    cle = os.environ.get("SUPABASE_SERVICE_KEY", "")
    if not url or not cle:
        print("SUPABASE absent, rien depose")
        return 0
    lignes = [{
        "sujet": str(i.get("titre", ""))[:300],
        "mode": mode,
        "famille": str(i.get("famille", "inconnu"))[:60],
        "titre": str(i.get("titre", ""))[:300],
        "url": str(i.get("source", ""))[:500],
        "hypothese": json.dumps({"texte": i.get("hypothese", ""),
                                 "params": i.get("params", {}),
                                 "cerveau": i.get("cerveau", "")},
                                ensure_ascii=False)[:4000],
        "conditions": str(i.get("conditions", ""))[:2000],
        "statut": "IDEATED",
    } for i in idees]
    if not lignes:
        return 0
    req = urllib.request.Request(
        f"{url}/rest/v1/lab_research", method="POST",
        data=json.dumps(lignes).encode(),
        headers={"apikey": cle, "Authorization": f"Bearer {cle}",
                 "Content-Type": "application/json",
                 "Prefer": "return=minimal"})
    try:
        urllib.request.urlopen(req, timeout=60).read()
        return len(lignes)
    except urllib.error.HTTPError as e:
        print(f"depot refuse : {e.code} {e.read().decode()[:250]}")
        return 0


def main() -> int:
    a = argparse.ArgumentParser(description=__doc__)
    a.add_argument("--sujet", default="entrees, sorties et gestion du risque")
    a.add_argument("--combien", type=int, default=3)
    a.add_argument("--veille", action="store_true",
                   help="demander ce qui existe ailleurs, sans deposer")
    a.add_argument("--cerveaux", default="chatgpt,claude")
    args = a.parse_args()

    lesquels = tuple(x.strip() for x in args.cerveaux.split(",") if x.strip())

    if args.veille:
        # LA VEILLE NE DEPOSE RIEN. Elle rend du texte a lire : une
        # recommandation d'outil n'est pas une hypothese testable, et la
        # ranger dans la file a tester serait un abus de langage.
        r = consulter(VEILLE, lesquels=lesquels, max_jetons=3000)
        for nom, res in r.items():
            print(f"\n===== {nom.upper()} =====")
            print(res.get("reponse") or f"(injoignable : {res.get('erreur')})")
        return 0

    connus = reglages_connus()
    print(f"  {len(connus)} reglages applicables par le labo")
    question = QUESTION.format(
        sujet=args.sujet, combien=args.combien,
        reglages=", ".join(sorted(connus)))

    try:
        # DE LA PLACE POUR REFLECHIR ET POUR ECRIRE.
        #
        # Les deux modeles produisent un bloc de raisonnement
        # AVANT leur texte, et le budget le compte. Sur une
        # question difficile, 1 200 jetons partent entierement
        # dans la reflexion et le contenu ressort VIDE — avec
        # un `finish_reason: stop` parfaitement normal, donc
        # sans rien qui signale le probleme.
        reponses = consulter(question, lesquels=lesquels,
                             max_jetons=8000)
    except CerveauErreur as e:
        print(f"echec : {e}")
        return 1

    retenues: list[dict] = []
    for nom, res in reponses.items():
        if not res.get("ok"):
            print(f"  {nom:9} injoignable : {str(res.get('erreur'))[:90]}")
            continue
        brutes = _extraire_json(res["reponse"])
        gardees = 0
        for idee in brutes:
            if not isinstance(idee, dict):
                continue
            propre, refus = valider(idee, connus)
            if propre is None:
                print(f"  {nom:9} REFUSEE « {str(idee.get('titre'))[:40]} » : {refus}")
                continue
            propre["cerveau"] = nom
            retenues.append(propre)
            gardees += 1
        print(f"  {nom:9} {len(brutes)} proposee(s), {gardees} retenue(s)")

    n = deposer(retenues, mode=args.sujet[:40])
    print(f"\n  {n} hypothese(s) deposee(s) dans lab_research (statut IDEATED)")
    for i in retenues:
        print(f"    [{i['cerveau']:7}] {str(i.get('titre'))[:52]:52} "
              f"{list(i['params'])}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
