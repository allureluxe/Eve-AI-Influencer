# Les images de l'application

| Fichier | Sert à | Taille |
|---|---|---|
| `logo-allure.png` | Le logo dans l'application (en-têtes, accueil, connexion) | 128 × 111 |
| `logo-detoure.png` | Le même, fond rendu transparent | 120 × 105 |
| `embleme.png` | L'emblème seul, sans le mot « ALLURE » | 120 × 72 |
| `icone.png` | L'icône du Play Store et de l'application | 1024 × 1024 |
| `icone-adaptative.png` | L'avant-plan de l'icône Android adaptative | 1024 × 1024 |
| `lancement.png` | L'écran de lancement | 1024 × 1024 |

## Pourquoi l'icône ne porte pas le mot « ALLURE »

Une icône d'application se regarde à **48 points** sur un téléphone —
environ un centimètre. À cette taille, un mot de six lettres devient une
tache grise. Toutes les icônes qui tiennent le coup sont un emblème seul.

Le nom, lui, s'affiche **sous** l'icône, écrit par Android. Le mettre
aussi dans l'image le fait apparaître deux fois.

L'écran de lancement, lui, garde le logo complet : là, il y a la place,
et c'est le moment où le nom doit se lire.

## Une limite à connaître

Le logo source fait **128 × 111 pixels**. Les icônes de 1024 × 1024 sont
donc un agrandissement de huit fois, adouci au filtre Lanczos. Ça passe —
l'emblème est du trait épais, il supporte bien l'agrandissement — mais
sur un grand écran, un œil averti verra que ce n'est pas net.

**Si tu as le logo d'origine** (fichier Illustrator, SVG, ou un PNG de
1000 pixels ou plus), remplace `logo-allure.png` et relance :

    cd app-signaux/assets
    convert logo-allure.png -alpha set -fuzz 12% \
      -fill none -floodfill +0+0 white -trim +repage logo-detoure.png
    convert logo-detoure.png -crop <emblème seul> +repage -trim +repage embleme.png
    convert embleme.png -filter Lanczos -resize 660x660 -background none \
      -gravity center -extent 1024x1024 \
      \( -size 1024x1024 xc:'#EFE73C' \) +swap -composite \
      -alpha remove -alpha off icone.png
