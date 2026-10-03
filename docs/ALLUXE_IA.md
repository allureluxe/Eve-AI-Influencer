# alluxe.ia — la liste, dans l'ordre

Décision de l'opérateur, 2 octobre 2026 : le compte Instagram de Luna est
repris et renommé **@alluxe.ia**, page sans visage sur l'IA pratique en
français. Concept complet (niche, analyse des concurrents, contenu, argent,
messages automatiques, 90 jours, système) :
https://claude.ai/artifact/Ht7E2zj2NGop7AgfGSY6Gb

L'application « Allure » (`app-signaux`) n'est pas concernée par cette liste.

**3 oct. : NICHE CHANGÉE.** La niche « packs de prompts » avait été reprise
du compte d'exemple sans recherche ; elle est saturée. Décision de
l'opérateur : **« je construis des systèmes avec l'IA sans être
développeur »** (coulisses, tutos, erreurs). Les 8 prompts de
@_mind__vision_ ont été exécutés un par un : `docs/alluxe_ia/CONCEPT_8_PROMPTS.md`
(recherche : `docs/alluxe_ia/RECHERCHE_NICHE.md`). Mot-clé unique : **KIT**.

Légende : **[toi]** l'opérateur, **[Claude]** une session Claude, ✅ fait.

## Phase 0 — la bascule (cette semaine)

1. **[toi] Couper la publication automatique de Luna** sur le VPS, sans rien
   effacer :

       crontab -l > ~/crontab.avant-alluxe-ia
       sudo systemctl disable --now luna-planner.timer
       crontab -l | grep -i luna      # puis commenter ces lignes

2. **[toi] Transformer le compte dans l'appli Instagram** :
   - archiver (pas supprimer) les posts et stories à la une de Luna ;
   - nom d'utilisateur `@alluxe.ia`, nom affiché « alluxe.ia · je construis avec l'IA » ;
   - bio (choisie le 3 oct.) : « Pas dev. J'ai quand même construit un robot, un labo et une appli avec l'IA. / Je te montre comment. / 👇 Commente KIT » ;
   - stories à la une : Commencer · Le labo · L'appli · Tutos · Kit · Questions ;
   - photo de profil : `python3 ops/alluxe_ia.py profil` → `data/alluxe_ia/profil.jpg` ;
   - catégorie du compte pro : « Éducation » ou « Créateur de contenu numérique ».
3. ✅ **[Claude] Gabarit des slides, 11 posts de lancement (nouvelle niche),
   publication de carrousels** (`alluxe_ia/`, `ops/alluxe_ia.py`, `ops/instagram.py::publier_carrousel`).
4. **[toi] Relire les 11 posts et tester chaque prompt** : `python3 ops/alluxe_ia.py rendre`
   puis ouvrir `data/alluxe_ia/<post>/`. Un prompt non testé ne part pas.
5. **[toi ou Claude] Publier les 9 premiers posts (la grille) sur 5 jours** :
   `python3 ops/alluxe_ia.py suivant --confirmer`.

## Phase 1 — la machine à abonnés et à emails (semaine 1)

6. ✅ **[Claude] Le kit du constructeur** (aimant à emails) : PDF des 12 prompts
   des posts, `docs/alluxe_ia/kit-constructeur.pdf` (régénérer : `python3 -m alluxe_ia.pack`).
7. ✅ **Pas de Gumroad (3 oct.)** : le kit est servi en lien direct depuis Supabase
   (`alluxe-ia-public/kit-constructeur.pdf`, `ALLUXE_IA_KIT_URL`). Robot KIT branché dans Meta
   et minuteur `alluxe-ia-kit.timer` actif depuis le 3 oct. 19 h. Ancien texte :
   **[toi] La page de téléchargement** (Gumroad ou Lemon Squeezy, gratuit) et
   son lien dans la bio.
8. ✅ **4 oct. — décision de l'opérateur : le kit est en LIEN DANS LA BIO.**
   L'envoi en privé sur KIT est abandonné (Meta masque les commentaires à
   l'app en mode Développement ; invitation testeur restée en attente). Le
   minuteur `alluxe-ia-kit` est arrêté et désactivé. Posts, légendes et Reel
   disent « Le kit gratuit : lien en bio ». **[toi]** lien de la bio =
   `https://jwksajhtvhwktkbkpits.supabase.co/storage/v1/object/public/alluxe-ia-public/kit-constructeur.pdf`.
   Historique du robot ci-dessous.

