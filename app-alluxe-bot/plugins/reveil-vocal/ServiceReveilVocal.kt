package fr.allure.alluxebot

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.Intent
import android.net.Uri
import android.os.Build
import android.os.IBinder
import android.util.Log
import ai.picovoice.porcupine.PorcupineManager
import ai.picovoice.porcupine.PorcupineManagerCallback

/**
 * Service permanent qui ecoute le mot de reveil "Alluxe" en arriere-plan
 * (meme application fermee) et ouvre l'application quand il l'entend.
 *
 * PREMIERE VERSION (16 sept.) -- voir memoire "reveil-vocal-alluxe" pour
 * le contexte complet. Ne fait qu'ecouter et ouvrir l'app : la suite de
 * la conversation (dicter la question, entendre la reponse) se passe
 * cote React Native (voir Agent.tsx, expo-speech-recognition + expo-speech).
 *
 * Necessite un fichier de mot-cle Porcupine ("alluxe_android.ppn",
 * genere sur console.picovoice.ai) dans assets/reveil/, et une cle
 * d'acces Picovoice injectee par le plugin Expo dans R.string.picovoice_access_key.
 * Sans l'un ou l'autre, le service s'arrete tout seul en le signalant
 * dans le journal Android -- il ne fait jamais planter l'application.
 */
class ServiceReveilVocal : Service(), PorcupineManagerCallback {

    companion object {
        private const val TAG = "ReveilVocalAlluxe"
        private const val CANAL_NOTIF = "reveil_vocal_alluxe"
        private const val ID_NOTIF = 4242
        private const val CHEMIN_MOT_CLE = "reveil/alluxe_android.ppn"

        // Lu depuis n'importe ou dans le process (le module React Native
        // le lit pour repondre a estActif() sans passer par une
        // communication inter-process).
        @Volatile
        @JvmStatic
        var actif: Boolean = false
            private set
    }

    private var manager: PorcupineManager? = null

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        demarrerEcoute()
        return START_STICKY
    }

    override fun onDestroy() {
        arreterEcoute()
        super.onDestroy()
    }

    private fun demarrerEcoute() {
        if (manager != null) return  // deja en ecoute

        val cle = getString(
            resources.getIdentifier("picovoice_access_key", "string", packageName)
        )
        if (cle.isBlank()) {
            Log.w(TAG, "cle d'acces Picovoice absente -- reveil vocal desactive")
            stopSelf()
            return
        }

        val cheminMotCle = copierMotCleDepuisAssets()
        if (cheminMotCle == null) {
            Log.w(TAG, "fichier de mot-cle ($CHEMIN_MOT_CLE) absent -- reveil vocal desactive")
            stopSelf()
            return
        }

        try {
            demarrerAuPremierPlan()
            manager = PorcupineManager.Builder()
                .setAccessKey(cle)
                .setKeywordPath(cheminMotCle)
                .setSensitivity(0.6f)
                .build(applicationContext, this)
            manager?.start()
            actif = true
            Log.i(TAG, "reveil vocal actif, en ecoute de \"Alluxe\"")
        } catch (e: Exception) {
            Log.e(TAG, "impossible de demarrer Porcupine : ${e.message}", e)
            actif = false
            stopSelf()
        }
    }

    private fun arreterEcoute() {
        try {
            manager?.stop()
            manager?.delete()
        } catch (e: Exception) {
            Log.w(TAG, "arret de Porcupine : ${e.message}")
        }
        manager = null
        actif = false
    }

    /** Porcupine veut un chemin de fichier reel, pas un flux d'assets --
     * on le copie une fois dans le stockage prive de l'app. */
    private fun copierMotCleDepuisAssets(): String? {
        return try {
            val fichier = java.io.File(filesDir, "alluxe_android.ppn")
            if (!fichier.exists()) {
                assets.open(CHEMIN_MOT_CLE).use { entree ->
                    fichier.outputStream().use { sortie -> entree.copyTo(sortie) }
                }
            }
            fichier.absolutePath
        } catch (e: java.io.IOException) {
            null
        }
    }

    private fun demarrerAuPremierPlan() {
        val gestionnaire = getSystemService(NotificationManager::class.java)
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            val canal = NotificationChannel(
                CANAL_NOTIF, "Reveil vocal Alluxe", NotificationManager.IMPORTANCE_MIN
            )
            gestionnaire.createNotificationChannel(canal)
        }
        val notification: Notification = Notification.Builder(this, CANAL_NOTIF)
            .setContentTitle("Alluxe ecoute")
            .setContentText("Dis \"Alluxe\" pour lui parler")
            .setSmallIcon(applicationInfo.icon)
            .setOngoing(true)
            .build()
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
            startForeground(
                ID_NOTIF, notification,
                android.content.pm.ServiceInfo.FOREGROUND_SERVICE_TYPE_MICROPHONE
            )
        } else {
            startForeground(ID_NOTIF, notification)
        }
    }

    /** Callback Porcupine : le mot de reveil vient d'etre entendu. */
    override fun invoke(keywordIndex: Int) {
        try {
            val intention = Intent(Intent.ACTION_VIEW, Uri.parse("alluxebot://reveil"))
            intention.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
            startActivity(intention)
        } catch (e: Exception) {
            Log.e(TAG, "ouverture de l'application apres reveil : ${e.message}", e)
        }
    }
}
