# alluxe.ia — la liste, dans l'ordre

Décision de l'opérateur, 2 octobre 2026 : le compte Instagram de Luna est
repris et renommé **@alluxe.ia**, page sans visage sur l'IA pratique en
français. Concept complet (niche, analyse des concurrents, contenu, argent,
messages automatiques, 90 jours, système) :
https://claude.ai/artifact/Ht7E2zj2NGop7AgfGSY6Gb

L'application « Allure » (`app-signaux`) n'est pas concernée par cette liste.

Légende : **[toi]** l'opérateur, **[Claude]** une session Claude, ✅ fait.

## Phase 0 — la bascule (cette semaine)

1. **[toi] Couper la publication automatique de Luna** sur le VPS, sans rien
   effacer :

       crontab -l > ~/crontab.avant-alluxe-ia
       sudo systemctl disable --now luna-planner.timer
       crontab -l | grep -i luna      # puis commenter ces lignes

2. **[toi] Transformer le compte dans l'appli Instagram** :
   - archiver (pas supprimer) les posts et stories à la une de Luna ;
   - nom d'utilisateur `@alluxe.ia`, nom affiché « alluxe.ia · prompts & automatisation » ;
   - bio : « L'IA qui fait le travail à ta place. / Prompts testés, automatisations réelles, zéro blabla. / 👇 Commente PROMPTS sous un post » ;
   - photo de profil : `python3 ops/alluxe_ia.py profil` → `data/alluxe_ia/profil.jpg` ;
   - catégorie du compte pro : « Éducation » ou « Créateur de contenu numérique ».
3. ✅ **[Claude] Gabarit des slides, 9 posts de lancement, publication de
   carrousels** (`alluxe_ia/`, `ops/alluxe_ia.py`, `ops/instagram.py::publier_carrousel`).
4. **[toi] Relire les 9 posts et tester chaque prompt** : `python3 ops/alluxe_ia.py rendre`
   puis ouvrir `data/alluxe_ia/<post>/`. Un prompt non testé ne part pas.
5. **[toi ou Claude] Publier les 9 posts sur 3 jours**, 3 par jour :
   `python3 ops/alluxe_ia.py suivant --confirmer`.

## Phase 1 — la machine à abonnés et à emails (semaine 1)

6. ✅ **[Claude] Le pack gratuit** : PDF de 20 prompts au même gabarit,
   `docs/alluxe_ia/pack-gratuit.pdf` (régénérer : `python3 -m alluxe_ia.pack`).
7. **[toi] La page de téléchargement** (Gumroad ou Lemon Squeezy, gratuit) et
   son lien dans la bio.
8. **[toi] ManyChat** : mots-clés `PROMPTS` (tous les posts) et `PHOTO` (post 02) avec les 4 messages du concept (étape 6).
   Créer le compte ManyChat avec le compte Instagram : Claude ne peut pas le faire.
9. ✅ **[Claude] Publication automatique** : `systemd/alluxe-ia-publication.timer`
   lance `suivant --confirmer` chaque jour à 12 h 30. **Prête, pas installée** :
   à activer seulement après la phase 0 :

       sudo cp systemd/alluxe-ia-publication.* /etc/systemd/system/
       sudo systemctl daemon-reload
       sudo systemctl enable --now alluxe-ia-publication.timer
10. **[Claude] Les 21 posts suivants** (jours 10 à 30 du concept) dans
    `alluxe_ia/posts.json`.

## Phase 2 — accélérer (semaines 2 à 4)

11. **[Claude] Les Reels** : slides animées en vidéo 9:16, publiées par
    `publier_reel` (déjà en place).
12. **[Claude] Suivi des chiffres** : lecture automatique des statistiques
    Instagram (portée, sauvegardes, partages) dans un tableau, chaque dimanche.
13. **[Claude + toi] Le premier produit payant** : guide de 100 prompts + page
    de vente. Lancement vers le jour 45, après le test « commente GUIDE ».

## Phase 3 — après 60 jours

14. Newsletter alimentée par les emails du pack gratuit.
15. Collaborations avec des comptes de taille proche.
16. Application alluxe.ia (bibliothèque de prompts), d'abord en version web,
    sur le Play Store seulement quand ~50 personnes ont acheté.

## À respecter

- « Publicité » ou « Collaboration commerciale » sur tout lien rémunéré,
  « Image virtuelle » sur une image générée par IA dans un contenu commercial
  (loi du 9 juin 2023).
- Le robot de trading n'apparaît que comme histoire technique : jamais de
  résultats, de gains, ni de lien vers Bitvavo.
- Aucune clé, mot de passe ou donnée personnelle visible sur une capture.
