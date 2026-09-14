"""Generation de la page ALLURE, sans passer par une session Claude.

    from rapports import page_allure
    chemin = page_allure(depuis=..., vers=...)

POURQUOI CE MODULE EXISTE. Les rapports ALLURE etaient jusqu'ici
fabriques a la main dans une conversation. L'operateur veut pouvoir en
demander un depuis Telegram, a tout moment, sans personne devant le
clavier — et il veut LA MEME page, avec son logo, pas un pave de texte.

Le gabarit est donc range dans le depot :

    rapports/allure_tete.html    titre, polices, feuille de style
    rapports/allure_logo.html    le logo Allure, en base64

CE QUE CE MODULE NE FAIT PAS. Il n'invente aucun commentaire. Une page
ecrite dans une conversation porte une lecture — « ce que ca dit et ce que
ca ne dit pas » — qui vient d'une analyse. Ici on s'en tient aux CHIFFRES,
et on le dit en clair dans la page plutot que de faire semblant.

Aucun ordre n'est envoye : ce module lit.

LE GRAPHIQUE ET LE TABLEAU DES TRADES SONT RENDUS COTE SERVEUR (14 sept.).
Ils l'etaient auparavant en JavaScript, execute au chargement de la page
(`allure_script.js`, retire). Le fichier envoye par Telegram est ouvert
dans la visionneuse de documents interne de l'app, qui n'execute PAS le
JavaScript — l'operateur a vu une page entiere sans graphique NI tableau
de trades, alors que « Jour par jour » (deja rendu en HTML pur par ce
module) s'affichait normalement. Le second bug, cache derriere le
premier : quand `POINTS` etait vide, `POINTS[0][1]` levait une exception
JavaScript qui arretait TOUT le script — c'est ce qui emportait aussi le
tableau des trades avec le graphique, deux blocs distincts mais un seul
`<script>`. Rendre les deux en HTML/SVG statique, comme "Jour par jour"
deja, regle les deux a la fois et ne depend plus d'aucun moteur JS.
"""
from __future__ import annotations

import datetime as dt
import json
import math
import os
import re

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GABARIT = os.path.dirname(os.path.abspath(__file__))

JOURS = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]
MOIS = ["janvier", "fevrier", "mars", "avril", "mai", "juin", "juillet",
        "aout", "septembre", "octobre", "novembre", "decembre"]
MOIS_ABREGE = ["janv.", "fevr.", "mars", "avr.", "mai", "juin", "juil.",
               "aout", "sept.", "oct.", "nov.", "dec."]
PARIS = dt.timezone(dt.timedelta(hours=2))

# Couleurs de la charte (rapports/allure_tete.html, section :root). Ecrites
# en dur ici : le graphique est maintenant du SVG statique, sans CSS pour
# les nourrir a l'affichage.
C_JAUNE = "#EFE73C"
C_OLIVE = "#5C570C"
C_GAIN = "#2C6B3F"
C_PERTE = "#A8382A"
C_INK = "#15150F"
C_INK_SOFT = "#55554A"
C_INK_FAINT = "#8E8E80"
C_LIGNE_DOUCE = "#E9E9DE"
C_SURFACE = "#FFFFFF"

#: Retouches pour le telephone, ajoutees APRES la feuille du gabarit pour
#: la surcharger. Le gabarit vise un ecran d'ordinateur : 15 px de base et
#: 22 px de marge laterale, lisibles a 60 cm, petits a bout de bras.
MOBILE = """
<style>
@media (max-width: 700px) {
  body{ font-size:17px; line-height:1.6 }
  .wrap{ padding:20px 15px 48px }
  h1{ font-size:clamp(26px,7vw,34px) }
  h2{ font-size:20px }
  .gros{ font-size:clamp(42px,13vw,56px) }
  .sous, .periode, .contexte p{ font-size:16px }
  .eyebrow{ font-size:12.5px }
  /* Deux colonnes de statistiques au lieu de quatre en file indienne. */
  .stats{ grid-template-columns:repeat(2,1fr); gap:9px }
  .stat .v{ font-size:23px }
  .stat .k{ font-size:12.5px }
  .stat .d{ font-size:12px }
  /* Les tableaux gardent leur largeur mini et defilent : les tasser
     rendrait les colonnes de chiffres illisibles. La marge negative du
     gabarit vaut 28 px et depasserait du telephone. */
  .tablewrap{ margin:0 -15px; padding:0 15px }
  table{ font-size:15px; min-width:460px }
  th, td{ padding:9px 8px }
  .lecture li{ font-size:16px }
  footer{ font-size:13px }
}
@media (max-width: 380px) {
  .stats{ grid-template-columns:1fr }
}
</style>"""


