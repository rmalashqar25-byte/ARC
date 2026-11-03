package com.example.arc

import android.accessibilityservice.AccessibilityServiceInfo
import android.content.ComponentName
import android.content.Context
import android.content.Intent
import android.net.Uri
import android.provider.Settings
import android.view.accessibility.AccessibilityManager
import io.flutter.embedding.android.FlutterActivity
import io.flutter.embedding.engine.FlutterEngine
import io.flutter.plugin.common.MethodChannel

class MainActivity : FlutterActivity() {
    private val channelName = "arc/accessibility"

    override fun configureFlutterEngine(flutterEngine: FlutterEngine) {
        super.configureFlutterEngine(flutterEngine)

        MethodChannel(
            flutterEngine.dartExecutor.binaryMessenger,
            channelName,
        ).setMethodCallHandler { call, result ->
            when (call.method) {
                "isAccessibilityEnabled" -> result.success(isAccessibilityEnabled())
                "openAccessibilitySettings" -> {
                    val component = ComponentName(this, ArcAccessibilityService::class.java)
                    val detailsIntent = Intent("android.settings.ACCESSIBILITY_DETAILS_SETTINGS").apply {
                        data = Uri.parse("package:${component.flattenToString()}")
                    }
                    runCatching { startActivity(detailsIntent) }
                        .onFailure {
                            startActivity(Intent(Settings.ACTION_ACCESSIBILITY_SETTINGS))
                        }
                    result.success(true)
                }
                "executeActions" -> {
                    val rawActions = call.arguments as? List<*>
                    val actions = rawActions
                        ?.mapNotNull { item ->
                            @Suppress("UNCHECKED_CAST")
                            item as? Map<String, Any?>
                        }
                        ?.take(30)
                        ?: emptyList()

                    if (actions.isEmpty()) {
                        result.error("INVALID_ACTIONS", "No Android actions were supplied", null)
                        return@setMethodCallHandler
                    }

                    val service = ArcAccessibilityService.activeInstance
                    if (service == null) {
                        result.error(
                            "SERVICE_DISABLED",
                            "Enable ARC App Control in Android Accessibility settings",
                            null,
                        )
                        return@setMethodCallHandler
                    }

                    service.executeActions(actions) { actionResults ->
                        runOnUiThread {
                            result.success(
                                mapOf(
                                    "success" to actionResults.all { it["success"] == true },
                                    "results" to actionResults,
                                ),
                            )
                        }
                    }
                }
                else -> result.notImplemented()
            }
        }
    }

    private fun isAccessibilityEnabled(): Boolean {
        val manager = getSystemService(Context.ACCESSIBILITY_SERVICE) as AccessibilityManager
        return manager
            .getEnabledAccessibilityServiceList(AccessibilityServiceInfo.FEEDBACK_ALL_MASK)
            .any { info ->
                val serviceInfo = info.resolveInfo.serviceInfo
                serviceInfo.packageName == packageName &&
                    serviceInfo.name == ArcAccessibilityService::class.java.name
            }
    }
}
