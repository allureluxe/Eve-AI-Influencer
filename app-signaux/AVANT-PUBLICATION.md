# Avant de publier Eve

Ce document est la liste de ce qui doit être vrai le jour de la mise en
ligne, et de ce qui doit être revérifié à chaque mise à jour.

---

## Le conseil qui prime sur tous les autres

**Ne publie rien sur le Play Store tant que le robot n'a pas trois mois
de performances positives et vérifiables.**

Ce n'est pas de la prudence excessive, c'est arithmétique. L'écran
Analyse refuse d'afficher une courbe sous **30 trades clôturés** — et le
robot en produit environ **un par jour**. Publier avant, c'est mettre en
ligne une application dont l'écran principal dit « pas encore assez
d'historique ». Personne ne s'abonne à ça, et personne ne devrait.

**En attendant :** mets l'application en ligne comme site web et donne
l'accès gratuit à vingt personnes. Tu sauras en deux semaines si les
gens accrochent, et tu auras entre-temps l'historique qui rend
l'abonnement défendable.

---

## 1. Sécurité

| Contrôle | Comment | Fait |
|---|---|---|
| Aucune clé API dans l'app | `grep -rE "(service_role\|sk_live\|sk-ant)" app-signaux/src app-signaux/App.tsx` doit être vide | ☐ |
| La clé `service_role` n'est **que** dans les fonctions Edge | Vérifier les variables d'environnement Supabase | ☐ |
| RLS active et cohérente sur chaque table | `psql "$SUPABASE_DB_URL" -f supabase/verifier_securite.sql` — sections 1, 2, 3 et 6 **vides** | ☐ |
| `profiles.tier` non modifiable par l'utilisateur | Section 4 du script : un déclencheur doit être nommé | ☐ |
| Un signal publié ne se réécrit pas | Section 5 : `signals_immuables` doit apparaître | ☐ |
| Limitation de débit sur les fonctions Edge | En place dans `_partage/commun.ts` | ☐ |
| Le webhook RevenueCat exige son secret | `REVENUECAT_WEBHOOK_SECRET` défini côté Supabase **et** dans RevenueCat | ☐ |
| Les fonctions cron exigent leur secret | `EVE_CRON_SECRET` défini | ☐ |

### Le test qui vaut tous les autres

Crée un compte gratuit de test, puis :

```bash
# Avec le jeton d'un compte FREE, demande les signaux.
curl -s "$SUPABASE_URL/functions/v1/signals" \
     -H "Authorization: Bearer $JETON_COMPTE_GRATUIT" | jq '.actifs[].pair'
```

**La sortie ne doit contenir que BTC/EUR, ETH/EUR ou SOL/EUR**, et aucun
signal de moins de deux heures. Si une autre paire apparaît, l'abonnement
ne protège rien — et le corriger après la publication est trop tard.

---

## 2. Conformité Play Store

### Déclaration « Fonctionnalités financières »

Dans Play Console → *Contenu de l'application* → *Applications financières* :

- Type : **information financière / actualités**, pas courtage, pas
  gestion de portefeuille, pas cryptomonnaie négociable.
- **Ne coche pas** « échange de cryptomonnaies » ni « portefeuille ».
  Eve n'exécute aucun ordre et ne détient aucun fonds — cocher ces cases
  déclenche une exigence de licence que l'application n'a pas et ne
  justifie pas.
- Pays de diffusion : là où tu peux répondre en français.

### Textes obligatoires

Cette phrase est déjà **dans l'application** (bas des onglets Signaux et
Compte) et doit figurer **à l'identique** dans la fiche du store :

> Eve publie des analyses de marché. Ce n'est pas un conseil en
> investissement personnalisé. Nous ne détenons aucun fonds.

### Pages publiques à héberger avant la soumission

- `https://eve-signaux.fr/cgu`
- `https://eve-signaux.fr/confidentialite`

Modèles fournis dans `app-signaux/legal/`. Les liens sont déjà en dur
dans l'écran Compte : **une page absente est un motif de rejet**.

### Ce qui est interdit dans la fiche et dans l'app

| Interdit | Pourquoi ce n'est pas négociable |
|---|---|
| Une promesse de gain, un « garanti », un « sans risque » | Motif de retrait, et faux |
| Un témoignage inventé | Motif de retrait, et malhonnête |
| Un chiffre de performance non vérifiable | Motif de retrait |
| Une capture montrant une courbe fabriquée | Idem — les captures doivent venir de données réelles |

Trois barrières le tiennent déjà côté code, et il faut qu'elles restent :

- `gold_bot/market_note.py` → `verifier_la_note()` refuse la note et la
  fait recommencer ;
- `supabase/functions/_partage/redaction.ts` → `verifierLeTon()` refuse
  la notification ;
- `supabase/functions/performance/index.ts` → refuse la courbe sous
  30 trades.

Elles sont testées. **Si un test y échoue, ce n'est pas le test qu'il
faut changer.**

---

## 3. Captures, icône, description

### Captures (8 exigées par Play Console, 1080 × 1920)

À produire **depuis l'application réelle, sur des données réelles.**
Un montage est un motif de rejet et, plus grave, une promesse implicite.

| # | Écran | Ce qu'elle doit montrer |
|---|---|---|
| 1 | Signaux | Une position en cours, avec « au pire, ça te coûte » visible |
| 2 | Signaux | L'historique, **avec au moins un trade perdant à l'écran** |
| 3 | Analyse | La note du matin et ses jauges |
| 4 | Analyse | La courbe, avec le pire recul affiché |
| 5 | Agenda | Une annonce importante et la règle du robot en dessous |
| 6 | Compte | L'offre Eve Plus |
| 7 | Compte | Le bloc « ce qu'Eve ne fait pas » |
| 8 | Accueil | Le deuxième écran (« Eve ne touche jamais à ton argent ») |

