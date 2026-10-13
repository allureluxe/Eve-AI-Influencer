"""Fabrique les pages « idées cadeaux » d'alluxe.fr (référencement Google, 13 oct. 2026).

    python3 ops/pages_idees.py      # réécrit docs/kit/idee-*.html

Les produits et les livres viennent de noel/catalogue.json et livres.json (noms,
images, liens) : rien n'est recopié à la main. Aucun prix écrit en dur — ils
changent ; la boutique et la page Livres les affichent.
"""
from __future__ import annotations

import html
import json
from pathlib import Path

KIT = Path(__file__).resolve().parents[1] / "docs" / "kit"
CAT = {p["id"]: p for p in json.loads((KIT / "noel/catalogue.json").read_text())["produits"]}
LIV = json.loads((KIT / "livres.json").read_text())
TOMES = {t["n"]: t for t in LIV["serie"]["tomes"]}
CP = {l["asin"]: l for l in LIV["autres"]["livres"]}
e = html.escape


def carte_produit(pid: str, pourquoi: str) -> str:
    p = CAT[pid]
    return (f'<a class="fiche" href="noel/#produits"><img src="noel/{p["image"]}" alt="{e(p["nom"])}" loading="lazy">'
            f'<div class="corps"><h3>{e(p["nom"])}</h3><p>{e(pourquoi)}</p><span class="voir-lien">Voir dans la boutique →</span></div></a>')


def carte_livre(livre: dict, sous: str, pourquoi: str) -> str:
    return (f'<a class="fiche fiche-livre-idee" href="livres.html#{livre["asin"]}"><img src="{livre["image"]}" alt="Couverture : {e(livre["titre"])}" loading="lazy">'
            f'<div class="corps"><span class="sous">{e(sous)}</span><h3>{e(livre["titre"])}</h3><p>{e(pourquoi)}</p>'
            f'<span class="voir-lien">Lire le résumé →</span></div></a>')


def page(fichier, titre, desc, h1, accroche, image, sections, faq, interet, texte_inscription):
    url = f"https://alluxe.fr/{fichier}"
    ld_faq = {"@context": "https://schema.org", "@type": "FAQPage", "mainEntity": [
        {"@type": "Question", "name": q, "acceptedAnswer": {"@type": "Answer", "text": r}} for q, r in faq]}
    ld_art = {"@context": "https://schema.org", "@type": "Article", "headline": h1, "description": desc,
              "image": f"https://alluxe.fr/{image}", "inLanguage": "fr-FR", "datePublished": "2026-10-13",
              "dateModified": "2026-10-13", "author": {"@type": "Organization", "name": "alluxe", "url": "https://alluxe.fr/"},
              "publisher": {"@type": "Organization", "name": "alluxe", "logo": {"@type": "ImageObject", "url": "https://alluxe.fr/logo-alluxe.png"}},
              "mainEntityOfPage": url}
    corps = "\n".join(
        f'<section class="idee-bloc"><div class="conteneur"><h2>{s["titre"]}</h2>'
        + "".join(f"<p>{x}</p>" for x in s.get("textes", []))
        + (f'<div class="etal">{"".join(s["cartes"])}</div>' if s.get("cartes") else "")
        + "</div></section>" for s in sections)
    questions = "".join(f'<details class="apparait"><summary>{e(q)}</summary><p>{e(r)}</p></details>' for q, r in faq)
    return f'''<!doctype html>
<html lang="fr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{e(titre)}</title>
<meta name="description" content="{e(desc)}">
<link rel="canonical" href="{url}">
<meta property="og:url" content="{url}">
<meta property="og:type" content="article">
<meta property="og:site_name" content="alluxe">
<meta property="og:locale" content="fr_FR">
<meta property="og:title" content="{e(h1)}">
<meta property="og:description" content="{e(desc)}">
<meta property="og:image" content="https://alluxe.fr/{image}">
<meta name="twitter:card" content="summary_large_image">
<meta name="theme-color" content="#6e0f12">
<link rel="icon" href="logo-alluxe.png">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Bricolage+Grotesque:opsz,wght@12..96,600;12..96,800&family=Inter:wght@400;500;700&family=JetBrains+Mono:wght@400;600&display=swap" rel="stylesheet">
<link rel="stylesheet" href="style.css?v=20261013d">
<link rel="stylesheet" href="boutique.css?v=20261013d">
<script type="application/ld+json">{json.dumps(ld_art, ensure_ascii=False)}</script>
<script type="application/ld+json">{json.dumps(ld_faq, ensure_ascii=False)}</script>
</head>
<body class="page-idee">
<!-- Page générée par ops/pages_idees.py : modifier le script, pas ce fichier. -->
<header class="vitrine">
  <div class="conteneur entete-livres">
    <div>
      <span class="pastille">🎁 IDÉES CADEAUX DE NOËL</span>
      <h1>{h1}</h1>
      <p class="accroche">{accroche}</p>
      <p class="rebours">🎄 Livré pour Noël : commandez avant le <b>14 décembre</b></p>
    </div>
    <img class="pile" src="{image}" alt="" fetchpriority="high">
  </div>
</header>
{corps}
<section class="idee-bloc"><div class="conteneur"><h2>Questions fréquentes</h2><div class="faq">{questions}</div></div></section>
<section class="idee-bloc"><div class="conteneur"><div data-inscription="{interet}" data-titre="{'Reste au courant des nouveautés' if interet == 'livres' else "On te prévient à l'ouverture des commandes"}" data-texte="{e(texte_inscription)}"></div></div></section>
<section class="idee-bloc"><div class="conteneur"><p class="autres-idees">Autres idées : {AUTRES.replace(f'<a href="{fichier}">', '<a class="ici" href="' + fichier + '">')}</p></div></section>
<script src="commun.js?v=20261013d"></script>
</body>
</html>
'''


