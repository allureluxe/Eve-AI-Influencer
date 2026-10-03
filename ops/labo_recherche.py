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
import hashlib
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
from ops.agent_outils import recherche_idee_trading  # noqa: E402


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


QUESTION = """Tu es le responsable R&D d'un laboratoire quantitatif multi-marches.
Le but est de fabriquer le plus grand portefeuille possible d'hypotheses testables,
puis de laisser le Strategy Lab les falsifier avec frais, spread, glissement,
liquidite et tests hors echantillon.

COUVERTURE : crypto spot et microstructure; actions/bourse et facteurs;
futures, commodities, indices et FX; taux/obligations; banques centrales
(BCE, Fed, BoE, BoJ); credit et conditions de financement; volatilite;
intermarket; macro; resultats et revisions; ETF; regulation; news/event-driven;
regimes; cross-sectional; pairs; saisonnalite; gestion du risque.
Toute information publique doit etre horodatee : jamais de look-ahead.

RECHERCHE : priorite aux publications universitaires, working papers, arXiv,
SSRN, NBER, BIS et institutions. Quant/market data ensuite. Forums et marketing
servent seulement a generer des idees, jamais de preuve.

MODE TRADING INFO : transforme une information de marche en regle reproductible
et datee. Signale toute feature necessaire avant de la tester. Ne donne jamais
une instruction de trading reel.

Le labo explore deja momentum, Donchian, ADX, rendement/risque, ATR-stop et
timeframes. Priorise donc les familles nouvelles et les combinaisons distinctes.

SUJET DEMANDE : {sujet}

Propose {combien} hypotheses. Cherche volontairement la diversite : entrees,
sorties, regimes, volatilite, facteurs, cross-sectional, macro, intermarket,
event-driven, risque. Chaque hypothese doit utiliser au maximum 8 reglages, dont au moins un reglage directement lie au mecanisme de la strategie. Ne pas empiler des reglages de risque/execution sans necessite.

Chaque hypothese doit nommer son mecanisme, etre falsifiable,
indiquer ce qui la rendrait fausse, donner les sources exactes et les biais
possibles (look-ahead, survivorship, publication, data-snooping).

Reglages disponibles :
{reglages}

FORMAT DES VALEURS (sinon le test est fausse -- 3 oct. 2026, un tiers des
essais rendaient zero trade a cause de ca) :
- tout reglage *_percentile est une FRACTION entre 0 et 1 (0.60, pas 60) ;
- donchian_entrees est une LISTE d'horizons en bougies ([10] ou [10, 20]) ;
- les unites de temps (*_tf) s'ecrivent M5, M15, M30, H1, H4 ou D1 (pas 1h, 4h, 1d) ;
- strategie_famille, si tu la donnes, vaut exactement l'une de :
  tendance, donchian, momentum, reversion. Le champ "famille" ci-dessous
  n'est qu'une etiquette de classement, pas la methode executee.

Reponds UNIQUEMENT par tableau JSON :
[
  {{"titre":"...","famille":"momentum|reversion|volatilite|sortie|risque|filtre|macro|intermarket|event|feature_requise",
    "hypothese":"mecanisme testable","conditions":"ce qui la rendrait fausse",
    "params":{{"nom_du_reglage": valeur}},
    "feature_requise":"","sources":[{{"titre":"...","url":"...","annee":2025}}]}}
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


FAMILLES_STRATEGIE = {"tendance", "momentum", "donchian", "reversion"}
FAMILLES_RECHERCHE_EXECUTABLES = FAMILLES_STRATEGIE | {"volatilite", "risque", "filtre", "sortie"}
# Compatibilite des tests/consommateurs : ce nom signifie désormais
# « catégorie de recherche exécutable », pas « valeur de strategy.famille ».
FAMILLES_EXECUTABLES = FAMILLES_RECHERCHE_EXECUTABLES


def valider(idee: dict, connus: set[str]) -> tuple[dict | None, str]:
    """Rend l'idee nettoyee, ou None et la raison du refus.

    Le moteur actuel n'execute que quatre familles. Une idee macro/event/
    intermarket peut rester precieuse pour la R&D, mais elle ne doit jamais
    etre silencieusement testee comme une tendance simplement parce qu'elle
    contient un reglage connu. Elle sera deposee en FEATURE_REQUIRED.
    """
    famille = str(idee.get("famille") or "").strip().lower()
    if famille not in FAMILLES_RECHERCHE_EXECUTABLES:
        idee = dict(idee)
        idee["famille"] = famille or "inconnu"
        return idee, "FEATURE_REQUIRED"
    params = idee.get("params")
    if not isinstance(params, dict) or not params:
        return None, "aucun reglage propose"
    if len(params) > 8:
        return None, f"trop de reglages ({len(params)}), maximum 8 pour eviter le sur-ajustement"
    gardes = {k: v for k, v in params.items() if k in connus}
    rejetes = sorted(set(params) - set(gardes))
    if not gardes:
        return None, f"aucun reglage reconnu (proposes : {', '.join(rejetes)})"
    idee = dict(idee)
    idee["params"] = gardes
    if famille not in FAMILLES_STRATEGIE:
        idee["params"]["strategie_famille"] = "tendance"
    if rejetes:
        idee["conditions"] = (str(idee.get("conditions", "")) +
                              f" [reglages ignores : {', '.join(rejetes)}]").strip()
    return idee, ""


def _empreinte_idee(idee: dict) -> str:
    """Identifie une expérience par son mécanisme et ses paramètres.

    Deux cerveaux peuvent reformuler la même expérience à chaque demi-heure.
    Si les paramètres testés sont identiques, la seconde ligne n'apporte
    aucune information au Lab : on la considère comme un doublon.
    """
    payload = {
        "famille": str(idee.get("famille", "")).strip().lower(),
        "params": idee.get("params", {}),
    }
    brut = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(brut.encode("utf-8")).hexdigest()


def _empreintes_existantes(url: str, cle: str, limit: int = 5000) -> set[str]:
    """Charge les expériences déjà déposées, sans lire ni exposer aucun secret."""
    endpoint = (
        f"{url}/rest/v1/lab_research?select=famille,hypothese"
        f"&statut=eq.IDEATED&order=created_at.desc&limit={int(limit)}"
    )
    req = urllib.request.Request(endpoint, headers={
        "apikey": cle, "Authorization": f"Bearer {cle}",
    })
    try:
        rows = json.loads(urllib.request.urlopen(req, timeout=30).read().decode() or "[]")
    except Exception as exc:  # noqa: BLE001
        print(f"lecture des doublons impossible : {type(exc).__name__}")
        return set()
    result: set[str] = set()
    for row in rows:
        try:
            h = json.loads(row.get("hypothese") or "{}")
            result.add(_empreinte_idee({"famille": row.get("famille"), "params": h.get("params", {})}))
        except (TypeError, ValueError, json.JSONDecodeError):
            continue
    return result


def deposer(idees: list[dict], mode: str) -> int:
    url = os.environ.get("SUPABASE_URL", "").rstrip("/")
    cle = os.environ.get("SUPABASE_SERVICE_KEY", "")
    if not url or not cle:
        print("SUPABASE absent, rien depose")
        return 0
    deja = _empreintes_existantes(url, cle)
    uniques: list[dict] = []
    for idee in idees:
        empreinte = _empreinte_idee(idee)
        if empreinte in deja:
            continue
        deja.add(empreinte)
        uniques.append(idee)
    if len(uniques) < len(idees):
        print(f"  {len(idees) - len(uniques)} doublon(s) ignore(s)")

    lignes = [{
        "sujet": str(i.get("titre", ""))[:300],
        "mode": mode,
        "famille": str(i.get("famille", "inconnu"))[:60],
        "titre": str(i.get("titre", ""))[:300],
        "url": str((i.get("sources") or [{}])[0].get("url", ""))[:500],
        "hypothese": json.dumps({"texte": i.get("hypothese", ""),
                                 "params": i.get("params", {}),
                                 "cerveau": i.get("cerveau", ""),
                                 "feature_requise": i.get("feature_requise", ""),
                                 "sources": i.get("sources", [])},
                                ensure_ascii=False)[:4000],
        "conditions": str(i.get("conditions", ""))[:2000],
        "statut": ("IDEATED" if str(i.get("famille", "")).strip().lower() in FAMILLES_RECHERCHE_EXECUTABLES else "FEATURE_REQUIRED"),
    } for i in uniques]
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


def hypotheses_en_attente() -> int | None:
    """Hypotheses du Lab pas encore testees (IDEATED + TESTING), ou None."""
    url = os.getenv("SUPABASE_URL", "").rstrip("/")
    cle = os.getenv("SUPABASE_SERVICE_KEY", "")
    if not url or not cle:
        return None
    try:
        req = urllib.request.Request(
            f"{url}/rest/v1/lab_research?statut=in.(IDEATED,TESTING)&select=id",
            headers={"apikey": cle, "authorization": f"Bearer {cle}",
                     "prefer": "count=exact", "range": "0-0"})
        with urllib.request.urlopen(req, timeout=15) as r:
            plage = r.headers.get("content-range", "")
        return int(plage.rsplit("/", 1)[-1])
    except Exception:  # noqa: BLE001
        return None


def main() -> int:
    a = argparse.ArgumentParser(description=__doc__)
    a.add_argument("--sujet", default="entrees, sorties et gestion du risque")
    a.add_argument("--combien", type=int, default=3)
    a.add_argument("--veille", action="store_true",
                   help="demander ce qui existe ailleurs, sans deposer")
    a.add_argument("--cerveaux", default="chatgpt,claude")
    a.add_argument("--local-only", action="store_true", help="n'utiliser que des variables calculables depuis les bougies OHLC et les reglages du moteur")
    a.add_argument("--forcer", action="store_true",
                   help="chercher meme si le Lab a encore des hypotheses a tester")
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

    # LA RECHERCHE NE TOURNE QUE QUAND LE LAB A FAIM (operateur, 3 oct. 2026).
    #
    # « Tant qu'il y a des strategies a tester, les recherches sont
    # stoppees ; des qu'il n'y en a plus, elles se relancent. » Chaque
    # passage coute (ChatGPT, Claude) ; deposer des idees dans une file que
    # le Lab ne videra pas avant des jours, c'est payer pour attendre.
    # Ce controle-ci ne coute rien : une lecture de la base.
    if not args.forcer:
        en_attente = hypotheses_en_attente()
        if en_attente is None:
            print("  file du Lab illisible : recherche suspendue par prudence")
            return 0
        if en_attente > 0:
            print(f"  {en_attente} hypothese(s) encore a tester : recherche suspendue "
                  "(elle repartira quand la file sera vide)")
            return 0

    connus = reglages_connus()
    print(f"  {len(connus)} reglages applicables par le labo")
    sujet = args.sujet
    if args.local_only:
        sujet += "\nCONTRAINTE FORTE: produire uniquement des hypotheses executables avec les bougies OHLC et les indicateurs/reglages deja presents dans le moteur. feature_requise doit etre vide. Aucune donnee VIX, funding, order book, macro, news, earnings, credit ou API externe. Prioriser momentum, donchian, reversion, filtres de tendance, sorties et gestion du risque."
    question = QUESTION.format(
        sujet=sujet, combien=args.combien,
        reglages=", ".join(sorted(connus)))

    try:
        # AVANT les cerveaux : recherche web multi-sources. Cela couvre
        # academique, quant, marches, banques centrales, actions, futures,
        # FX, crypto et communautes. Les URLs servent de provenance; seules
        # les hypotheses executables entrent ensuite dans le Lab.
        web = recherche_idee_trading({
            "sujet": args.sujet,
            "mode": "complet",
        })
        sources = web.get("resultats") or []
        contexte = "SOURCES WEB TROUVEES AVANT L'ANALYSE :\n" + json.dumps(
            sources[:30], ensure_ascii=False)[:14000]
        reponses = consulter(question, contexte=contexte,
                             lesquels=lesquels, max_jetons=12000)
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
