/**
 * Onglet Compte -- segment Profil.
 *
 * Retour reel du 14 sept. : « dans l'espace compte, fais des onglets au
 * lieu de montrer que l'abonnement, tu mets profil, et tout les autres
 * onglets ainsi que a propos et contact ». Le capital declaratif et les
 * notifications, personnels a l'utilisateur, rejoignent ce segment
 * plutot que de rester noyes au milieu de l'abonnement.
 */

import React from "react";
import { Pressable, ScrollView, Switch, TextInput, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { CAPITAL_DEFAUT, enregistrerCapital, useCapital }
  from "../services/reglages";
import { supabase } from "../services/supabase";
import { euros } from "../services/format";
import { espace, rayon } from "../theme";
import { Carte, Etiquette, Separateur, T, useCouleurs } from "../composants/base";

function LigneReglage({ titre, detail, valeur, onChange }: {
  titre: string; detail?: string; valeur: boolean;
  onChange: (v: boolean) => void;
}) {
  const c = useCouleurs();
  return (
    <View style={{ flexDirection: "row", alignItems: "center",
                   paddingVertical: espace.m }}>
      <View style={{ flex: 1, paddingRight: espace.l }}>
        <T v="corps">{titre}</T>
        {detail ? <T v="petit" style={{ marginTop: 2 }}>{detail}</T> : null}
      </View>
      <Switch value={valeur} onValueChange={onChange}
              trackColor={{ true: c.jaune, false: c.creux }}
              thumbColor={c.surface} />
    </View>
  );
}

export function EcranProfil({ email, onRetour }: {
  email: string; onRetour: () => void;
}) {
  const c = useCouleurs();
  const marges = useSafeAreaInsets();
  const capitalEnregistre = useCapital();

  const [pseudo, setPseudo] = React.useState("");
  const [bio, setBio] = React.useState("");
  const [bioEnregistree, setBioEnregistree] = React.useState("");
  const [capital, setCapital] = React.useState(String(CAPITAL_DEFAUT));
  const [signaux, setSignaux] = React.useState(true);
  const [macro, setMacro] = React.useState(true);

  React.useEffect(() => { setCapital(String(capitalEnregistre)); },
                  [capitalEnregistre]);

  React.useEffect(() => {
    supabase.auth.getSession().then(async ({ data }) => {
      const id = data.session?.user?.id;
      if (!id) return;
      const { data: p } = await supabase
        .from("profiles")
        .select("pseudo, bio, notif_signals, notif_macro")
        .eq("id", id).single();
      if (p) {
        setPseudo(p.pseudo ?? "");
        setBio(p.bio ?? ""); setBioEnregistree(p.bio ?? "");
        setSignaux(p.notif_signals); setMacro(p.notif_macro);
      }
    });
  }, []);

  async function enregistrerBio() {
    if (bio === bioEnregistree) return;
    const { data } = await supabase.auth.getSession();
    const id = data.session?.user?.id;
    if (!id) return;
    await supabase.from("profiles").update({ bio: bio || null }).eq("id", id);
    setBioEnregistree(bio);
  }

  async function majNotif(champ: "notif_signals" | "notif_macro", v: boolean) {
    const { data } = await supabase.auth.getSession();
    const id = data.session?.user?.id;
    if (id) await supabase.from("profiles").update({ [champ]: v }).eq("id", id);
  }

  return (
    <ScrollView
      style={{ backgroundColor: c.fond }}
      contentContainerStyle={{
        padding: espace.l, paddingTop: marges.top + espace.m,
        paddingBottom: marges.bottom + espace.xxxl,
      }}
    >
      <Pressable onPress={onRetour} style={{ marginBottom: espace.l }}>
        <T v="sousTitre" couleur={c.encreDouce}>‹ Retour</T>
      </Pressable>

      <Carte>
        <Etiquette>{pseudo || "Ton profil"}</Etiquette>
        <T v="petit" style={{ marginTop: 2 }}>{email}</T>
        <T v="etiquette" style={{ marginTop: espace.l, marginBottom: espace.s }}>
          Presentation (visible sur la Communaute)
        </T>
        <TextInput
          value={bio}
          onChangeText={setBio}
          onEndEditing={enregistrerBio}
          placeholder="Quelques mots sur toi..."
          placeholderTextColor={c.encrePale}
          maxLength={280}
          multiline
          style={{
            backgroundColor: c.creux, color: c.encre, borderRadius: rayon.s,
            paddingHorizontal: espace.m, paddingVertical: espace.m,
            fontSize: 15, minHeight: 70, textAlignVertical: "top",
          }}
        />
      </Carte>

      <Carte style={{ marginTop: espace.l }}>
        <Etiquette>Ton capital</Etiquette>
        <T v="petit" style={{ marginTop: espace.s }}>
          Sert uniquement a te dire, sur chaque signal, ce que la position
          peut te couter en euros. Ce chiffre reste sur ton telephone : il
          n'est envoye nulle part.
        </T>
        <View style={{ flexDirection: "row", alignItems: "center",
                       marginTop: espace.m }}>
          <TextInput
            value={capital}
            onChangeText={setCapital}
            onEndEditing={() => enregistrerCapital(Number(capital))}
            keyboardType="numeric"
            style={{
              flex: 1, backgroundColor: c.creux, color: c.encre,
              borderRadius: rayon.s, paddingHorizontal: espace.m,
              paddingVertical: espace.m, fontSize: 17,
              fontVariant: ["tabular-nums"],
            }}
            placeholderTextColor={c.encrePale}
          />
          <T v="sousTitre" style={{ marginLeft: espace.m }}>€</T>
        </View>
        <T v="legende" style={{ marginTop: espace.s }}>
          Exemple : sur {euros(Number(capital) || CAPITAL_DEFAUT, 0)}, un
          signal a 0,6 % risque {euros((Number(capital) || CAPITAL_DEFAUT)
            * 0.006)}.
        </T>
      </Carte>

      <Carte style={{ marginTop: espace.l }}>
        <Etiquette style={{ marginBottom: espace.s }}>Notifications</Etiquette>
        <LigneReglage
          titre="Nouveaux signaux" valeur={signaux}
          onChange={(v) => { setSignaux(v); majNotif("notif_signals", v); }}
        />
        <Separateur />
        <LigneReglage
          titre="Annonces economiques"
          detail="Quinze minutes avant les plus importantes"
          valeur={macro}
          onChange={(v) => { setMacro(v); majNotif("notif_macro", v); }}
        />
        <Separateur />
        <T v="legende" style={{ marginTop: espace.m, lineHeight: 16 }}>
          Rien n'est envoye entre 23 h et 7 h, heure de chez toi.
        </T>
      </Carte>

      <T v="corps" couleur={c.perte}
         style={{ marginTop: espace.xxl, textAlign: "center" }}
         onPress={() => supabase.auth.signOut()}>
        Se deconnecter
      </T>
    </ScrollView>
  );
}
