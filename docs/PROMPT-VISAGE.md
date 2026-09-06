# Le prompt du visage d'Eve

À coller tel quel dans n'importe quel générateur d'images. En anglais :
tous les modèles y répondent mieux.

## Prompt

```
candid iPhone photo of a 26 year old French woman, long golden blonde hair
with soft natural waves and loose flyaway strands, warm hazel eyes, light
sun-kissed skin with faint freckles across the nose, heart-shaped face,
high cheekbones, small gold hoop earrings, barely any makeup, wearing a
plain white t-shirt, head and shoulders, looking straight into the lens,
relaxed natural expression, soft daylight from a window on her left,
plain wall behind her, shallow depth of field, visible skin pores and fine
texture, light shine on the forehead and nose, faint under-eye shadows,
slight facial asymmetry, imperfect framing, unretouched, shot on iPhone 15
Pro, photojournalism, no filter, no beauty retouching
```

## Prompt négatif

```
3d render, cgi, illustration, painting, drawing, anime, cartoon, digital art,
airbrushed, smooth plastic skin, waxy, doll-like, porcelain skin, perfect
symmetry, beauty filter, instagram filter, oversaturated, hdr, studio
lighting, glamour shot, retouched, flawless skin, deformed hands, extra
fingers, distorted face, asymmetric eyes, watermark, text, logo
```

## Modèles qui rendent du photoréalisme

Du plus accessible au plus exigeant :

| Modèle | Où | Note |
|---|---|---|
| **FLUX.1 dev** ou **FLUX.1.1 pro** | Replicate, fal.ai, Together | Le meilleur rapport qualité/simplicité aujourd'hui |
| **Imagen 4** | Google AI Studio | Très bon sur les visages, facturation à activer |
| **RealVisXL V5** | ComfyUI, Automatic1111, Civitai | Spécialisé portrait photoréaliste |
| **epiCRealism** / **Realistic Vision V6** | ComfyUI, Automatic1111 | Références du visage photoréaliste, gratuits en local |
| **Juggernaut XL** | ComfyUI, SDXL | Bon compromis, polyvalent |

À éviter pour un visage : **sana**, **SD 1.5 de base**, **SDXL de base** — ils
rendent du semi-illustré, quel que soit le prompt.

## Réglages

| Paramètre | Valeur |
|---|---|
| Résolution | 1024×1024 (profil) · 832×1216 (vertical) |
| Steps | 30 à 40 |
| CFG / Guidance | 3,5 pour FLUX · 5 à 7 pour SDXL |
| Sampler | DPM++ 2M Karras |
| Seed | **774921** — le seed d'Eve, à ne jamais changer |

## Ce qui fait le réalisme, par ordre d'importance

1. **Le médium en tête de prompt.** « candid iPhone photo » pèse plus que dix
   adjectifs placés à la fin.
2. **Les défauts.** Pores visibles, brillance sur le front, cernes légers,
   asymétrie, mèches folles. Une peau parfaite est le premier signal d'une
   image générée.
3. **Une lumière nommée et imparfaite.** « lumière du jour venant d'une
   fenêtre à gauche » bat « éclairage studio parfait ».
4. **Le prompt négatif.** Sans « 3d render, illustration, smooth skin », la
   plupart des modèles y retournent d'eux-mêmes.
5. **Le seed fixe.** C'est lui qui garde le même visage d'une image à l'autre.

## Pour un visage rigoureusement identique

Le prompt et le seed tiennent la ressemblance à 70-80 %. Au-delà, il faut
une référence de visage : **IP-Adapter FaceID** dans ComfyUI, alimenté par
huit à dix images validées d'Eve. C'est ce qui sépare un compte crédible
d'un compte dont le visage change chaque semaine.
