import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import HAgent

// Responsive desktop shell with a draggable sidebar divider.
// `controller` and `chatModel` are injected as context properties from Python.
Rectangle {
    id: root
    color: Theme.bg
    implicitWidth: 420
    implicitHeight: 760
    readonly property bool wide: width >= Theme.fs(880)
    property bool sidebarExpanded: wide
    onWideChanged: sidebarExpanded = wide
    property real sidebarWidth: 236 // logical pixels; follows the UI font scale
    readonly property real minimumNavigationWidth: Math.min(Theme.fs(160), width * 0.35)
    readonly property real maximumNavigationWidth: Math.max(minimumNavigationWidth,
        Math.min(Theme.fs(420), width - Math.min(Theme.fs(280), width * 0.6) - Theme.fs(6)))
    readonly property real navigationWidth: Math.max(minimumNavigationWidth,
        Math.min(Theme.fs(sidebarWidth), maximumNavigationWidth))
    function resizeNavigation(value) {
        if (value < Theme.fs(72)) {
            sidebarExpanded = false
            return
        }
        sidebarWidth = Math.max(minimumNavigationWidth, Math.min(value, maximumNavigationWidth)) / Theme.scale
        sidebarExpanded = true
    }
    function toggleNavigation() {
        sidebarExpanded = !sidebarExpanded
    }
    // Python Panel（pane.py）在 tab 被激活时调用，让键盘焦点落在输入框
    function focusComposer() {
        if (composer) composer.focusInput()
    }
    // 兜底：面板里没有任何输入控件持有焦点时，可打印字符直接送进输入框
    // （Houdini pane 里个别情况下点击输入框不会把 QML 焦点切过去）
    focus: true
    Keys.priority: Keys.BeforeItem
    Keys.onPressed: function(event) {
        if (!event.text || event.text.length === 0) return
        var code = event.text.charCodeAt(0)
        if (code < 0x20 || code === 0x7f) return              // 退格/回车/控制字符不兜底
        if (event.modifiers & (Qt.ControlModifier | Qt.AltModifier | Qt.MetaModifier)) return
        var focused = Window.activeFocusItem
        if (focused && focused.text !== undefined) return   // 文本输入/按钮自己处理
        if (!composer) return
        composer.focusInput()
        composer.insertText(event.text)
        event.accepted = true
    }
    // QML Shortcut 不支持 WidgetShortcut 的焦点匹配。面板宿主显式告知键盘焦点，
    // 在保留 WindowShortcut 的同时避免抢走 Houdini 其它 pane 的 Ctrl+N 等快捷键。
    property bool embedded: false
    property bool embeddedFocus: false
    readonly property bool shortcutsEnabled: !embedded || embeddedFocus
    Shortcut { sequence: "Ctrl+N"; context: Qt.WindowShortcut; enabled: root.shortcutsEnabled; onActivated: if (controller) controller.newSession() }
    Shortcut { sequence: "Ctrl+B"; context: Qt.WindowShortcut; enabled: root.shortcutsEnabled; onActivated: root.toggleNavigation() }
    Shortcut { sequence: "Ctrl+,"; context: Qt.WindowShortcut; enabled: root.shortcutsEnabled; onActivated: if (controller) controller.menuAction("settings") }

    // 外观状态（字号 / 主题 / 强调色 / 字体方案 / 密度）驱动 Theme 单例换肤
    function applyAppearance() {
        if (!controller) return
        Theme.scale = controller.fontScale
        Theme.mode = controller.appTheme
        Theme.accentKey = controller.accentKey
        Theme.typeKey = controller.fontFamilyKey
        Theme.densityKey = controller.densityKey
    }
    Component.onCompleted: applyAppearance()
    Connections {
        target: controller
        ignoreUnknownSignals: true
        function onFontScaleChanged() { if (controller) Theme.scale = controller.fontScale }
        function onAppearanceChanged() { root.applyAppearance() }
    }

    RowLayout {
        anchors.fill: parent
        spacing: 0
        Sidebar {
            objectName: "dockedSidebar"
            visible: root.sidebarExpanded
            Layout.preferredWidth: root.navigationWidth
            Layout.minimumWidth: root.navigationWidth
            Layout.maximumWidth: root.navigationWidth
            Layout.fillHeight: true
            onNavigated: if (!root.wide) root.sidebarExpanded = false
        }
        Rectangle {
            id: divider
            objectName: "sidebarResizeHandle"
            Layout.preferredWidth: Theme.fs(6)
            Layout.fillHeight: true
            color: "transparent"
            activeFocusOnTab: true
            Accessible.role: Accessible.Slider
            Accessible.name: controller && controller.lang === "en" ? "Sidebar width" : "侧栏宽度"
            Keys.onLeftPressed: root.resizeNavigation((root.sidebarExpanded ? root.navigationWidth : 0) - Theme.fs(24))
            Keys.onRightPressed: root.resizeNavigation((root.sidebarExpanded ? root.navigationWidth : 0) + Theme.fs(80))
            Rectangle {
                anchors.centerIn: parent; width: 1; height: parent.height
                visible: dragArea.pressed
                color: Theme.border
            }
            MouseArea {
                id: dragArea
                anchors.fill: parent
                hoverEnabled: true
                cursorShape: Qt.SplitHCursor
                property real startX: 0
                property real startWidth: 0
                onPressed: function(mouse) {
                    startX = mapToItem(root, mouse.x, mouse.y).x
                    startWidth = root.sidebarExpanded ? root.navigationWidth : 0
                }
                onPositionChanged: function(mouse) {
                    if (pressed) root.resizeNavigation(startWidth + mapToItem(root, mouse.x, mouse.y).x - startX)
                }
                onDoubleClicked: { root.sidebarWidth = 236; root.sidebarExpanded = true }
            }
        }
        ColumnLayout {
            id: conversationPane
            objectName: "conversationPane"
            Layout.fillWidth: true
            Layout.minimumWidth: 0
            Layout.fillHeight: true
            clip: true
            spacing: 0
            Header {
                id: conversationHeader
                Layout.fillWidth: true
            }

            ChatView {
                id: conversationView
                objectName: "chatViewport"
                Layout.fillWidth: true
                Layout.fillHeight: true
            }

            ContextBar {
                id: sceneContextBar
                Layout.fillWidth: true
                Layout.maximumWidth: Theme.contentMaxWidth + Theme.sp(16) * 2
                Layout.rightMargin: conversationView.navigationGutter
                Layout.alignment: Qt.AlignHCenter
            }
            Composer {
                id: composer
                objectName: "composer"
                Layout.fillWidth: true
                Layout.maximumWidth: Theme.contentMaxWidth + Theme.sp(16) * 2
                Layout.rightMargin: conversationView.navigationGutter
                Layout.alignment: Qt.AlignHCenter
                availableHeightBudget: Math.max(0, conversationPane.height - conversationHeader.implicitHeight
                    - sceneContextBar.implicitHeight)
            }
        }
    }

    // Meshy 资产库浮层抽屉：向内叠在聊天之上；未被面板覆盖处用半透明磨砂遮罩盖住，点遮罩关闭。
    Item {
        id: libOverlay
        anchors.fill: parent
        z: 90
        property bool open: controller ? controller.libraryOpen : false
        visible: open || scrim.opacity > 0.001

        // 磨砂遮罩：半透明盖住未被面板覆盖的区域，点击关闭
        Rectangle {
            id: scrim
            anchors.fill: parent
            color: Qt.rgba(0.05, 0.05, 0.06, 0.55)
            opacity: libOverlay.open ? 1 : 0
            Behavior on opacity { NumberAnimation { duration: 200; easing.type: Easing.OutCubic } }
            MouseArea {
                anchors.fill: parent
                onClicked: if (controller) controller.setLibraryOpen(false)
            }
        }

        // 抽屉面板：从左侧滑入，叠在聊天上方（不挤占窗口）
        Rectangle {
            id: libDrawer
            width: Math.min(360, libOverlay.width * 0.88)
            height: parent.height
            color: Theme.bg
            radius: Theme.radMd
            x: libOverlay.open ? 0 : -width - 2
            Behavior on x { NumberAnimation { duration: 220; easing.type: Easing.OutCubic } }
            LibraryContent { anchors.fill: parent }
        }
    }

    // transient toast
    Rectangle {
        id: toast
        z: 100
        anchors.horizontalCenter: parent.horizontalCenter
        anchors.bottom: parent.bottom; anchors.bottomMargin: 96
        visible: opacity > 0
        opacity: 0
        width: toastText.implicitWidth + 26
        height: toastText.implicitHeight + 16
        color: Theme.surface2
        border.color: Theme.border; border.width: 1; radius: Theme.radSm
        Behavior on opacity { NumberAnimation { duration: 200 } }
        Text {
            id: toastText
            anchors.centerIn: parent
            color: Theme.textBright
            font.family: Theme.fontBody; font.pixelSize: Theme.fSm
        }
        Timer { id: toastTimer; interval: 2200; onTriggered: toast.opacity = 0 }
        Connections {
            target: controller
            ignoreUnknownSignals: true
            function onToast(msg) { toastText.text = msg; toast.opacity = 1; toastTimer.restart() }
        }
    }

    FontPopup { id: fontPopup }
    TokenPopup { id: tokenPopup }
    ActionDialog { id: actionDialog }
    ActionDialog { id: infoDialog; objectName: "infoDialog" }
    SubscriptionDialog { id: subscriptionDialog }
    ManagementPanel { id: managementPanel }
    SettingsWindow { id: settingsWindow }
    TemplateLibrary { id: templateLibrary }
    Connections {
        target: controller
        ignoreUnknownSignals: true
        function onOpenSettingsDialog() { settingsWindow.open() }
        function onOpenTemplates() { templateLibrary.openedFromSettings = settingsWindow.visible; templateLibrary.open() }
        function onPrefillComposer(text) { settingsWindow.close() }
        function onOpenFontDialog() { fontPopup.open() }
        function onOpenTokenDialog() { tokenPopup.st = controller.tokenStats(); tokenPopup.open() }
        function onOpenInfoDialog(title, body) { infoDialog.openInfo(title, body) }
        function onOpenUpdateDialog(title, body) { infoDialog.openUpdate(title, body) }
        function onOpenSubscriptionDialog() { subscriptionDialog.show() }
        function onOpenApiKeyDialog(provider) { actionDialog.openApi(provider) }
        function onOpenCustomProviderDialog(url, key, model, anthropic, contextLimit, supportsVision) { actionDialog.openCustom(url, key, model, anthropic, contextLimit, supportsVision) }
        function onOpenConfirmDialog(title, body, token) { actionDialog.openConfirm(title, body, token) }
        function onOpenRulesDialog() { managementPanel.openRules() }
        function onOpenPluginsDialog() { managementPanel.openPlugins() }
        function onOpenMemoryDialog() { managementPanel.openMemory() }
        function onManagementChanged() { managementPanel.refresh() }
    }
}
