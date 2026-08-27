/* L'application : messages, appel, visio.
 *
 * Tout passe par la petite API JSON du serveur local. La voix et l'ecoute
 * restent dans le navigateur (speechSynthesis / SpeechRecognition) : c'est
 * instantane, gratuit, et aucune phrase intime ne part chez un tiers tant
 * qu'aucun prestataire n'est configure.
 */
(function () {
  "use strict";

  var jeton = new URLSearchParams(location.search).get("token") || "";
  var etat = null;
  var avatars = {};
  var vocalActif = false;     // Luna repond a voix haute
  var ecoute = null;          // instance de reconnaissance vocale
  var registreVise = "sensuel";
  // Choix courants de la visio : changer l'ambiance ne doit pas rhabiller
  // Luna, et changer de tenue ne doit pas rallumer la lumiere du jour.
  var choixVisio = { tenue: "", ambiance: "" };

  function $(s) { return document.querySelector(s); }
  function $$(s) { return Array.prototype.slice.call(document.querySelectorAll(s)); }

  function api(chemin, corps) {
    var options = { method: corps ? "POST" : "GET", headers: {} };
    if (jeton) options.headers["x-luna-token"] = jeton;
    if (corps) {
      options.headers["content-type"] = "application/json";
      options.body = JSON.stringify(corps);
    }
    return fetch(chemin + (jeton ? "?token=" + encodeURIComponent(jeton) : ""), options)
      .then(function (r) { return r.json(); });
  }

  // ---------------------------------------------------------------- voix
  var voixChoisie = null;
  function trouverVoix(profil) {
    if (voixChoisie) return voixChoisie;
    var toutes = window.speechSynthesis ? speechSynthesis.getVoices() : [];
    var fr = toutes.filter(function (v) { return /^fr/i.test(v.lang); });
    var preferees = (profil && profil.prefere) || [];
    for (var i = 0; i < preferees.length; i++) {
      var trouvee = fr.filter(function (v) { return v.name.indexOf(preferees[i]) >= 0; })[0];
      if (trouvee) { voixChoisie = trouvee; return trouvee; }
    }
    voixChoisie = fr[0] || toutes[0] || null;
    return voixChoisie;
  }
  if (window.speechSynthesis) {
    speechSynthesis.onvoiceschanged = function () { voixChoisie = null; };
  }

  function parler(texte, profil, avatar) {
    if (!window.speechSynthesis || !texte) return;
    // On retire les emojis : « emoji coeur rouge » lu a voix haute, non.
    var propre = texte.replace(/[\u{1F300}-\u{1FAFF}\u{2600}-\u{27BF}️]/gu, "");
    speechSynthesis.cancel();
    var phrase = new SpeechSynthesisUtterance(propre);
    var v = trouverVoix(profil);
    if (v) phrase.voice = v;
    phrase.lang = (profil && profil.langue) || "fr-FR";
    phrase.pitch = (profil && profil.hauteur) || 1.05;
    phrase.rate = (profil && profil.debit) || 1;
    phrase.onstart = function () { if (avatar) avatar.parler(true); marquerParle(true); };
    phrase.onend = function () { if (avatar) avatar.parler(false); marquerParle(false); };
    speechSynthesis.speak(phrase);
  }

  function marquerParle(actif) {
    var halo = $("#halo");
    if (halo) halo.classList.toggle("parle", actif);
  }

  // ------------------------------------------------------------- ecoute
  function creerEcoute(surTexte, surFin) {
    var Rec = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!Rec) return null;
    var rec = new Rec();
    rec.lang = "fr-FR";
    rec.interimResults = true;
    rec.continuous = false;
    rec.onresult = function (e) {
      var texte = "", final = false;
      for (var i = e.resultIndex; i < e.results.length; i++) {
        texte += e.results[i][0].transcript;
        if (e.results[i].isFinal) final = true;
      }
      surTexte(texte, final);
    };
    rec.onend = function () { if (surFin) surFin(); };
    return rec;
  }

  // ----------------------------------------------------------- messages
  function ajouterBulle(qui, texte) {
    var fil = $("#fil");
    var el = document.createElement("div");
    el.className = "bulle-msg " + qui;
    el.textContent = texte;
    fil.appendChild(el);
    fil.scrollTop = fil.scrollHeight;
    return el;
  }

  function bulleAttente() {
    var el = ajouterBulle("elle", "");
    el.className += " points";
    el.innerHTML = "<span>●</span><span>●</span><span>●</span>";
    return el;
  }

  function envoyer(texte, canal, cible) {
    if (!texte.trim()) return Promise.resolve();
    if (canal === "app") ajouterBulle("moi", texte);
    var attente = canal === "app" ? bulleAttente() : null;
    return api("/api/message", { texte: texte, canal: canal || "app" })
      .then(function (r) {
        if (attente) attente.remove();
        if (canal === "app") ajouterBulle("elle", r.texte);
        appliquerReponse(r, cible);
        return r;
      })
      .catch(function (e) {
        if (attente) attente.remove();
        ajouterBulle("systeme", "Erreur : " + e.message);
      });
  }

  function appliquerReponse(r, cible) {
    Object.keys(avatars).forEach(function (cle) {
      if (avatars[cle]) avatars[cle].expression(r.expression);
    });
    if (r.erreur) console.warn("moteur:", r.erreur);
    if (vocalActif && cible) parler(r.texte, r.voix, avatars[cible]);
    if (cible === "visio") {
      var bulle = $("#bulle-visio");
      bulle.hidden = false;
      bulle.textContent = r.texte;
    }
    if (cible) {
      var zone = cible === "visio" ? $("#visio-transcription") : $("#appel-transcription");
      if (zone) zone.textContent = "Luna : " + r.texte;
    }
    rafraichirEtat();
  }

  // -------------------------------------------------------------- vues
  function montrerVue(nom) {
    $$(".vue").forEach(function (v) { v.classList.remove("active"); });
    $("#vue-" + nom).classList.add("active");
    $$(".onglets button").forEach(function (b) {
      b.classList.toggle("actif", b.dataset.vue === nom);
    });
  }

  // ------------------------------------------------------------- porte
  function ouvrirPorte(registreDemande) {
    registreVise = registreDemande || "sensuel";
    $("#porte").hidden = false;
    $("#porte-majeur").checked = false;
    $("#porte-fiction").checked = false;
    $("#porte-valider").disabled = true;
  }

  function verifierCases() {
    $("#porte-valider").disabled = !($("#porte-majeur").checked && $("#porte-fiction").checked);
  }

  // ----------------------------------------------------------- reglages
  function rendrePastilles(hote, items, actifCle, surClic) {
    hote.innerHTML = "";
    items.forEach(function (item) {
      var b = document.createElement("button");
      b.textContent = item.nom;
      if (item.cle === actifCle) b.classList.add("actif");
      b.onclick = function () { surClic(item); };
      hote.appendChild(b);
    });
  }

  function rafraichirEtat() {
    return api("/api/etat").then(function (e) {
      etat = e;
      $("#etat-moment").textContent = e.moment.nom + " — registre « " + e.registre + " »";
      $("#etat-moteur").textContent = "· " + e.moteur.nom;
      $("#memoire-resume").textContent = e.memoire.resume;
      $("#capacites").textContent =
        "moteur       : " + e.moteur.nom + "\n" +
        "images       : " + (e.capacites.images ? "configurees" : "aucune (prompts seuls)") + "\n" +
        "voix externe : " + (e.capacites.voix_externe ? "configuree" : "navigateur") + "\n" +
        "avatar       : " + e.capacites.avatar.type;
      $("#etat-acces").textContent = e.acces.majeur
        ? "18+ confirme (" + e.acces.methode + "), plafond « " + e.acces.registre_max + " »"
        : "18+ non confirme : registre limite a tendre.";

      rendrePastilles($("#liste-registres"),
        [{ cle: "tendre", nom: "Tendre" }, { cle: "sensuel", nom: "Sensuel" },
         { cle: "adulte", nom: "Adulte 18+" }],
        e.registre_demande,
        function (item) {
          if (item.cle !== "tendre" && !e.acces.majeur) { ouvrirPorte(item.cle); return; }
          api("/api/registre", { registre: item.cle }).then(rafraichirEtat);
        });

      rendrePastilles($("#liste-moments"),
        [{ cle: "auto", nom: "Automatique" }].concat(e.moments.map(function (m) {
          return { cle: m.cle, nom: m.nom.split(",")[0] + (m.sur_demande ? " 🔞" : "") };
        })),
        "", function (item) {
          api("/api/moment", { cle: item.cle }).then(function (r) {
            if (r.erreur === "acces_refuse") { ouvrirPorte("sensuel"); return; }
            rafraichirEtat();
          });
        });

      rendrePastilles($("#liste-scenes"),
        e.scenes.map(function (s) {
          return { cle: s.cle, nom: s.titre + (s.registre !== "tendre" ? " 🔞" : "") };
        }), "", function (item) { demanderPhoto(item.cle); });

      rendrePastilles($("#liste-tenues"),
        e.tenues.map(function (t) {
          return { cle: t.cle, nom: t.nom + (t.registre !== "tendre" ? " 🔞" : "") };
        }), "", function (item) { lancerVisio(item.cle, ""); });

      rendrePastilles($("#liste-ambiances"),
        e.ambiances.map(function (a) { return { cle: a.cle, nom: a.nom }; }),
        "", function (item) { lancerVisio("", item.cle); });

      rendrePastilles($("#liste-jeux"),
        e.jeux.map(function (j) { return { cle: j.cle, nom: j.nom }; }),
        "", function (item) {
          montrerVue("visio");
          envoyer("On joue a « " + item.nom + " » ? " + item.resume, "visio", "visio");
        });
      return e;
    });
  }

  function demanderPhoto(scene) {
    var zone = $("#photo-resultat");
    zone.innerHTML = "<div class='note'>Generation…</div>";
    api("/api/photo", { scene: scene }).then(function (r) {
      if (r.erreur === "acces_refuse") { zone.innerHTML = ""; ouvrirPorte("sensuel"); return; }
      if (r.erreur) { zone.innerHTML = "<div class='note'>" + r.message + "</div>"; return; }
      zone.innerHTML = "<div class='note'>" + (r.legende || "") + "</div>" +
        (r.image ? "<img alt='" + r.titre + "' src='" + r.image + "'>"
                 : "<div class='note'>" + (r.message || "") + "</div>" +
                   "<div class='prompt'>" + r.prompt + "</div>" +
                   "<div class='prompt'>seed " + r.graine + "</div>");
    });
  }

  // -------------------------------------------------------------- visio
  function lancerVisio(tenue, ambiance) {
    if (tenue) choixVisio.tenue = tenue;
    if (ambiance) choixVisio.ambiance = ambiance;
    return api("/api/visio", { tenue: choixVisio.tenue, ambiance: choixVisio.ambiance })
      .then(function (s) {
        if (!avatars.visio) {
          avatars.visio = LunaAvatar.creer($("#avatar-visio"), {
            cadrage: "plein",
            fond1: s.ambiance.fond[0], fond2: s.ambiance.fond[1] });
        }
        avatars.visio.ambiance(s.ambiance.fond);
        avatars.visio.tenue(s.tenue.couleurs);
        avatars.visio.expression(s.expression);
        $("#bandeau-visio").textContent = "IA — " + s.tenue.nom + " · " + s.ambiance.nom;
        // Le serveur peut refuser une tenue trop osee pour le registre :
        // on se realigne sur ce qu'il a reellement choisi.
        choixVisio.tenue = s.tenue.cle;
        choixVisio.ambiance = s.ambiance.cle;
        return s;
      });
  }

  // ------------------------------------------------------------ demarrage
  function init() {
    avatars.pastille = LunaAvatar.creer($("#pastille-avatar"), {});
    $$(".onglets button").forEach(function (b) {
      b.onclick = function () { montrerVue(b.dataset.vue); };
    });

    $("#porte-majeur").onchange = verifierCases;
    $("#porte-fiction").onchange = verifierCases;
    $("#porte-valider").onclick = function () {
      api("/api/acces", { majeur: true, methode: "declaratif", registre_max: registreVise })
        .then(function () { return api("/api/registre", { registre: registreVise }); })
        .then(function () { $("#porte").hidden = true; rafraichirEtat(); });
    };
    $("#porte-refuser").onclick = function () {
      api("/api/registre", { registre: "tendre" }).then(function () {
        $("#porte").hidden = true; rafraichirEtat();
      });
    };
    $("#ouvrir-porte").onclick = function () { ouvrirPorte("sensuel"); };
    $("#revoquer").onclick = function () {
      api("/api/acces", { revoquer: true }).then(rafraichirEtat);
    };
    $("#oublier").onclick = function () {
      if (confirm("Luna oubliera tout ce qu'elle sait de toi. Continuer ?"))
        api("/api/oublier", {}).then(rafraichirEtat);
    };

    // messages
    $("#saisie").onsubmit = function (e) {
      e.preventDefault();
      var texte = $("#champ").value;
      $("#champ").value = "";
      envoyer(texte, "app", null);
    };
    $("#dicter").onclick = function () {
      var rec = creerEcoute(function (texte, final) {
        $("#champ").value = texte;
        if (final) $("#saisie").dispatchEvent(new Event("submit"));
      });
      if (!rec) { alert("La dictee demande Chrome ou Edge."); return; }
      rec.start();
    };

    // appel
    $("#appel-demarrer").onclick = function () {
      vocalActif = true;
      if (!avatars.appel) avatars.appel = LunaAvatar.creer($("#avatar-appel"), {});
      $("#appel-demarrer").hidden = true;
      $("#appel-parler").hidden = false;
      $("#appel-raccrocher").hidden = false;
      $("#appel-etat").textContent = "En ligne — maintiens le micro pour parler";
      api("/api/ouverture", { canal: "telephone" }).then(function (r) {
        $("#appel-transcription").textContent = "Luna : " + r.texte;
        avatars.appel.expression(r.expression);
        parler(r.texte, r.voix, avatars.appel);
      });
    };
    $("#appel-raccrocher").onclick = function () {
      vocalActif = false;
      if (window.speechSynthesis) speechSynthesis.cancel();
      if (ecoute) { try { ecoute.stop(); } catch (e) {} ecoute = null; }
      $("#appel-demarrer").hidden = false;
      $("#appel-parler").hidden = true;
      $("#appel-raccrocher").hidden = true;
      $("#appel-etat").textContent = "Appel termine";
    };
    brancherMicro($("#appel-parler"), "telephone", "appel", $("#appel-transcription"));

    // visio
    $("#visio-demarrer").onclick = function () {
      vocalActif = true;
      lancerVisio("", "").then(function (s) {
        $("#visio-demarrer").hidden = true;
        $("#visio-parler").hidden = false;
        $("#visio-arreter").hidden = false;
        $("#bulle-visio").hidden = false;
        $("#bulle-visio").textContent = s.ouverture;
        parler(s.ouverture, s.voix, avatars.visio);
      });
    };
    $("#visio-arreter").onclick = function () {
      vocalActif = false;
      if (window.speechSynthesis) speechSynthesis.cancel();
      $("#visio-demarrer").hidden = false;
      $("#visio-parler").hidden = true;
      $("#visio-arreter").hidden = true;
      $("#bulle-visio").hidden = true;
    };
    brancherMicro($("#visio-parler"), "visio", "visio", $("#visio-transcription"));

    rafraichirEtat().then(function (e) {
      if (!e.acces.majeur) ouvrirPorte("sensuel");
      return api("/api/ouverture", { canal: "app" });
    }).then(function (r) {
      if (etat && etat.historique) {
        etat.historique.forEach(function (t) {
          ajouterBulle(t.role === "user" ? "moi" : "elle", t.texte);
        });
      }
      ajouterBulle("elle", r.texte);
      if (avatars.pastille) avatars.pastille.expression(r.expression);
    });
  }

  function brancherMicro(bouton, canal, cible, zone) {
    if (!bouton) return;
    var rec = null;
    function demarrer() {
      if (window.speechSynthesis) speechSynthesis.cancel();
      rec = creerEcoute(function (texte, final) {
        zone.textContent = "Toi : " + texte;
        if (final) envoyer(texte, canal, cible);
      });
      if (!rec) { alert("La reconnaissance vocale demande Chrome ou Edge."); return; }
      ecoute = rec;
      bouton.classList.add("actif");
      try { rec.start(); } catch (e) {}
    }
    function arreter() {
      bouton.classList.remove("actif");
      if (rec) { try { rec.stop(); } catch (e) {} }
    }
    bouton.addEventListener("mousedown", demarrer);
    bouton.addEventListener("touchstart", function (e) { e.preventDefault(); demarrer(); });
    bouton.addEventListener("mouseup", arreter);
    bouton.addEventListener("mouseleave", arreter);
    bouton.addEventListener("touchend", function (e) { e.preventDefault(); arreter(); });
  }

  document.addEventListener("DOMContentLoaded", init);
})();
