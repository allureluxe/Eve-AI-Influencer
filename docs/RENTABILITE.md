# Rentabilité des prix alluxe.fr (13 oct. 2026)

Calcul par vente, sur les prix actuels de `docs/kit/offres.json` et `docs/kit/noel/catalogue.json`.

## Hypothèses

- Micro-entreprise, franchise de TVA (pas de TVA facturée ni récupérée).
- Paiement par carte via Stripe : 1,5 % + 0,25 € par paiement.
- Objets (vente de marchandises) : URSSAF 12,3 % + formation pro 0,2 % + impôt (versement libératoire) 1 % = **13,5 % du chiffre encaissé**, livraison comprise.
- Services (sites, IA, contenus) : on les compte en BNC, le cas le plus cher : URSSAF 25,6 % + formation pro 0,2 % + impôt 2,2 % = **28 %**. S'ils sont déclarés en prestations commerciales (BIC), c'est 23,2 %.
- Sans versement libératoire, l'impôt dépend des revenus du foyer : il peut être plus élevé ou plus bas.
- CFE : pas due l'année de création. Ensuite, quelques centaines d'euros par an selon la commune.
- Coûts des objets : devis Gelato du 11 oct., fabrication + port, TTC.
- Coûts des services (outils IA, hébergement) et heures de travail : **estimations**, à corriger au réel.
- Livres de Bastien et Christine : liens vers Amazon, aucune marge, aucune charge (pure publicité).

## Objets de Noël (Gelato)

| Produit | Prix + livraison payés | Coût Gelato | Stripe | URSSAF + impôt | **Bénéfice** | Prix conseillé (≈ 20 % net) |
|---|---|---|---|---|---|---|
| Affiche 30×40 | 19,90 + 6,90 | 22,31 | 0,65 | 3,62 | **0,22** | 27,90 |
| Affiche encadrée | 39,90 + 6,90 | 40,20 | 0,95 | 6,32 | **−0,67** | 55,90 |
| Toile 30×40 | 44,90 + 9,90 | 49,42 | 1,07 | 7,40 | **−3,09** | 66,90 |
| Mug | 14,90 + 4,90 | 12,14 | 0,55 | 2,67 | **4,44** | 14,90 (inchangé) |
| 10 cartes de vœux | 16,90 + 4,90 | 18,52 | 0,58 | 2,94 | **−0,24** | 23,90 |
| Verre acrylique 20×30 | 44,90 + 9,90 | 48,49 | 1,07 | 7,40 | **−2,16** | 65,90 |
| Calendrier 2027 | 34,90 (port non facturé) | 18,26 | 0,77 | 4,71 | **11,15** | 34,90 (inchangé) |

Les autres objets (textile, plaid, coussin, papier cadeau, déco) n'ont pas encore de coût fournisseur : impossible de calculer leur bénéfice.

## Services (paiement unique)

| Offre | Prix | Coût outils (est.) | **Bénéfice net** | Heures (est.) | Net par heure |
|---|---|---|---|---|---|
| Site vitrine | 29 | 1 | **19,20** | 3 h | 6,40 €/h |
| Boutique Shopify | 25 | 1 | **16,38** | 4 h | 4,09 €/h |
| E-commerce de A à Z | 49 | 2 | **32,30** | 8 h | 4,04 €/h |
| Agent IA secrétaire | 29 | 1 | **19,20** | 3 h | 6,40 €/h |
| Robot d'automatisation | 29 | 1 | **19,20** | 3 h | 6,40 €/h |
| Influenceuse IA | 49 | 15 | **19,30** | 6 h | 3,22 €/h |
| Pack business IA | 99 | 15 | **54,55** | 15 h | 3,64 €/h |
| Boutique de Noël numérique | 15 | 1 | **9,32** | 3 h | 3,11 €/h |
| Campagne de Noël | 19 | 3 | **10,14** | 3 h | 3,38 €/h |
| Compte faceless | 19 | 4 | **9,14** | 3 h | 3,05 €/h |
| Agent de publication auto | 19 | 0,5 | **12,64** | 1,5 h | 8,43 €/h |
| Kit créateur UGC | 9 | 0,5 | **5,59** | 1 h | 5,59 €/h |
| Clip vidéo IA | 15 | 5 | **5,32** | 2 h | 2,66 €/h |
| Marque de vêtements | 39 | 2 | **25,24** | 5 h | 5,05 €/h |
| Création d'application | 99 | 2 | **67,55** | 10 h | 6,75 €/h |

## Abonnements (par mois)

| Offre | Prix/mois | Coût/mois (est.) | **Bénéfice/mois** |
|---|---|---|---|
| Site vitrine | 9 | 1,50 | **4,59** |
| Boutique Shopify | 9 | 0,50 | **5,59** |
| E-commerce | 15 | 1 | **9,32** |
| Agent IA secrétaire | 9 | 3 | **3,09** |
| Robot | 9 | 2 | **4,09** |
| Influenceuse IA (30 vidéos/mois) | 15 | 12 | **−1,68** |
| Pack business IA | 25 | 5 | **12,38** |
| Compte faceless (30 Reels/mois) | 9 | 4 | **2,09** |
| Agent de publication auto | 9 | 1 | **5,09** |
| Marque de vêtements | 9 | 1 | **5,09** |
| Application | 19 | 3 | **10,14** |
| Suivi & coaching | 29 | 0 | **20,20** |

L'offre de Noël (1er mois offert + Kit UGC offert à chaque commande) retire en plus un mois d'abonnement et environ 1 h de travail par commande.
