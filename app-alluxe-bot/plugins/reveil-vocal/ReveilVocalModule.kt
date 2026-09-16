package fr.allure.alluxebot

import android.content.Intent
import com.facebook.react.bridge.Promise
import com.facebook.react.bridge.ReactApplicationContext
import com.facebook.react.bridge.ReactContextBaseJavaModule
import com.facebook.react.bridge.ReactMethod

/**
 * Pont JS <-> ServiceReveilVocal. Trois methodes, rien de plus : le
 * reveil vocal ne fait qu'ecouter et ouvrir l'app (voir ServiceReveilVocal.kt) --
 * aucune methode d'action ici, conformement a la version 1 de l'agent
 * Alluxe (lecture seule).
 */
class ReveilVocalModule(private val contexte: ReactApplicationContext) :
    ReactContextBaseJavaModule(contexte) {

    override fun getName(): String = "ReveilVocal"

    @ReactMethod
    fun demarrer(promesse: Promise) {
        try {
            val intention = Intent(contexte, ServiceReveilVocal::class.java)
            contexte.startForegroundService(intention)
            promesse.resolve(true)
        } catch (e: Exception) {
            promesse.reject("reveil_vocal_demarrage", e.message, e)
        }
    }

    @ReactMethod
    fun arreter(promesse: Promise) {
        try {
            contexte.stopService(Intent(contexte, ServiceReveilVocal::class.java))
            promesse.resolve(true)
        } catch (e: Exception) {
            promesse.reject("reveil_vocal_arret", e.message, e)
        }
    }

    @ReactMethod
    fun estActif(promesse: Promise) {
        promesse.resolve(ServiceReveilVocal.actif)
    }
}
