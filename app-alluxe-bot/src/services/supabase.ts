/**
 * Le client Supabase de l'application.
 *
 * IL N'UTILISE QUE LA CLE ANONYME. Elle est publique par construction :
 * elle part dans l'APK, et n'importe qui peut l'extraire. C'est prevu —
 * la Row Level Security decide de ce qu'elle donne.
 *
 * La cle `service_role`, elle, CONTOURNE la RLS. Placee ici, elle
 * donnerait a chaque utilisateur la base entiere : tous les profils,
 * tous les signaux payants, toutes les adresses e-mail. Elle ne vit que
 * dans les fonctions Edge, cote serveur.
 */

import AsyncStorage from "@react-native-async-storage/async-storage";
import Constants from "expo-constants";
import { createClient } from "@supabase/supabase-js";
import "react-native-url-polyfill/auto";

const extra = (Constants.expoConfig?.extra ?? {}) as Record<string, string>;

export const supabase = createClient(
  extra.supabaseUrl,
  extra.supabaseAnonKey,
  {
    auth: {
      storage: AsyncStorage,
      autoRefreshToken: true,
      persistSession: true,
      // Une application mobile n'a pas d'URL : le retour du lien magique
      // passe par le schema `allure://`, gere a la main dans App.tsx.
      detectSessionInUrl: false,
    },
  },
);
