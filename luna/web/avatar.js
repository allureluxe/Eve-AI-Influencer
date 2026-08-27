/* L'avatar de Luna, dessine en SVG et anime dans le navigateur.
 *
 * Pourquoi dessiner plutot que streamer une video : ca demarre
 * instantanement, ca ne coute rien, ca marche hors ligne, et surtout
 * aucune image intime ne transite chez un tiers. Le rendu est stylise,
 * assume — et il reagit vraiment : il cligne des yeux, il sourit, il
 * bouge les levres pendant qu'elle parle.
 *
 * Si un prestataire d'avatar video est configure cote serveur, app.js
 * bascule sur son flux et ce module reste en veille.
 */
(function (global) {
  "use strict";

  var PEAU = "#f2d3bd", PEAU_OMBRE = "#e0b79e", LEVRES = "#c25b74";
  var CHEVEUX = "#e8c37a", CHEVEUX_OMBRE = "#c9a054", OEIL = "#3d94c9";

  var BOUCHES = {
    ferme:   "M128 206 Q150 212 172 206 Q150 209 128 206",
    sourire: "M126 203 Q150 221 174 203 Q150 211 126 203",
    rire:    "M124 200 Q150 236 176 200 Q150 214 124 200",
    moue:    "M132 210 Q150 199 168 210 Q150 205 132 210",
    o:       "M139 200 Q150 224 161 200 Q150 210 139 200",
    a:       "M130 201 Q150 228 170 201 Q150 212 130 201",
    e:       "M126 205 Q150 216 174 205 Q150 209 126 205",
    m:       "M129 206 Q150 210 171 206 Q150 208 129 206"
  };

  // Chaque expression : sourcils (decalage y, angle), ouverture des yeux,
  // bouche, rougeur, inclinaison de la tete.
  var EXPRESSIONS = {
    neutre:      { sourcils: [0, 0],   yeux: [1, 1],   bouche: "ferme",   rouge: .25, tete: 0 },
    sourire:     { sourcils: [-1, 0],  yeux: [.94, .94], bouche: "sourire", rouge: .4, tete: -1 },
    rire:        { sourcils: [-3, 0],  yeux: [.45, .45], bouche: "rire",    rouge: .6, tete: -3 },
    clin:        { sourcils: [-2, 4],  yeux: [.95, .06], bouche: "sourire", rouge: .5, tete: 2 },
    tendre:      { sourcils: [1, 0],   yeux: [.75, .75], bouche: "sourire", rouge: .55, tete: -2 },
    surprise:    { sourcils: [-6, 0],  yeux: [1.2, 1.2], bouche: "o",       rouge: .3, tete: 0 },
    moue:        { sourcils: [3, 0],   yeux: [.85, .85], bouche: "moue",    rouge: .35, tete: 3 },
    pensive:     { sourcils: [-2, 3],  yeux: [.9, .9],   bouche: "ferme",   rouge: .25, tete: 4 },
    seductrice:  { sourcils: [-1, 2],  yeux: [.6, .6],   bouche: "sourire", rouge: .5, tete: -4 }
  };

  var VISEMES = ["a", "e", "o", "m", "a", "e", "ferme", "o"];

  function svg(fond1, fond2, cadrage) {
    // « cercle » : gros plan sur le visage, pour la pastille et l'appel.
    // « plein »  : le buste entier tient dans le cadre de la visio.
    var ajustement = cadrage === "plein" ? "xMidYMid meet" : "xMidYMid slice";
    return '' +
    '<svg viewBox="0 0 300 320" width="100%" height="100%" preserveAspectRatio="' + ajustement + '">' +
      '<defs>' +
        '<linearGradient id="lu-fond" x1="0" y1="0" x2="0" y2="1">' +
          '<stop offset="0%" stop-color="' + fond1 + '"/>' +
          '<stop offset="100%" stop-color="' + fond2 + '"/>' +
        '</linearGradient>' +
        '<linearGradient id="lu-cheveux" x1="0" y1="0" x2="1" y2="1">' +
          '<stop offset="0%" stop-color="' + CHEVEUX + '"/>' +
          '<stop offset="100%" stop-color="' + CHEVEUX_OMBRE + '"/>' +
        '</linearGradient>' +
        '<radialGradient id="lu-lumiere" cx="35%" cy="25%" r="75%">' +
          '<stop offset="0%" stop-color="#ffffff" stop-opacity=".14"/>' +
          '<stop offset="100%" stop-color="#000000" stop-opacity="0"/>' +
        '</radialGradient>' +
      '</defs>' +
      '<rect id="lu-bg" width="300" height="320" fill="url(#lu-fond)"/>' +
      '<g id="lu-buste">' +
        // cheveux arriere
        '<path d="M60 300 C55 170 80 92 150 92 C220 92 245 170 240 300 Z" fill="url(#lu-cheveux)"/>' +
        // epaules et vetement
        '<path id="lu-vetement" d="M64 320 C70 258 106 236 150 236 C194 236 230 258 236 320 Z" fill="#33243d"/>' +
        '<path id="lu-decollete" d="M126 240 C136 262 164 262 174 240 C166 250 134 250 126 240 Z" fill="#e6d6ef"/>' +
        // cou
        '<path d="M132 200 h36 v42 q-18 12 -36 0 Z" fill="' + PEAU_OMBRE + '"/>' +
        '<g id="lu-tete">' +
          // visage
          '<ellipse cx="150" cy="160" rx="60" ry="72" fill="' + PEAU + '"/>' +
          '<ellipse cx="88" cy="168" rx="8" ry="12" fill="' + PEAU + '"/>' +
          '<ellipse cx="212" cy="168" rx="8" ry="12" fill="' + PEAU + '"/>' +
          // boucles d oreille
          '<circle id="lu-bijou-g" cx="88" cy="182" r="4" fill="#e6d6ef"/>' +
          '<circle id="lu-bijou-d" cx="212" cy="182" r="4" fill="#e6d6ef"/>' +
          // frange
          '<path d="M90 132 C100 96 200 96 210 132 C196 116 176 110 150 122 C124 110 104 116 90 132 Z" fill="url(#lu-cheveux)"/>' +
          '<path d="M88 140 C86 112 108 88 150 88 C192 88 214 112 212 140 C206 118 184 104 150 104 C116 104 94 118 88 140 Z" fill="url(#lu-cheveux)"/>' +
          // sourcils
          '<path id="lu-sourcil-g" d="M112 140 Q128 132 144 139" stroke="' + CHEVEUX_OMBRE + '" stroke-width="4" fill="none" stroke-linecap="round"/>' +
          '<path id="lu-sourcil-d" d="M156 139 Q172 132 188 140" stroke="' + CHEVEUX_OMBRE + '" stroke-width="4" fill="none" stroke-linecap="round"/>' +
          // yeux
          '<g id="lu-oeil-g">' +
            '<ellipse cx="128" cy="158" rx="12.5" ry="8.5" fill="#fff"/>' +
            '<circle cx="128" cy="158" r="7" fill="' + OEIL + '"/>' +
            '<circle cx="128" cy="158" r="3" fill="#1b1220"/>' +
            '<circle cx="131" cy="155" r="2" fill="#fff" opacity=".85"/>' +
            '<path d="M114 152 Q128 144 142 152" stroke="#4a3326" stroke-width="2.5" fill="none" stroke-linecap="round"/>' +
          '</g>' +
          '<g id="lu-oeil-d">' +
            '<ellipse cx="172" cy="158" rx="12.5" ry="8.5" fill="#fff"/>' +
            '<circle cx="172" cy="158" r="7" fill="' + OEIL + '"/>' +
            '<circle cx="172" cy="158" r="3" fill="#1b1220"/>' +
            '<circle cx="175" cy="155" r="2" fill="#fff" opacity=".85"/>' +
            '<path d="M158 152 Q172 144 186 152" stroke="#4a3326" stroke-width="2.5" fill="none" stroke-linecap="round"/>' +
          '</g>' +
          // rougeur
          '<ellipse id="lu-rouge-g" cx="116" cy="182" rx="13" ry="8" fill="#e58aa0" opacity=".3"/>' +
          '<ellipse id="lu-rouge-d" cx="184" cy="182" rx="13" ry="8" fill="#e58aa0" opacity=".3"/>' +
          // nez
          '<path d="M150 168 q-5 12 2 15" stroke="' + PEAU_OMBRE + '" stroke-width="2.5" fill="none" stroke-linecap="round"/>' +
          // bouche
          '<path id="lu-bouche" d="' + BOUCHES.sourire + '" fill="' + LEVRES + '"/>' +
        '</g>' +
        // meches devant les epaules
        '<path d="M92 132 C74 190 76 244 84 300 L104 300 C92 244 92 188 104 140 Z" fill="url(#lu-cheveux)" opacity=".95"/>' +
        '<path d="M208 132 C226 190 224 244 216 300 L196 300 C208 244 208 188 196 140 Z" fill="url(#lu-cheveux)" opacity=".95"/>' +
      '</g>' +
      '<rect width="300" height="320" fill="url(#lu-lumiere)" pointer-events="none"/>' +
    '</svg>';
  }

  function creerAvatar(hote, options) {
    options = options || {};
    var fond1 = options.fond1 || "#3a2a34", fond2 = options.fond2 || "#1d1520";
    hote.innerHTML = svg(fond1, fond2, options.cadrage);
    // En cadrage « plein », le SVG est contenu et laisse des bandes : le fond
    // du conteneur reprend le degrade pour que la scene reste d'un seul bloc.
    function peindreHote(a, b) {
      if (options.cadrage === "plein") {
        hote.style.background = "linear-gradient(" + a + ", " + b + ")";
      }
    }
    peindreHote(fond1, fond2);
    var q = function (id) { return hote.querySelector("#" + id); };
    var elements = {
      bg: q("lu-bg"), tete: q("lu-tete"), bouche: q("lu-bouche"),
      oeilG: q("lu-oeil-g"), oeilD: q("lu-oeil-d"),
      sourcilG: q("lu-sourcil-g"), sourcilD: q("lu-sourcil-d"),
      rougeG: q("lu-rouge-g"), rougeD: q("lu-rouge-d"),
      vetement: q("lu-vetement"), decollete: q("lu-decollete"),
      bijouG: q("lu-bijou-g"), bijouD: q("lu-bijou-d"),
      degrade: hote.querySelectorAll("#lu-fond stop")
    };

    var etat = { expression: "sourire", parle: false, cligne: false };
    var minuteurBouche = null, minuteurClin = null;

    function echelleOeil(el, cx, cy, s) {
      el.setAttribute("transform",
        "translate(" + cx + " " + cy + ") scale(1 " + s + ") translate(" + (-cx) + " " + (-cy) + ")");
    }

    function appliquer() {
      var e = EXPRESSIONS[etat.expression] || EXPRESSIONS.sourire;
      var ouvertureG = etat.cligne ? 0.06 : e.yeux[0];
      var ouvertureD = etat.cligne ? 0.06 : e.yeux[1];
      echelleOeil(elements.oeilG, 128, 158, ouvertureG);
      echelleOeil(elements.oeilD, 172, 158, ouvertureD);
      elements.sourcilG.setAttribute("transform", "translate(0 " + e.sourcils[0] + ") rotate(" + (-e.sourcils[1]) + " 128 138)");
      elements.sourcilD.setAttribute("transform", "translate(0 " + e.sourcils[0] + ") rotate(" + e.sourcils[1] + " 172 138)");
      elements.rougeG.setAttribute("opacity", e.rouge);
      elements.rougeD.setAttribute("opacity", e.rouge);
      elements.tete.setAttribute("transform", "rotate(" + e.tete + " 150 200)");
      if (!etat.parle) elements.bouche.setAttribute("d", BOUCHES[e.bouche] || BOUCHES.ferme);
    }

    function clignerPlusTard() {
      minuteurClin = setTimeout(function () {
        etat.cligne = true; appliquer();
        setTimeout(function () { etat.cligne = false; appliquer(); clignerPlusTard(); }, 110);
      }, 2600 + Math.random() * 3800);
    }
    clignerPlusTard();
    appliquer();

    return {
      expression: function (nom) {
        if (EXPRESSIONS[nom]) { etat.expression = nom; appliquer(); }
      },
      tenue: function (couleurs) {
        if (!couleurs) return;
        elements.vetement.setAttribute("fill", couleurs[0]);
        elements.decollete.setAttribute("fill", couleurs[1]);
        elements.bijouG.setAttribute("fill", couleurs[1]);
        elements.bijouD.setAttribute("fill", couleurs[1]);
      },
      ambiance: function (fond) {
        if (!fond || elements.degrade.length < 2) return;
        elements.degrade[0].setAttribute("stop-color", fond[0]);
        elements.degrade[1].setAttribute("stop-color", fond[1]);
        peindreHote(fond[0], fond[1]);
      },
      parler: function (actif) {
        etat.parle = !!actif;
        if (minuteurBouche) { clearInterval(minuteurBouche); minuteurBouche = null; }
        if (!actif) { appliquer(); return; }
        minuteurBouche = setInterval(function () {
          var v = VISEMES[Math.floor(Math.random() * VISEMES.length)];
          elements.bouche.setAttribute("d", BOUCHES[v]);
        }, 105);
      },
      detruire: function () {
        clearInterval(minuteurBouche); clearTimeout(minuteurClin); hote.innerHTML = "";
      }
    };
  }

  global.LunaAvatar = { creer: creerAvatar, expressions: Object.keys(EXPRESSIONS) };
})(window);
