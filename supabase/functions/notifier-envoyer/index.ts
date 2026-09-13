/**
 * Vide la file vers Firebase. Appele toutes les 5 minutes.
 *
 * Un seul metier : prendre ce qui est du, l'envoyer, marquer la ligne.
 * Aucune regle de palier, aucune regle d'heure — elles sont deja dans
 * `a_envoyer_a`. Ce decoupage est ce qui rend l'ensemble verifiable.
 */

import { clientService, reponse } from "../_partage/commun.ts";

/** Au-dela, on abandonne : un jeton revoque boucle sinon pour toujours. */
const ECHECS_MAX = 3;

/** Combien on en traite par passage. Cinq minutes suffisent largement. */
const PAR_PASSAGE = 200;

/**
 * Le jeton d'acces Firebase, obtenu depuis le compte de service.
 *
 * FCM v1 exige OAuth2 ; l'ancienne cle serveur est fermee depuis 2024.
 * On signe un JWT nous-memes plutot que d'embarquer une bibliotheque
 * Google : trois appels de `crypto.subtle`, et rien a maintenir.
 */
async function jetonGoogle(): Promise<string> {
  const compte = JSON.parse(Deno.env.get("FIREBASE_SERVICE_ACCOUNT")!);
  const maintenant = Math.floor(Date.now() / 1000);

  const entete = { alg: "RS256", typ: "JWT" };
  const charge = {
    iss: compte.client_email,
    scope: "https://www.googleapis.com/auth/firebase.messaging",
    aud: "https://oauth2.googleapis.com/token",
    iat: maintenant,
    exp: maintenant + 3600,
  };

  const b64 = (o: unknown) =>
    btoa(JSON.stringify(o)).replace(/\+/g, "-").replace(/\//g, "_")
      .replace(/=+$/, "");
  const aSigner = `${b64(entete)}.${b64(charge)}`;

  const pem = compte.private_key
    .replace(/-----(BEGIN|END) PRIVATE KEY-----/g, "").replace(/\s/g, "");
  const cle = await crypto.subtle.importKey(
    "pkcs8",
    Uint8Array.from(atob(pem), (c) => c.charCodeAt(0)),
    { name: "RSASSA-PKCS1-v1_5", hash: "SHA-256" },
    false, ["sign"],
  );
  const signature = await crypto.subtle.sign(
    "RSASSA-PKCS1-v1_5", cle, new TextEncoder().encode(aSigner));
  const jwt = `${aSigner}.${
    btoa(String.fromCharCode(...new Uint8Array(signature)))
      .replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "")}`;

  const rep = await fetch("https://oauth2.googleapis.com/token", {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body: new URLSearchParams({
      grant_type: "urn:ietf:params:oauth:grant-type:jwt-bearer",
      assertion: jwt,
    }),
  });
  const corps = await rep.json();
  if (!rep.ok) throw new Error(`OAuth Google : ${JSON.stringify(corps)}`);
  return corps.access_token;
}

Deno.serve(async (requete) => {
  const secret = requete.headers.get("x-eve-cron") ?? "";
  if (secret !== Deno.env.get("EVE_CRON_SECRET")) {
    return reponse({ error: "non autorise" }, 401);
  }

  const service = clientService();
  const { data: attente } = await service
    .from("notifications")
    .select("id, user_id, title, body, echecs")
    .is("envoye_a", null)
    .eq("abandonne", false)
    .lte("a_envoyer_a", new Date().toISOString())
    .order("a_envoyer_a", { ascending: true })
    .limit(PAR_PASSAGE);

  const lignes = attente ?? [];
  if (lignes.length === 0) return reponse({ envoyes: 0 });

  // Les jetons en un seul appel : une requete par notification
  // multiplierait les allers-retours pour rien.
  const { data: profils } = await service
    .from("profiles")
    .select("id, push_token")
    .in("id", [...new Set(lignes.map((l) => l.user_id))]);
  const jetons = new Map(
    (profils ?? []).map((p) => [p.id, p.push_token as string | null]));

  const projet = JSON.parse(Deno.env.get("FIREBASE_SERVICE_ACCOUNT")!).project_id;
  const acces = await jetonGoogle();
  let envoyes = 0, echoues = 0, sansJeton = 0;

  for (const ligne of lignes) {
    const jeton = jetons.get(ligne.user_id);
    if (!jeton) {
      // Pas de jeton : la ligne est close, pas retentee. L'utilisateur
      // a desinstalle ou refuse les notifications.
      await service.from("notifications")
        .update({ abandonne: true }).eq("id", ligne.id);
      sansJeton += 1;
      continue;
    }

    try {
      const rep = await fetch(
        `https://fcm.googleapis.com/v1/projects/${projet}/messages:send`,
        {
          method: "POST",
          headers: {
            Authorization: `Bearer ${acces}`,
            "Content-Type": "application/json",
          },
          body: JSON.stringify({
            message: {
              token: jeton,
              notification: { title: ligne.title, body: ligne.body },
              android: { priority: "high" },
            },
          }),
        },
      );

      if (rep.ok) {
        await service.from("notifications")
          .update({ envoye_a: new Date().toISOString() }).eq("id", ligne.id);
        envoyes += 1;
      } else {
        const detail = await rep.text();
        // 404 / UNREGISTERED : le jeton est mort. On le retire du profil
        // pour ne pas reessayer a chaque passage sur chaque notification.
        if (rep.status === 404 || detail.includes("UNREGISTERED")) {
          await service.from("profiles")
            .update({ push_token: null }).eq("id", ligne.user_id);
          await service.from("notifications")
            .update({ abandonne: true }).eq("id", ligne.id);
        } else {
          const echecs = (ligne.echecs ?? 0) + 1;
          await service.from("notifications").update({
            echecs, abandonne: echecs >= ECHECS_MAX,
          }).eq("id", ligne.id);
        }
        echoues += 1;
      }
    } catch (e) {
      console.error("envoi :", e);
      const echecs = (ligne.echecs ?? 0) + 1;
      await service.from("notifications").update({
        echecs, abandonne: echecs >= ECHECS_MAX,
      }).eq("id", ligne.id);
      echoues += 1;
    }
  }

  return reponse({ envoyes, echoues, sansJeton });
});
