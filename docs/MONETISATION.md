# Monétisation

Rien n'est vendu aujourd'hui. C'est un choix, et il est bon : un compte qui
vend avant d'avoir une audience ne vend rien et brûle sa crédibilité.

La séquence, dans l'ordre.

## Phase 1 — l'audience (maintenant, 6 à 12 mois)

Deux publications par jour, piliers **mode** et **art de vivre** en tête. Le
pilier `work` sert la différenciation : très peu de comptes lifestyle parlent
sérieusement de systèmes automatisés, et c'est ce qui rend Eve mémorable.

Ce qui compte, dans l'ordre d'impact :

1. **La régularité** — 2 posts/jour pendant 90 jours battent 10 posts parfaits.
2. **Les 3 premières secondes** — le hook fait 80 % de la portée.
3. **Un seul sujet reconnaissable** — « style durable et méthode » se retient.
4. **Les commentaires** — l'agent ne répond pas à ta place, volontairement.
   C'est le levier le plus rentable et il est manuel.

## Phase 2 — le guide de style gratuit

```bash
python3 -m eve.cli product
```

Génère « La garde-robe de 30 pièces » (Markdown + HTML imprimable). Il est
**gratuit** : son travail n'est pas de rapporter de l'argent, c'est de
construire la liste et l'habitude d'achat avant l'ouverture de la boutique.

Distribue-le contre une adresse e-mail (Beehiiv, Substack ou MailerLite —
gratuits jusqu'à plusieurs milliers d'abonnés). Cette liste vaudra plus que le
nombre d'abonnés Instagram le jour du lancement du site.

## Phase 3 — les partenariats de marque

Tarif usuel : **1 à 2 % du nombre d'abonnés, par publication** (10 000 abonnés
≈ 100 à 200 $).

Le media kit généré (`output/products/media-kit.md`) annonce la nature IA du
compte dès la première ligne. C'est ce que les marques vérifient avant de
signer, et un compte virtuel non déclaré est disqualifié à la découverte.

Refus inscrits dans le kit, parce qu'ils protègent la valeur du compte :
aucun produit financier, aucune contrefaçon, aucun partenariat sans `#ad`.

## Phase 4 — le site de vêtements

C'est la destination. Tout le contenu mode des phases 1 à 3 sert à ça : au
lancement, l'audience connaît déjà les critères d'Eve sur les matières, les
coupes et le coût par port. Elle achète une sélection, pas une nouveauté.

Deux points à préparer bien avant l'ouverture :

- **L'approvisionnement.** Revente autorisée, distributeur officiel ou seconde
  main tracée. La contrefaçon est le seul risque qui tue l'entreprise entière.
- **La cohérence.** Une boutique qui vend ce qu'Eve n'a jamais recommandé perd
  en un mois ce que le contenu a mis un an à construire.

## Ce qui n'arrivera pas

Le système de trading n'est pas commercialisé : ni formation, ni signaux, ni
copie de trades, ni accès privé. Le code refuse de produire ce contenu.

## Suivre les chiffres

```bash
python3 -m eve.cli revenue --add sponsorship 250 --note "collaboration marque X"
python3 -m eve.cli revenue --followers 12000 --views 400000
```

La projection enchaîne trois taux réels (clics → achats → commission) plutôt
qu'un taux unique appliqué aux vues. Les fourchettes sont volontairement
basses.
