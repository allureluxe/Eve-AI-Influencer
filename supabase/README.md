# Base de données de l'application

Schéma Supabase pour l'application mobile de signaux. Le robot Turtle qui
tourne sur le VPS **écrit** ici avec la clé `service_role` ; l'application
**lit** avec la clé `anon`, au nom d'un utilisateur connecté.

## Ce qui reste à faire, et que je ne peux pas faire à ta place

Créer le projet demande ton compte Supabase. Trois étapes :

```bash
# 1. Créer le projet sur supabase.com/dashboard (région : Europe)

# 2. Installer le CLI et relier le dossier au projet
npm install -g supabase
supabase login
supabase link --project-ref TON_REF     # visible dans l'URL du dashboard

# 3. Appliquer les migrations
supabase db push
```

Pour essayer sans rien déployer : `supabase start` monte une base locale
et applique les migrations dessus.

## Les deux clés, et laquelle ne doit jamais bouger

| clé | où elle vit | ce qu'elle peut |
|---|---|---|
| `anon` | **dans l'application mobile** | lire, filtré par RLS |
| `service_role` | **uniquement sur le VPS** | tout, RLS contourné |

La clé `anon` est publique de fait : n'importe qui peut l'extraire d'un
APK en dix minutes. C'est pour ça que chaque table a des politiques —
elles sont la seule barrière, pas une précaution supplémentaire.

**La clé `service_role` ne doit jamais approcher l'application.** Elle
ignore toutes les politiques.

## Ce que le schéma garantit

- **Un brouillon ne sort jamais.** `published_at is null` = invisible.
  Le filtre est dans la politique, pas dans la requête : une requête
  s'oublie, une politique non.
- **Chacun chez soi.** Un utilisateur ne lit que son profil et ses
  propres trades marqués. Vérifié : une tentative de suppression des
  lignes d'autrui n'en touche aucune.
- **Personne ne s'offre l'abonnement.** Le `tier` est verrouillé par un
  déclencheur ; seul `service_role` peut le changer, après paiement.
- **Le stop est du bon côté.** Un stop au-dessus du prix d'entrée sur un
  achat est refusé par la base — c'est une erreur qui déclencherait la
  vente immédiatement.

## Vérification faite

Les cinq migrations ont été rejouées sur PostgreSQL 18, puis neuf
tentatives d'abus ont été essayées depuis un compte ordinaire : écrire un
signal, en modifier un, en supprimer, changer son palier, voler un autre
profil, écrire dans l'agenda, écrire une analyse, marquer un trade au nom
d'un autre, effacer le trade d'un autre. **Les neuf échouent.**

Deux défauts ont été trouvés par ces tests et corrigés :

1. La politique de modification du profil s'interrogeait elle-même :
   `infinite recursion detected in policy for relation "profiles"`. Le
   changement de palier était refusé — mais toute modification l'était
   aussi, préférences comprises.
2. Le verrou du palier utilisait `session_user` et `security definer` :
   il laissait passer le changement. `security definer` remplace
   `current_user` par le propriétaire de la fonction, ce qui rendait le
   contrôle toujours vrai.

## Ce qui n'est pas encore là

- Aucune table de facturation : le passage en `plus` devra être écrit par
  le serveur après vérification du paiement.
- Aucune donnée d'exemple. `supabase/seed.sql` reste à écrire si tu veux
  une base locale peuplée pour développer l'application.
