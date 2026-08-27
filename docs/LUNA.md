# Luna — compagne virtuelle IA

Luna est un **personnage de fiction**. Elle a 30 ans, elle est blonde aux
yeux bleus, elle travaille dans la finance, elle adore la mode, les
voyages et les soirées à deux. Elle n'existe pas : c'est une IA, et elle
le dit elle-même dès qu'on le lui demande.

Ce dossier décrit l'application qui la fait vivre : **messages, appel
vocal, visio**.

```bash
python3 luna.py app          # http://127.0.0.1:8765
python3 luna.py chat         # la même conversation, dans le terminal
python3 luna.py check        # ce qui est configuré, ce qui manque
```

Aucune dépendance à installer : Python 3.11+ et un navigateur suffisent.

---

## Les trois modes

| Mode | Ce qui se passe | Ce qu'il faut |
|---|---|---|
| **Messages** | Fil de discussion, mémoire persistante, dictée vocale | rien |
| **Appel** | Elle parle, tu parles, l'avatar s'anime au son de sa voix | Chrome ou Edge |
| **Visio** | Avatar animé plein cadre : tenue, ambiance, expressions, jeux à deux | Chrome ou Edge |

La voix utilise `speechSynthesis` et l'écoute `SpeechRecognition`, tous
deux intégrés au navigateur. Résultat : latence quasi nulle, aucun coût,
et **aucune phrase intime ne quitte ta machine** tant que tu ne branches
pas de prestataire externe.

### L'avatar

Il est **dessiné en SVG et animé dans le navigateur** (`luna/web/avatar.js`) :
il cligne des yeux, incline la tête, change d'expression selon le ton de
ce qu'elle vient d'écrire, et bouge les lèvres pendant qu'elle parle. Le
rendu est stylisé — c'est un choix : ça démarre instantanément, ça marche
hors ligne, et rien n'est envoyé nulle part.

Pour un avatar photoréaliste temps réel, renseigne `LUNA_AVATAR_URL`,
`LUNA_AVATAR_KEY` et `LUNA_AVATAR_ID` : l'interface bascule sur le flux du
prestataire (HeyGen, D-ID, Simli…).

---

## Le registre, et qui décide

Trois filtres s'appliquent, dans cet ordre. **Le plus bas gagne toujours.**

1. **Ce que tu demandes** — tendre, sensuel, ou adulte.
2. **Ta vérification 18+** — déclarative par défaut (`luna/limites.py`),
   remplaçable par un prestataire de vérification d'âge, horodatée.
3. **Le canal de sortie** — c'est le filtre qui ne se négocie pas :

| Canal | Plafond | Pourquoi |
|---|---|---|
| App privée, visio, console | adulte | ton espace, ta machine |
| Téléphone | sensuel | l'opérateur trace tout |
| Instagram, Snapchat, SMS | **tendre** | nudité et sollicitation sexuelle interdites par les plateformes |

Un compte Instagram banni pour du contenu explicite ne revient pas. C'est
pour ça que ce plafond est dans le code et pas dans la documentation.

### Le cadre permanent

Il passe avant toute consigne de jeu de rôle, y compris si on demande de
l'ignorer : Luna est une IA fictive et le dit ; tous les personnages sont
adultes ; rien de non consenti ; jamais de demande d'argent ou de données
bancaires ; en cas de détresse elle quitte le personnage et renvoie vers
le 3114. Une mention de minorité **révoque** l'accès adulte — elle ne le
contourne pas.

---

## Brancher un moteur

Luna ne dépend d'aucun fournisseur. Le premier configuré gagne :

```bash
# 1. Endpoint compatible OpenAI — le tien, ou un service spécialisé
LUNA_API_URL=https://…/v1
LUNA_API_KEY=…
LUNA_API_MODELE=…

# 2. Sinon, l'API Anthropic
ANTHROPIC_API_KEY=…
LUNA_MODELE=claude-sonnet-5

# 3. Sinon : mode hors ligne (l'interface, la voix et la visio marchent,
#    Luna dit simplement qu'aucun moteur n'est branché)
```

