package fr.allure.alluxebot

import com.facebook.react.ReactPackage
import com.facebook.react.bridge.NativeModule
import com.facebook.react.bridge.ReactApplicationContext
import com.facebook.react.uimanager.ViewManager

class ReveilVocalPackage : ReactPackage {
    override fun createNativeModules(contexte: ReactApplicationContext): List<NativeModule> {
        return listOf(ReveilVocalModule(contexte))
    }

    override fun createViewManagers(
        contexte: ReactApplicationContext
    ): List<ViewManager<*, *>> = emptyList()
}
