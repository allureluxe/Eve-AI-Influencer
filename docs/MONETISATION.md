# Monétisation

Ordre volontaire : on commence par ce qui ne dépend d'aucun seuil d'abonnés.

## 1. Produit numérique — disponible immédiatement

```bash
python -m eve.cli product --title "Reset 4 semaines"
```

Génère un programme complet de 4 semaines (Markdown + HTML imprimable en PDF
depuis le navigateur) et un media kit. Aucun seuil, aucune plateforme
intermédiaire.

**Mise en vente gratuite** : Gumroad, Payhip ou un lien de paiement Stripe —
tous à 0 € fixe, commission uniquement sur les ventes. Renseigne
`STRIPE_PAYMENT_LINK` ou `SHOP_URL` dans `.env`, l'agent insère le lien dans
les légendes des piliers pertinents.

Prix de départ conseillé : 9 à 19 $. En dessous de 9 $, le produit est perçu
comme sans valeur ; au-dessus de 19 $ sans preuve sociale, il ne se vend pas.

## 2. Affiliation — dès les premiers abonnés

Renseigne `AMAZON_ASSOCIATE_TAG` (ou tout autre programme : Gymshark, Myprotein,
Alo Yoga). L'agent :

- choisit une offre **cohérente avec le pilier** du post — jamais d'offre hors
  sujet, c'est ce qui détruit la confiance ;
- ajoute les paramètres UTM pour distinguer les sources ;
- ajoute automatiquement la mention `#ad` / « lien affilié », **obligation
  FTC**.

Rendement réaliste : 1 à 4 $ de commission par vente, avec 0,2 à 0,6 % des vues
qui cliquent et 2 à 5 % des clics qui achètent.

## 3. Programmes des plateformes

| Programme | Condition d'entrée | Ordre de grandeur |
|---|---|---|
| TikTok Creator Rewards | 10 000 abonnés, 100 000 vues sur 30 j, vidéos > 1 min, marché éligible | 0,40 à 1,00 $ / 1000 vues |
| Instagram (bonus, variables) | Sur invitation, selon les pays | 0 à 0,50 $ / 1000 vues |
| TikTok LIVE | 1 000 abonnés | Très variable |

Ces revenus sont les moins fiables et les moins contrôlables : ils viennent en
complément, jamais en base.

## 4. Partenariats de marque — le vrai revenu

C'est là que se joue la rentabilité d'un compte fitness. Tarif usuel : **1 à
2 % du nombre d'abonnés, par publication** (10 000 abonnés ≈ 100 à 200 $).

Le media kit généré (`output/products/media-kit.md`) annonce explicitement la
nature IA du compte. Ce n'est pas un handicap commercial : c'est ce que les
marques demandent avant de signer, et un compte virtuel non déclaré est
disqualifié dès la découverte.

Refus à assumer dans le kit, parce qu'ils protègent la valeur du compte :
compléments non certifiés, allégations de perte de poids chiffrées,
partenariat sans mention `#ad`.

## 5. Suivre et projeter

```bash
python -m eve.cli revenue --add affiliate 24.50 --note "commissions août"
python -m eve.cli revenue --followers 12000 --views 400000
```

La projection enchaîne trois taux réels (clics → achats → commission) plutôt
qu'un taux unique appliqué aux vues. Les fourchettes sont volontairement
basses : mieux vaut être surpris en bien.

Exemple à 12 000 abonnés et 400 000 vues mensuelles :

| Source | Bas | Haut |
|---|---|---|
| Plateformes | 160 $ | 600 $ |
| Affiliation | 24 $ | 480 $ |
| Produits | 152 $ | 912 $ |
| Sponsoring | 120 $ | 480 $ |

## Ce qui décide vraiment du résultat

Aucun agent ne compense un mauvais positionnement. Dans l'ordre d'impact :

1. **Régularité** — 2 posts/jour pendant 90 jours battent 10 posts parfaits.
2. **Les 3 premières secondes** — le hook fait 80 % de la portée.
3. **Un seul sujet** — « séances courtes pour débutantes » se retient ; « fitness
   lifestyle » ne se retient pas.
4. **Les commentaires** — répondre alimente l'algorithme et crée l'audience qui
   achètera.

Le point 4 reste manuel : l'agent ne répond pas aux commentaires à ta place, et
c'est délibéré — une communauté se construit sur des réponses réelles.