def _fr(quand: dt.datetime) -> str:
    q = quand.astimezone(PARIS)
    return f"{JOURS[q.weekday()]} {q.day} {MOIS[q.month - 1]}"


def _lire(nom: str) -> str:
    with open(os.path.join(GABARIT, nom), encoding="utf-8") as f:
        return f.read()


def _trades(depuis: float, vers: float) -> list[dict]:
    """Tous les trades fermes dans la fenetre, les deux journaux confondus."""
    sortie = []
    for nom in ("data/trades-avant-resserrage.jsonl", "data/trades.jsonl"):
        chemin = os.path.join(RACINE, nom)
        if not os.path.exists(chemin):
            continue
        with open(chemin, encoding="utf-8") as f:
            for ligne in f:
                ligne = ligne.strip()
                if not ligne:
                    continue
                try:
                    t = json.loads(ligne)
                except ValueError:
                    continue
                if depuis <= t.get("closed_at", 0) <= vers:
                    sortie.append(t)
    return sorted(sortie, key=lambda t: t["closed_at"])


def _courbe(depuis: float, vers: float) -> list[list]:
    """Capital reel releve toutes les 5 min par le chien de garde.

    CORRIGE DES MOUVEMENTS D'ARGENT. Sans cette correction un depot ferait
    un bond vertical que l'operateur lirait comme un gain, et un retrait
    comme une perte — l'erreur du tout premier rapport ALLURE.
    """
    mouvements = _mouvements()
    points, vus = [], set()
    chemin = os.path.join(RACINE, "data/chien_de_garde.log")
    if not os.path.exists(chemin):
        return []
    with open(chemin, encoding="utf-8") as f:
        for ligne in f:
            m = re.search(r"^(\S+ \S+)\s+OK : equite ([\d.]+)", ligne)
            if not m:
                continue
            try:
                t = dt.datetime.strptime(m.group(1), "%Y-%m-%d %H:%M:%S").timestamp()
            except ValueError:
                continue
            if not (depuis <= t <= vers):
                continue
            cle = int(t // 1800)          # un point toutes les 30 min
            if cle in vus:
                continue
            vus.add(cle)
            ajust = sum(v for q, v in mouvements if q <= t)
            points.append([int(t), round(float(m.group(2)) - ajust, 2)])
    return points


def _mouvements() -> list[tuple[float, float]]:
    """Depots et retraits en devise du compte, lus chez Bitvavo.

    Liste VIDE en cas d'echec : mieux vaut une courbe non corrigee qu'un
    rapport qui ne part pas. Le defaut se verra, un rapport absent non.
    """
    try:
        from dataclasses import replace

        from gold_bot.brokers.bitvavo import BitvavoBroker, BitvavoConfig
        cfg = BitvavoConfig.from_env()
        courtier = BitvavoBroker(replace(cfg, dry_run=True))
        if not courtier.connect():
            return []
        sortie = []
        for chemin, signe in (("/depositHistory", +1.0), ("/withdrawalHistory", -1.0)):
            for ligne in courtier._appel("GET", chemin) or []:
                if str(ligne.get("status", "")).lower() != "completed":
                    continue
                if str(ligne.get("symbol", "")).upper() != cfg.quote_asset.upper():
                    continue
                try:
                    sortie.append((float(ligne["timestamp"]) / 1000.0,
                                   signe * float(ligne["amount"])))
                except (KeyError, TypeError, ValueError):
                    continue
        return sortie
    except Exception:                                         # noqa: BLE001
        return []


def _compte() -> tuple[float, float, int]:
    try:
        from dataclasses import replace

        from gold_bot.brokers.bitvavo import BitvavoBroker, BitvavoConfig
        cfg = BitvavoConfig.from_env()
        courtier = BitvavoBroker(replace(cfg, dry_run=True))
        if not courtier.connect():
            return 0.0, 0.0, 0
        compte = courtier.account()
        prix = courtier._prix_du_marche()
        n = sum(1 for a, q in courtier._soldes.items()
                if a != cfg.quote_asset and q * prix.get(f"{a}-{cfg.quote_asset}", 0) > 1)
        return compte.equity, compte.margin_free, n
    except Exception:                                         # noqa: BLE001
        return 0.0, 0.0, 0


def _heure_paris(t: float) -> int:
    return int(dt.datetime.fromtimestamp(t, PARIS).strftime("%H"))


def _jour_court_paris(t: float) -> str:
    q = dt.datetime.fromtimestamp(t, PARIS)
    return f"{q.day} {MOIS_ABREGE[q.month - 1]}"


def _virgule(v: float) -> str:
    return f"{v:.2f}".replace(".", ",")


def _graphique_svg(points: list[list], trades: list[dict]) -> str:
    """Le graphique de la courbe de capital, en SVG statique.

    Portage direct de l'ancien `allure_script.js` (retire) : memes
    dimensions, memes pas de grille, meme decoupe des trous > 2 h. La
    seule difference est qu'il n'a plus besoin d'un moteur JavaScript
    pour exister — voir la note en tete de module.
    """
    if len(points) < 2:
        return ('<p class="h2note">Pas encore assez de points relevés sur '
                'cette période pour tracer une courbe.</p>')

    W, H, PL, PR, PT, PB = 900, 320, 58, 14, 18, 30
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    x0, x1 = min(xs), max(xs)
    lo, hi = min(ys), max(ys)
    pad = (hi - lo) * .06 or 0.5
    y_lo, y_hi = lo - pad, hi + pad
    portee_x = (x1 - x0) or 1

    def X(t: float) -> float:
        return PL + (t - x0) / portee_x * (W - PL - PR)

    def Y(v: float) -> float:
        return PT + (y_hi - v) / (y_hi - y_lo) * (H - PT - PB)

    elements = [
        f'<defs><linearGradient id="deg" x1="0" y1="0" x2="0" y2="1">'
        f'<stop offset="0%" stop-color="{C_JAUNE}" stop-opacity=".95"/>'
        f'<stop offset="100%" stop-color="{C_JAUNE}" stop-opacity=".15"/>'
        f'</linearGradient></defs>'
    ]

    # Grille horizontale, graduee au demi-euro.
    pas = 0.5
    v = math.ceil(y_lo / pas) * pas
    while v <= y_hi:
        y = Y(v)
        rond = abs(v - round(v)) < 1e-9
        tirets = '' if rond else 'stroke-dasharray="2 4"'
        elements.append(
            f'<line x1="{PL}" y1="{y:.1f}" x2="{W-PR}" y2="{y:.1f}" '
            f'stroke="{C_LIGNE_DOUCE}" stroke-width="{1.4 if rond else 1}" {tirets}/>')
        libelle = f"{v:.0f}" if rond else _virgule(v)
        elements.append(
            f'<text x="{PL-10}" y="{y+4:.1f}" fill="{C_INK_FAINT}" font-size="11.5" '
            f'text-anchor="end" font-family="IBM Plex Mono, monospace">{libelle} €</text>')
        v += pas

    # Reperes de temps toutes les 6 h.
    H6 = 6 * 3600
    t = math.ceil((x0 + 5400) / H6) * H6
    while t <= x1 - 3600:
        x = X(t)
        h = _heure_paris(t)
        elements.append(
            f'<line x1="{x:.1f}" y1="{PT}" x2="{x:.1f}" y2="{H-PB}" '
            f'stroke="{C_LIGNE_DOUCE}" stroke-width="1" stroke-dasharray="2 5"/>')
        libelle = _jour_court_paris(t) if h == 0 else f"{h} h"
        elements.append(
            f'<text x="{x:.1f}" y="{H-9}" fill="{C_INK_FAINT}" font-size="11" '
            f'text-anchor="middle" font-family="Archivo, sans-serif">{libelle}</text>')
        t += H6

    # Les deux bouts, toujours nommes.
    for t, x, ancrage in ((x0, PL, "start"), (x1, W - PR, "end")):
        libelle = f"{_jour_court_paris(t)} {_heure_paris(t):02d} h"
        elements.append(
            f'<text x="{x}" y="{H-9}" fill="{C_INK_SOFT}" font-size="11" '
            f'text-anchor="{ancrage}" font-weight="500" '
            f'font-family="Archivo, sans-serif">{libelle}</text>')

    # Ligne de depart : tout ce qui est au-dessus est du gain.
    y_dep = Y(points[0][1])
    elements.append(
        f'<line x1="{PL}" y1="{y_dep:.1f}" x2="{W-PR}" y2="{y_dep:.1f}" '
        f'stroke="{C_INK_FAINT}" stroke-width="1.5" stroke-dasharray="6 4"/>')
    elements.append(
        f'<text x="{W-PR-4}" y="{y_dep-7:.1f}" fill="{C_INK_SOFT}" font-size="11.5" '
        f'text-anchor="end" font-family="Archivo, sans-serif">'
        f'départ {_virgule(points[0][1])} €</text>')

    # On coupe la courbe la ou le robot etait arrete (trou > 2 h).
    segments: list[list[list]] = [[]]
    for i, p in enumerate(points):
        if i and p[0] - points[i - 1][0] > 7200:
            segments.append([])
        segments[-1].append(p)

    for seg in segments:
        if len(seg) < 2:
            continue
        d = " ".join(
            f"{'L' if i else 'M'}{X(p[0]):.1f} {Y(p[1]):.1f}"
            for i, p in enumerate(seg))
        aire = (f"{d} L{X(seg[-1][0]):.1f} {H-PB} "
                f"L{X(seg[0][0]):.1f} {H-PB} Z")
        elements.append(f'<path d="{aire}" fill="url(#deg)"/>')
        elements.append(
            f'<path d="{d}" fill="none" stroke="{C_OLIVE}" stroke-width="3" '
            f'stroke-linejoin="round" stroke-linecap="round"/>')

    # Chaque trade ferme, pose sur la courbe.
    def valeur_a(t: float) -> float:
        b = points[0]
        for p in points:
            if p[0] <= t:
                b = p
            else:
                break
        return b[1]

    for tr in trades:
        c = int(tr["closed_at"])
        if c < x0 or c > x1:
            continue
        couleur = C_GAIN if tr["profit"] >= 0 else C_PERTE
        elements.append(
            f'<circle cx="{X(c):.1f}" cy="{Y(valeur_a(c)):.1f}" r="4.5" '
            f'fill="{couleur}" stroke="{C_SURFACE}" stroke-width="2"/>')

    # Point final, appuye.
    dernier = points[-1]
    elements.append(
        f'<circle cx="{X(dernier[0]):.1f}" cy="{Y(dernier[1]):.1f}" r="6" '
        f'fill="{C_JAUNE}" stroke="{C_OLIVE}" stroke-width="3"/>')
    elements.append(
        f'<text x="{X(dernier[0])-10:.1f}" y="{Y(dernier[1])-12:.1f}" fill="{C_OLIVE}" '
        f'font-size="13" text-anchor="end" font-weight="600" '
        f'font-family="IBM Plex Mono, monospace">{_virgule(dernier[1])} €</text>')

    return (f'<svg class="chart" viewBox="0 0 {W} {H}" role="img" '
            f'aria-label="Courbe du travail du robot">{"".join(elements)}</svg>')


def _lignes_trades(trades: list[dict]) -> str:
    """Le tableau « Les trades », en HTML statique -- voir la note de module."""
    if not trades:
        return '<tr><td colspan="5">aucun trade</td></tr>'

    max_r = max((abs(t.get("r_multiple") or 0) for t in trades), default=0) or 1.0
    lignes = []
    for t in trades:
        d = dt.datetime.fromtimestamp(t["closed_at"], PARIS)
        date_fr = f"{d.day:02d}/{d.month:02d} à {d.hour:02d}h{d.minute:02d}"
        symbole = t["symbol"].replace("USD", "")
        r = t.get("r_multiple") or 0
        profit = t["profit"]
        cls = "pos" if profit > 0 else "neg"
        largeur = abs(r) / max_r * 50
        if r >= 0:
            style = f"left:50%;width:{largeur:.2f}%;background:var(--gain)"
        else:
            style = f"right:50%;width:{largeur:.2f}%;background:var(--loss)"
        lignes.append(
            f'<tr><td class="num" style="color:var(--ink-soft)">{date_fr}</td>'
            f'<td class="sym">{symbole}</td>'
            f'<td><span class="bar"><i class="mid"></i><i style="{style}"></i></span></td>'
            f'<td class="r num {cls}">{r:+.2f}</td>'
            f'<td class="r num {cls}">{profit:+.2f} €</td></tr>')
    return "".join(lignes)


def page_allure(depuis: float, vers: float | None = None,
                titre_periode: str = "") -> str:
    """Fabrique la page et rend son chemin sur le disque.

    `depuis` et `vers` sont des horodatages. `titre_periode` remplace la
    ligne de periode si on veut la nommer autrement (« depuis ta derniere
    demande », par exemple).
    """
    vers = vers if vers is not None else dt.datetime.now().timestamp()
    trades = _trades(depuis, vers)
    points = _courbe(depuis, vers)
    capital, cash, positions = _compte()

    gagnants = [t for t in trades if t["profit"] > 0]
    perdants = [t for t in trades if t["profit"] <= 0]
    net = sum(t["profit"] for t in trades)
    encaisse = sum(t["profit"] for t in gagnants)
    rendu = sum(t["profit"] for t in perdants)
    frais = sum(abs(t.get("volume", 0) * t.get("entry_price", 0)) * 0.005
                for t in trades)
    taux = 100 * len(gagnants) / len(trades) if trades else 0.0
    meilleur = max(trades, key=lambda t: t["profit"]) if trades else None

    periode = titre_periode or (
        f"du {_fr(dt.datetime.fromtimestamp(depuis))} au "
        f"{_fr(dt.datetime.fromtimestamp(vers))}")

    # --- jour par jour ---
    par_jour: dict = {}
    for t in trades:
        j = dt.datetime.fromtimestamp(t["closed_at"]).date()
        par_jour.setdefault(j, []).append(t)
    lignes_jours = []
    for j in sorted(par_jour):
        X = par_jour[j]
        g = sum(1 for t in X if t["profit"] > 0)
        s = sum(t["profit"] for t in X)
        cls = "pos" if s >= 0 else "neg"
        lignes_jours.append(
            f'<tr><td class="sym">{JOURS[j.weekday()]} {j.day}</td>'
            f'<td class="r num">{len(X)}</td><td class="r num">{g}</td>'
            f'<td class="r num {cls}">{s:+.2f} €</td></tr>')

    signe = "neg" if net < 0 else "pos"
    corps = f'''
<div class="wrap">
<header>
  <div class="ligne"><h1>Turtle en réel</h1>{_lire("allure_logo.html")}</div>
  <div class="meta">
    <span class="periode num">{periode} · {len(trades)} trades</span>
    <span class="chip">robot actif</span>
  </div>
</header>

<section class="tete">
  <div>
    <div class="eyebrow">Ce que le robot a fait</div>
    <div class="gros num {signe}">{net:+.2f} €</div>
    <div class="sous num">{len(trades)} trades · {len(gagnants)} gagnants</div>
  </div>
  <div class="contexte">
    <p>Le robot a <strong>encaissé {encaisse:+.2f} €</strong> sur ses
    {len(gagnants)} bons trades et <strong>rendu {rendu:.2f} €</strong> sur
    les {len(perdants)} autres.</p>
    <p>Il tient <strong>{positions} position(s)</strong> en ce moment, pour
    <strong>{capital - cash:.2f} €</strong> investis. Il lui reste
    <strong>{cash:.2f} €</strong>.</p>
  </div>
</section>

<section class="stats">
  <div class="stat" style="--c:var(--gain)">
    <div class="k">Encaissé</div>
    <div class="v num" style="color:var(--gain)">{encaisse:+.2f} €</div>
    <div class="d">sur {len(gagnants)} trades</div>
  </div>
  <div class="stat" style="--c:var(--loss)">
    <div class="k">Rendu</div>
    <div class="v num" style="color:var(--loss)">{rendu:.2f} €</div>
    <div class="d">sur {len(perdants)} trades</div>
  </div>
  <div class="stat" style="--c:var(--jaune)">
    <div class="k">Réussite</div>
    <div class="v num" style="color:var(--ink)">{taux:.0f} %</div>
    <div class="d">frais payés {frais:.2f} €</div>
  </div>
  <div class="stat" style="--c:var(--jaune)">
    <div class="k">Meilleur trade</div>
    <div class="v num" style="color:var(--gain)">{(meilleur["profit"] if meilleur else 0):+.2f} €</div>
    <div class="d">{(meilleur["symbol"].replace("USD", "") if meilleur else "—")}</div>
  </div>
</section>

<section class="carte">
  <h2>La courbe du robot</h2>
  <p class="h2note">Ce qui monte, il l'a gagné ; ce qui descend, il l'a perdu.
  Les virements sont retirés point par point.</p>
  {_graphique_svg(points, trades)}
  <div class="legende">
    <span><i class="sw"></i> ce que le robot a fait du capital</span>
    <span><i class="dot"></i> trade fermé — vert gagnant, rouge perdant</span>
  </div>
</section>

<section class="carte">
  <h2>Jour par jour</h2>
  <div class="tablewrap"><table>
    <thead><tr><th>Jour</th><th class="r">Trades</th>
    <th class="r">Gagnants</th><th class="r">Résultat</th></tr></thead>
    <tbody>{"".join(lignes_jours) or '<tr><td colspan="4">aucun trade</td></tr>'}</tbody>
  </table></div>
</section>

<section class="carte">
  <h2>Les trades</h2>
  <p class="h2note">Tous sortis par un stop : la stratégie n'a aucun plafond de profit.</p>
  <div class="tablewrap"><table>
    <thead><tr><th>Date</th><th>Crypto</th><th>Amplitude</th>
    <th class="r">R</th><th class="r">Résultat</th></tr></thead>
    <tbody>{_lignes_trades(trades)}</tbody>
  </table></div>
</section>

<section class="carte">
  <h2>À lire avec précaution</h2>
  <ul class="lecture">
    <li><strong>Cette page est fabriquée par le robot, pas par une analyse.</strong>
    Elle donne les chiffres exacts ; elle ne dit pas ce qu'ils signifient.
    Pour ça, il faut demander.</li>
    <li><strong>Une poignée de trades porte tout le résultat.</strong> C'est le
    régime normal de cette stratégie : elle perd souvent un peu et gagne
    rarement beaucoup. Un total négatif sur quelques jours ne dit rien.</li>
    <li><strong>Rien ne tranche avant 40 trades</strong> avec la configuration
    en place. En dessous, l'incertitude dépasse ce qu'on mesure.</li>
  </ul>
</section>

<footer>Relevés Bitvavo · page générée le {_fr(dt.datetime.now())} à
{dt.datetime.now(PARIS):%Hh%M} · Donchian 20 j en D1</footer>
</div>
'''

    # UN FICHIER AUTONOME A BESOIN D'UN VRAI EN-TETE HTML.
    #
    # Le gabarit n'en porte pas : quand la page est publiee en artifact,
    # l'hote fournit `<!doctype>`, la balise `viewport` et un reset. Un
    # fichier envoye sur Telegram, lui, n'a personne pour le faire.
    #
    # Sans `viewport`, un telephone rend la page comme un ecran de
    # 980 pixels puis la reduit : tout devient minuscule. C'est ce que
    # l'operateur a vu le 12 septembre 2026. La feuille de style etait
    # deja adaptee au mobile — elle n'etait simplement jamais appliquee.
    entete = (
        "<!doctype html>\n<html lang=\"fr\">\n<head>\n"
        "<meta charset=\"utf-8\">\n"
        "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">\n"
        "<meta name=\"color-scheme\" content=\"light dark\">\n"
        + _lire("allure_tete.html")
        + MOBILE + "\n</head>\n<body>\n")
    html = entete + corps + "\n</body>\n</html>\n"
    chemin = os.path.join(RACINE, "data", "rapport_allure.html")
    os.makedirs(os.path.dirname(chemin), exist_ok=True)
    with open(chemin, "w", encoding="utf-8") as f:
        f.write(html)
    return chemin