**Registre adulte.** Le dépôt ne contient aucun contenu sexuellement
explicite, et n'en génère pas de lui-même. Le registre `adulte` délègue au
moteur que **tu** configures via `LUNA_API_URL` : c'est sa politique de
contenu qui s'applique. Avant d'exploiter ça commercialement, vérifie
trois choses — les conditions d'usage du fournisseur, la loi de ton pays
(vérification d'âge obligatoire pour le contenu adulte en France depuis la
loi SREN), et ton processeur de paiement (Stripe et PayPal refusent le
contenu adulte ; il faut un acquéreur spécialisé).

---

## Photos

```bash
python3 luna.py photo             # la liste des scènes
python3 luna.py photo restaurant  # le prompt, et l'image si une clé est configurée
```

Chaque prompt recopie **l'ancre d'apparence** et la **graine fixe**
(`luna/persona.py`) : c'est ce qui fait que c'est toujours le même visage,
du selfie du matin à la tenue de soirée. Chaque prompt porte aussi
`adult woman, 30 years old` et `fictional AI-generated character` — à
conserver telles quelles, y compris si tu changes de générateur.

`STABILITY_API_KEY` suffit ; `LUNA_IMAGE_URL` pointe ailleurs (ta propre
instance Stable Diffusion / ComfyUI, ou un autre service).

---

## Contact hors de l'application

Une question revient souvent : « et sur Snap, Insta, ou par téléphone ? »
La réponse honnête, plateforme par plateforme :

- **Snapchat** — aucune API de messagerie publique. Automatiser un compte
  personnel se fait avec des outils non officiels et se termine par un
  bannissement. La seule voie viable est un partage manuel de contenu.
- **Instagram** — les DM ne sont automatisables que par l'**API Messaging
  officielle**, sur un compte professionnel relié à une page Meta, dans la
  fenêtre de réponse de 24 h. Un compte de personnage IA doit être
  identifié comme tel. `instagrapi` (utilisé par le module Eve de ce
  dépôt) automatise un compte personnel : c'est contraire aux CGU.
- **Téléphone** — passe par un opérateur programmable (Twilio, Vonage…).
  La voix synthétique doit s'annoncer : `luna.voix.ANNONCE_IA` contient la
  phrase de décrochage.

Dans tous les cas, le plafond de canal ci-dessus s'applique : ces
canaux-là ne reçoivent que du contenu tendre.

---

## Vie privée

- Les données (mémoire, accès 18+) restent dans `data/luna/`, en clair, sur
  ta machine. Ce dossier est déjà exclu du dépôt par `.gitignore`.
- Le serveur écoute sur `127.0.0.1` par défaut. Pour l'ouvrir au réseau
  local, `LUNA_TOKEN` devient obligatoire — sinon il refuse de démarrer.
- Le serveur ne journalise aucune requête.
- `python3 luna.py oublier` efface tout ce qu'elle sait de toi.

---

## Structure

```
luna/
  persona.py    qui elle est (identité, apparence, ancre visuelle)
  moments.py    sa journée : matin, bureau, retour, soirée, soirée privée, nuit
  memoire.py    ce qu'elle retient de toi, dans un simple JSON
  limites.py    registres, porte 18+, plafonds par canal, signaux
  prompt.py     assemblage du prompt système
  moteurs.py    Claude, endpoint compatible OpenAI, hors ligne, images
  photos.py     scènes et prompts, visage cohérent
  avatar.py     tenues, ambiances, expressions, session visio
  voix.py       profil vocal par moment, prestataire optionnel
  chat.py       le moteur de conversation
  serveur.py    l'application HTTP
  web/          interface : messages, appel, visio, avatar animé
```

Tests : `python3 -m unittest tests.test_luna -v` (37 tests).