La capture 2 est celle qui compte. **Montrer un trade perdant dans la
vitrine** est ce qui distingue cette application des autres, et c'est
plus convaincant qu'une série de gains que personne ne croit.

### Description du store

**Titre court (30 caractères)**

    Eve — signaux crypto suivis

**Description courte (80 caractères)**

    Les positions d'un robot qui trade son propre argent. Pertes comprises.

**Description longue**

```
Eve suit un robot de trading qui achète et vend des cryptomonnaies avec
un compte réel. Chaque fois qu'il ouvre une position, tu la vois : la
crypto, le prix d'entrée, le stop de protection, et l'explication en
français simple.

Tu vois aussi quand il perd. C'est le même flux, sans tri.

CE QUE TU TROUVES DANS L'APPLICATION

• Les positions du robot, au moment où il les prend
• Ce que chaque position peut te coûter, en euros, sur ton capital
• Un point de marché chaque matin, en trois paragraphes
• L'agenda des annonces économiques, et ce que le robot fait autour
• L'historique complet des trades terminés, gagnants et perdants

CE QU'EVE NE FAIT PAS

Eve ne touche jamais à ton argent. Aucune connexion à ton compte, aucun
ordre passé à ta place, aucune clé d'échange demandée.

Eve ne promet aucun gain et ne te dit pas quoi faire. Elle publie ce
qu'un robot fait ; tu décides du reste.

EVE PLUS

Le compte gratuit reçoit Bitcoin, Ethereum et Solana, deux heures après
publication. Eve Plus donne les 70 cryptomonnaies suivies, au moment où
le robot agit.

Eve publie des analyses de marché. Ce n'est pas un conseil en
investissement personnalisé. Nous ne détenons aucun fonds. Les résultats
passés ne préjugent pas des résultats futurs.
```

### Icône (512 × 512)

Un « E » en Newsreader, laiton `#C9A15C` sur encre `#14181D`. Pas de
graphique, pas de flèche, pas de pièce de monnaie : c'est la signature
visuelle de toutes les applications du genre, et elle rend la nôtre
indistinguable dans une liste de résultats.

---

## 4. Checklist avant chaque mise à jour

À dérouler entièrement. Cinq minutes, et elle attrape les régressions
qui ne se voient qu'en production.

### Automatique

```bash
# Le robot
.venv/bin/python -m pytest tests/ -q

# Les fonctions Edge
deno test --allow-net --allow-env supabase/functions/_partage/
deno check supabase/functions/*/index.ts

# L'application
cd app-signaux && ./node_modules/.bin/tsc --noEmit && ./node_modules/.bin/jest

# La base
psql "$SUPABASE_DB_URL" -f supabase/verifier_securite.sql
```

### À la main, sur un vrai téléphone

- [ ] **Premier lancement** : les trois écrans d'accueil s'enchaînent,
      « Passer » fonctionne.
- [ ] **Connexion** : le lien magique arrive et ramène dans
      l'application.
- [ ] **Compte gratuit** : seuls BTC, ETH et SOL apparaissent, aucun
      signal de moins de deux heures.
- [ ] **Mode avion** : les derniers signaux s'affichent avec le bandeau
      « hors ligne — dernières données il y a X minutes ».
- [ ] **Liste vide** : le texte explique qu'un jour sans signal est
      normal (couper temporairement les données pour le vérifier).
- [ ] **Thème clair et thème sombre** : aucun texte illisible, aucune
      zone blanche sur fond sombre.
- [ ] **Achat en bac à sable** : essai → conversion → résiliation →
      expiration. Vérifier après chaque étape que `profiles.tier` suit,
      **et que « résilier » ne coupe pas l'accès immédiatement.**
- [ ] **Notification** : arrivée, texte sans point d'exclamation ni
      emoji, rien reçu entre 23 h et 7 h.
- [ ] **Le bouton « Gérer ou résilier »** ouvre bien Google Play.

### Le cycle d'abonnement en bac à sable, en détail

| Étape | Attendu | Piège |
|---|---|---|
| Début d'essai | `tier` passe à `plus` | Ne pas attendre le premier prélèvement : l'essai donne le droit |
| Conversion | `tier` reste `plus` | — |
| Résiliation | **`tier` reste `plus`** | C'est le piège n° 1 : couper ici est un vol, l'utilisateur a payé jusqu'à la fin |
| Expiration | `tier` repasse à `free` | — |
| Remboursement | `tier` repasse à `free` | — |

---

## 5. Ce qui n'est pas fait, et qu'il faut savoir

Honnêteté sur l'état réel du chantier :

- **La limitation de débit est en mémoire du conteneur.** Elle arrête
  une boucle d'application qui part en vrille, ce qui est le cas réel
  ici. Elle n'arrêterait pas un attaquant déterminé : il faudrait un
  compteur partagé. À traiter le jour où il y a quelque chose à
  attaquer.
- **Aucune fonction Edge n'a tourné contre une vraie base.** Elles
  compilent et leur logique est testée ; le premier déploiement reste
  un premier déploiement.
- **Le fuseau horaire vient du téléphone** au premier lancement. Un
  utilisateur qui voyage ne le voit pas se mettre à jour.
- **Le calcul de performance ne déduit pas les frais.** C'est dit dans
  les hypothèses affichées sous la courbe, mais un utilisateur réel
  gagnera moins que la simulation.