8. ⚠ **Robot KIT — 3 oct. au soir : Meta n'envoie RIEN au webhook.**
   Webhook validé par Meta (GET 200 à 11h16 UTC) mais aucun commentaire reçu
   de la journée : l'application Meta est en mode **Développement**, où Meta
   ne prévient le webhook (et n'autorise les messages privés) que pour les
   comptes testeurs. **Contournement en place** : le robot lit lui-même les
   commentaires des 10 derniers posts à chaque passage (`relever`), essaie le
   message privé, et s'il est refusé répond en public « Le kit est en lien
   dans ma bio 👆 ». **[toi]** mettre le lien du kit dans la bio, et demander
   la vérification de l'app par Meta (accès avancé
   `instagram_business_manage_comments` et `instagram_business_manage_messages`,
   puis mode Live) pour que les messages privés partent.

8. ✅ **[Claude] Le robot KIT** (remplace ManyChat, payant au-delà de 25 contacts) :
   quelqu'un commente KIT → réponse publique + le kit en privé, en moins d'une minute.
   Table et fonction `alluxe-ia-webhook` **déployées sur Supabase le 3 oct.**, inactives
   tant que Meta n'est pas branché. Code : `alluxe_ia/kit.py`, `ops/alluxe_ia_kit.py`,
   `supabase/functions/alluxe-ia-webhook/`.

   **[toi] Le brancher**, une fois la page Gumroad du kit créée :
   1. Choisir un mot de vérification (n'importe lequel, ex. `alluxe-kit-2026`).
   2. Supabase → Edge Functions → Secrets : `IG_WEBHOOK_VERIFY_TOKEN` = ce mot,
      `IG_APP_SECRET` = le secret de l'application Instagram (Meta for Developers →
      ton app → Instagram → Configuration de l'API → « Secret de l'app Instagram »).
   3. Meta for Developers → ton app → Instagram → « Configurer les webhooks » :
      URL `https://jwksajhtvhwktkbkpits.supabase.co/functions/v1/alluxe-ia-webhook`,
      jeton de vérification = le mot ; s'abonner à **comments** et **messages**.
   4. Le jeton Instagram doit porter `instagram_business_manage_comments` et
      `instagram_business_manage_messages` ; sinon refaire l'autorisation avec ces
      deux cases. L'app doit être en mode **Live** pour recevoir les webhooks.
   5. Sur le VPS : `ALLUXE_IA_KIT_URL=<lien Gumroad>` dans `.env`, puis
      `python3 ops/alluxe_ia_kit.py abonner`.
   6. Tester : commenter KIT depuis un autre compte, puis
      `python3 ops/alluxe_ia_kit.py traiter` (essai, n'envoie rien) et
      `python3 ops/alluxe_ia_kit.py etat`.
   7. Activer : `sudo cp systemd/alluxe-ia-kit.{service,timer} /etc/systemd/system/ &&
      sudo systemctl daemon-reload && sudo systemctl enable --now alluxe-ia-kit.timer`.
9. ✅ **[Claude] Publication automatique** : `systemd/alluxe-ia-publication.timer`
   lance `suivant --confirmer` chaque jour à 12 h 30. **Installée le 3 oct. 19 h**, post 1 publié à la main le même soir, puis 1 par jour.
   (texte d'origine : Prête, pas installée)
   à activer seulement après la phase 0 :

       sudo cp systemd/alluxe-ia-publication.* /etc/systemd/system/
       sudo systemctl daemon-reload
       sudo systemctl enable --now alluxe-ia-publication.timer
10. **[Claude] Les posts des semaines 2 à 4** : idées 10 à 30 du prompt n°3, écrites
    chaque dimanche à partir de ce qui s'est réellement passé dans la semaine.
    **[toi] Filmer les Reels écran** (labo, publication auto, agent, appli).

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
- Affiliation : seulement les outils réellement utilisés, avec « Publicité ».
- Le robot de trading n'apparaît que comme histoire technique : jamais de
  résultats, de gains, ni de lien vers Bitvavo.
- Aucune clé, mot de passe ou donnée personnelle visible sur une capture.