IDEES = {
    "idee-cadeau-noel-personnalise.html": "Cadeaux de Noël personnalisés",
    "idee-cadeau-noel-grands-parents.html": "Cadeau de Noël pour les grands-parents",
    "idee-livre-enfant-drole.html": "Livre drôle pour enfant",
    "idee-livre-developpement-personnel.html": "Livre de développement personnel à offrir",
}
AUTRES = " · ".join(f'<a href="{f}">{n}</a>' for f, n in IDEES.items())


def main() -> None:
    t = TOMES
    pages = {}
    pages["idee-cadeau-noel-personnalise.html"] = page(
        "idee-cadeau-noel-personnalise.html",
        "Idées de cadeaux de Noël personnalisés avec photo (famille, couple, enfants) | alluxe",
        "6 idées de cadeaux de Noël personnalisés d'après une simple photo : portrait de famille sur affiche, toile, verre, mug ou cartes de vœux. Aperçu offert avant impression.",
        "Cadeaux de Noël personnalisés : <em>6 idées d'après une simple photo.</em>",
        "Un cadeau personnalisé, c'est celui qu'on garde. Avec une photo prise au téléphone, on crée un portrait de Noël de la famille, du couple, des enfants ou de l'animal, puis on l'imprime sur l'objet de votre choix.",
        "noel/hero.jpg",
        [{"titre": "Pourquoi un cadeau personnalisé ?",
          "textes": ["Un objet acheté en magasin se remplace. Un portrait de la famille réunie à Noël, lui, reste accroché au mur des années. C'est aussi le cadeau idéal quand on ne sait plus quoi offrir : il n'existe en aucun autre exemplaire.",
                     "Le principe est simple : vous envoyez une photo, nous créons le portrait dans le style choisi, vous validez l'aperçu (offert), puis il est imprimé et livré chez vous."]},
         {"titre": "Les 6 idées les plus offertes",
          "cartes": [carte_produit("affiche-cadre", "Prête à accrocher : rien à faire en la recevant. Le cadeau qui fait le plus d'effet sous le sapin."),
                     carte_produit("affiche", "Le grand classique, sur papier mat épais. Parfait pour un premier cadeau personnalisé."),
                     carte_produit("toile", "Effet tableau de galerie : pour un salon ou une entrée."),
                     carte_produit("acrylique", "Couleurs éclatantes et effet verre brillant : le plus moderne."),
                     carte_produit("mug", "Le petit cadeau qui fait rire, pour les collègues, les cousins ou le Père Noël secret."),
                     carte_produit("cartes", "10 cartes de vœux avec votre portrait en couverture, à envoyer à toute la famille.")]},
         {"titre": "Bien choisir la photo",
          "textes": ["Une photo nette, prise à la lumière du jour, où l'on voit bien les visages, suffit. Pas besoin d'une photo de professionnel : on peut même réunir des personnes prises sur des photos différentes.",
                     "Pour être livré à temps pour Noël, commandez avant le 14 décembre : il faut compter la création du portrait, votre validation, puis l'impression et la livraison."]}],
        [("Faut-il une photo de bonne qualité ?", "Une photo nette prise au téléphone suffit, de préférence à la lumière du jour, avec les visages bien visibles."),
         ("Peut-on voir le portrait avant l'impression ?", "Oui : un aperçu est offert et vous pouvez demander des retouches avant l'impression."),
         ("Jusqu'à quand commander pour Noël ?", "Jusqu'au 14 décembre pour une livraison avant Noël en France."),
         ("Peut-on mettre un animal sur le portrait ?", "Oui, chiens, chats et autres compagnons sont les bienvenus, seuls ou avec la famille.")],
        "noel", "Les commandes de portraits ouvrent bientôt : laisse ton e-mail, tu seras prévenu en premier.")

    pages["idee-cadeau-noel-grands-parents.html"] = page(
        "idee-cadeau-noel-grands-parents.html",
        "Cadeau de Noël pour les grands-parents : idées qui font vraiment plaisir | alluxe",
        "Idées de cadeaux de Noël pour les grands-parents : portrait des petits-enfants, cartes de vœux personnalisées, livres qui font du bien, et une série drôle à lire avec les petits.",
        "Cadeau de Noël pour les grands-parents : <em>ce qui leur fait vraiment plaisir.</em>",
        "Les grands-parents ont souvent « déjà tout ». Ce qui les touche, ce sont leurs petits-enfants, des souvenirs à garder et des moments partagés. Voici nos idées.",
        "noel/famille-poster.jpg",
        [{"titre": "Le portrait des petits-enfants",
          "textes": ["Le cadeau qui marche à chaque fois : tous les petits-enfants réunis sur un même portrait de Noël, même s'ils n'étaient pas sur la même photo. Il trouvera sa place dans le salon et fera le tour de toutes les visites."],
          "cartes": [carte_produit("affiche-cadre", "Prête à accrocher, sans rien à bricoler : idéal pour des grands-parents."),
                     carte_produit("toile", "Effet tableau, pour le mur du salon."),
                     carte_produit("mug", "Le café du matin avec les petits-enfants dessus."),
                     carte_produit("cartes", "Pour qu'ils envoient leurs vœux avec le portrait de toute la famille.")]},
         {"titre": "Un livre qui fait du bien",
          "textes": ["Pour une grand-mère ou un grand-père qui aime prendre soin de soi, les recueils de Christine Pierre parlent de confiance, de paix intérieure et de la joie de vivre, avec des textes courts à lire et relire."],
          "cartes": [carte_livre(CP["2957687119"], "Christine Pierre", "Des phrases positives pour retrouver la paix intérieure, à piocher chaque jour."),
                     carte_livre(CP["B0GK2WMGQP"], "Christine Pierre", "Avancer sans crainte : un récit d'évolution et de transformation.")]},
         {"titre": "Une histoire à lire avec les petits",
          "textes": ["Lire ensemble, c'est le plus beau des moments. Les détectives maladroits sont des enquêtes drôles et courtes, parfaites à raconter le soir quand les petits-enfants viennent dormir."],
          "cartes": [carte_livre(t[2], "Les détectives maladroits · Tome 2", "Tous les burgers de la ville disparaissent : une enquête courte et hilarante pour commencer."),
                     carte_livre(t[3], "Les détectives maladroits · Tome 3", "Le chien du maire a disparu, trois jours avant la grande fête de la ville.")]}],
        [("Quoi offrir à des grands-parents qui ont déjà tout ?", "Un cadeau personnel : le portrait de leurs petits-enfants, un livre qui leur ressemble, ou un moment de lecture partagé avec les petits."),
         ("Peut-on réunir des petits-enfants qui ne sont pas sur la même photo ?", "Oui : on peut partir de plusieurs photos pour créer un seul portrait de famille."),
         ("Les livres sont-ils livrés pour Noël ?", "Les livres sont vendus et livrés par Amazon : vérifiez la date de livraison affichée sur Amazon au moment de commander.")],
        "noel", "Portraits, nouveautés et bons plans de Noël : on te prévient par e-mail.")

    pages["idee-livre-enfant-drole.html"] = page(
        "idee-livre-enfant-drole.html",
        "Livre drôle pour enfant à offrir à Noël : la série Les détectives maladroits | alluxe",
        "Un livre drôle à offrir à un enfant pour Noël : Les détectives maladroits, 19 enquêtes loufoques et complètes, à lire seul ou à raconter le soir. Par quel tome commencer ?",
        "Un livre drôle à offrir à un enfant : <em>Les détectives maladroits.</em>",
        "Lucie et Bastien, deux détectives aussi attachants que catastrophiques, enchaînent les enquêtes loufoques : burgers volés, gnomes kidnappés, momie au musée. 19 tomes, chacun se lit seul.",
        "livres/vitrine.jpg",
        [{"titre": "Pourquoi les enfants adorent",
          "textes": ["Chaque tome est une enquête complète, avec des quiproquos, des courses-poursuites et des catastrophes en série. On rit beaucoup, on tourne les pages pour savoir qui est le coupable, et l'amitié entre Lucie et Bastien donne aussi de jolis moments d'émotion.",
                     "Pas besoin de lire dans l'ordre : on peut commencer par n'importe quel tome. C'est idéal pour offrir un livre à un enfant qui n'aime pas encore lire : des chapitres courts, de l'humour, et l'envie de lire le suivant."]},
         {"titre": "Par quel tome commencer ?",
          "textes": ["Pour un premier tome, choisissez une enquête courte et très drôle :"],
          "cartes": [carte_livre(t[2], f"Tome 2 · {t[2].get('pages') or ''} pages", "Le plus court : tous les burgers de la ville disparaissent. Parfait pour se lancer."),
                     carte_livre(t[3], f"Tome 3 · {t[3].get('pages') or ''} pages", "La première vraie mission : retrouver Spooky, le chien du maire."),
                     carte_livre(t[5], f"Tome 5 · {t[5].get('pages') or ''} pages", "Une chaussette égyptienne volée, des momies qui bougent… et Bastien terrifié."),
                     carte_livre(t[11], f"Tome 11 · {t[11].get('pages') or ''} pages", "Des gnomes de jardin disparaissent dans tout le quartier. Absurde et touchant.")]},
         {"titre": "Pour les fans : offrir plusieurs tomes",
          "textes": ["Un enfant qui a aimé un tome voudra la suite. Offrir 2 ou 3 tomes sous le sapin, c'est l'assurance de longues soirées de lecture. Tous les tomes sont disponibles en livre broché et en Kindle, vendus et livrés par Amazon.",
                     '<a class="bouton" href="livres.html#tomes">Voir les 19 tomes <span class="fleche">→</span></a>']}],
        [("Faut-il lire les tomes dans l'ordre ?", "Non, chaque tome est une enquête complète : on peut commencer par n'importe lequel."),
         ("Les livres existent-ils en version papier ?", "Oui, en livre broché et en Kindle, vendus et livrés par Amazon."),
         ("Qui a écrit la série ?", "Les détectives maladroits sont écrits par Basutiian Liam.")],
        "livres", "Nouveaux tomes et idées de lecture : on te prévient par e-mail.")

    pages["idee-livre-developpement-personnel.html"] = page(
        "idee-livre-developpement-personnel.html",
        "Livre de développement personnel à offrir : 3 livres qui font du bien | alluxe",
        "Un livre de développement personnel à offrir à Noël : les recueils de Christine Pierre pour apaiser ses pensées, retrouver confiance et joie intérieure.",
        "Un livre de développement personnel à offrir : <em>3 livres qui font du bien.</em>",
        "Offrir un livre qui fait du bien, c'est offrir un peu de calme et de confiance. Christine Pierre partage dans ses recueils son chemin vers la paix intérieure, avec des textes simples à lire et à mettre en pratique.",
        "livres/cp-phrases.jpg",
        [{"titre": "Le bon livre selon la personne",
          "cartes": [carte_livre(CP["2957687119"], "Pour commencer", "Pour quelqu'un que les pensées, les peurs ou les doutes empêchent d'avancer : des phrases positives à lire chaque jour."),
                     carte_livre(CP["B0GK2QFQFX"], "Pour aller plus loin", "Un vécu partagé : se libérer des mémoires du passé familial et se reconnecter à soi."),
                     carte_livre(CP["B0GK2WMGQP"], "Pour reprendre confiance", "L'ouverture, l'évolution, la transformation : avancer sans crainte, pas à pas.")]},
         {"titre": "Pourquoi offrir ce type de livre à Noël",
          "textes": ["La fin d'année est un moment où l'on fait le point. Un livre de développement personnel accompagne ce moment : on le lit à son rythme, on le garde sur la table de nuit et on y revient.",
                     "Les recueils de Christine Pierre se lisent par petits textes, sans jargon : un bon choix pour quelqu'un qui découvre le développement personnel. Ils sont vendus et livrés par Amazon.",
                     '<a class="bouton" href="livres.html#pour-les-grands">Voir les livres de Christine Pierre <span class="fleche">→</span></a>']}],
        [("À qui offrir ces livres ?", "À toute personne qui traverse une période de doutes, de stress ou de changement, ou qui a envie de prendre soin d'elle."),
         ("Faut-il connaître le développement personnel ?", "Non : les textes sont courts et simples, ils se lisent sans connaissances préalables."),
         ("Comment les commander ?", "Les livres sont vendus et livrés par Amazon : sur la page Livres, chaque fiche mène directement à la bonne page Amazon.")],
        "livres", "Nouveaux livres et idées de lecture : on te prévient par e-mail.")

    for f, s in pages.items():
        (KIT / f).write_text(s)
        print("écrit :", f)


if __name__ == "__main__":
    main()
