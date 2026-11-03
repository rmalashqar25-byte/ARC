package com.example.arc

import android.accessibilityservice.AccessibilityService
import android.accessibilityservice.GestureDescription
import android.content.Intent
import android.graphics.Path
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.view.accessibility.AccessibilityEvent
import android.view.accessibility.AccessibilityNodeInfo

class ArcAccessibilityService : AccessibilityService() {
    companion object {
        @Volatile
        var activeInstance: ArcAccessibilityService? = null
            private set
    }

    private val mainHandler = Handler(Looper.getMainLooper())

    override fun onServiceConnected() {
        super.onServiceConnected()
        activeInstance = this
    }

    override fun onDestroy() {
        if (activeInstance === this) activeInstance = null
        super.onDestroy()
    }

    override fun onAccessibilityEvent(event: AccessibilityEvent?) = Unit

    override fun onInterrupt() = Unit

    fun executeActions(
        actions: List<Map<String, Any?>>,
        completion: (List<Map<String, Any?>>) -> Unit,
    ) {
        val results = mutableListOf<Map<String, Any?>>()
        executeNext(actions, 0, results, completion)
    }

    private fun executeNext(
        actions: List<Map<String, Any?>>,
        index: Int,
        results: MutableList<Map<String, Any?>>,
        completion: (List<Map<String, Any?>>) -> Unit,
    ) {
        if (index >= actions.size) {
            completion(results)
            return
        }

        val action = actions[index]
        val actionName = action["action"]?.toString().orEmpty()
        val outcome = runCatching { executeAction(actionName, action) }
            .fold(
                onSuccess = { success ->
                    mapOf(
                        "action" to actionName,
                        "success" to success,
                        "message" to if (success) "Completed" else "Target was not available",
                    )
                },
                onFailure = { error ->
                    mapOf(
                        "action" to actionName,
                        "success" to false,
                        "message" to (error.message ?: "Action failed"),
                    )
                },
            )
        results.add(outcome)

        val delay = if (actionName == "wait") {
            (action["duration_ms"] as? Number)?.toLong()?.coerceIn(100L, 10_000L) ?: 1_000L
        } else {
            700L
        }
        mainHandler.postDelayed(
            { executeNext(actions, index + 1, results, completion) },
            delay,
        )
    }

    private fun executeAction(actionName: String, action: Map<String, Any?>): Boolean {
        return when (actionName) {
            "open_app" -> openApp(action["app"]?.toString().orEmpty())
            "tap_text" -> tapText(action["text"]?.toString().orEmpty())
            "tap_coordinates" -> tapCoordinates(
                (action["x"] as? Number)?.toFloat() ?: 0f,
                (action["y"] as? Number)?.toFloat() ?: 0f,
            )
            "input_text" -> inputText(action["text"]?.toString().orEmpty())
            "scroll" -> scroll(action["direction"]?.toString() ?: "down")
            "back" -> performGlobalAction(GLOBAL_ACTION_BACK)
            "home" -> performGlobalAction(GLOBAL_ACTION_HOME)
            "recents" -> performGlobalAction(GLOBAL_ACTION_RECENTS)
            "wait" -> true
            else -> false
        }
    }

    private fun openApp(appNameOrPackage: String): Boolean {
        val target = appNameOrPackage.trim()
        if (target.isEmpty()) return false

        var launchIntent = packageManager.getLaunchIntentForPackage(target)
        if (launchIntent == null) {
            val launcherQuery = Intent(Intent.ACTION_MAIN).apply {
                addCategory(Intent.CATEGORY_LAUNCHER)
            }
            val match = packageManager.queryIntentActivities(launcherQuery, 0)
                .firstOrNull { resolveInfo ->
                    val label = resolveInfo.loadLabel(packageManager).toString()
                    val packageName = resolveInfo.activityInfo.packageName
                    label.equals(target, ignoreCase = true) ||
                        packageName.equals(target, ignoreCase = true) ||
                        label.contains(target, ignoreCase = true)
                }
            if (match != null) {
                launchIntent = packageManager.getLaunchIntentForPackage(
                    match.activityInfo.packageName,
                )
            }
        }

        launchIntent ?: return false
        launchIntent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
        startActivity(launchIntent)
        return true
    }

    private fun tapText(targetText: String): Boolean {
        val root = rootInActiveWindow ?: return false
        val matches = root.findAccessibilityNodeInfosByText(targetText)
        val preferred = matches.firstOrNull { node ->
            node.text?.toString().equals(targetText, ignoreCase = true) ||
                node.contentDescription?.toString().equals(targetText, ignoreCase = true)
        } ?: matches.firstOrNull() ?: return false

        var clickable: AccessibilityNodeInfo? = preferred
        repeat(10) {
            if (clickable?.isClickable == true) {
                return clickable?.performAction(AccessibilityNodeInfo.ACTION_CLICK) == true
            }
            clickable = clickable?.parent
        }
        return false
    }

    private fun inputText(text: String): Boolean {
        val root = rootInActiveWindow ?: return false
        val target = root.findFocus(AccessibilityNodeInfo.FOCUS_INPUT)
            ?.takeIf { it.isEditable }
            ?: findNode(root) { it.isEditable }
            ?: return false

        if (target.isPassword) return false
        val arguments = Bundle().apply {
            putCharSequence(
                AccessibilityNodeInfo.ACTION_ARGUMENT_SET_TEXT_CHARSEQUENCE,
                text.take(1000),
            )
        }
        return target.performAction(AccessibilityNodeInfo.ACTION_SET_TEXT, arguments)
    }

    private fun scroll(direction: String): Boolean {
        val root = rootInActiveWindow ?: return false
        val scrollable = findNode(root) { it.isScrollable } ?: return false
        val action = if (direction.equals("up", ignoreCase = true)) {
            AccessibilityNodeInfo.ACTION_SCROLL_BACKWARD
        } else {
            AccessibilityNodeInfo.ACTION_SCROLL_FORWARD
        }
        return scrollable.performAction(action)
    }

    private fun tapCoordinates(x: Float, y: Float): Boolean {
        val path = Path().apply { moveTo(x.coerceAtLeast(0f), y.coerceAtLeast(0f)) }
        val gesture = GestureDescription.Builder()
            .addStroke(GestureDescription.StrokeDescription(path, 0, 80))
            .build()
        return dispatchGesture(gesture, null, null)
    }

    private fun findNode(
        root: AccessibilityNodeInfo,
        predicate: (AccessibilityNodeInfo) -> Boolean,
    ): AccessibilityNodeInfo? {
        val queue = ArrayDeque<AccessibilityNodeInfo>()
        queue.add(root)
        var visited = 0
        while (queue.isNotEmpty() && visited < 2_000) {
            val node = queue.removeFirst()
            visited += 1
            if (predicate(node)) return node
            for (index in 0 until node.childCount) {
                node.getChild(index)?.let(queue::addLast)
            }
        }
        return null
    }
}
