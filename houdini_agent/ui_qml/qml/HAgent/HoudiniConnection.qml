import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import HAgent

Rectangle {
    id: button
    objectName: "houdiniConnectionButton"
    property var info: controller ? controller.houdiniConnection : ({})
    readonly property bool connected: info.state === "connected" || info.state === "embedded"
    readonly property bool working: info.state === "connecting" || info.state === "launching"
    readonly property color statusColor: connected ? (Theme.light ? "#138a43" : "#27d769")
                                                        : (Theme.light ? "#d92d36" : "#ff4d4f")
    property real statusBrightness: 1
    SequentialAnimation {
        running: !button.connected && button.visible
        loops: Animation.Infinite
        onStopped: button.statusBrightness = 1
        NumberAnimation {
            target: button; property: "statusBrightness"
            from: 1; to: 0.55; duration: 1100; easing.type: Easing.InOutSine
        }
        NumberAnimation {
            target: button; property: "statusBrightness"
            from: 0.55; to: 1; duration: 1100; easing.type: Easing.InOutSine
        }
    }
    readonly property string status: info.state === "launching" ? loc("启动中", "Starting")
        : info.state === "connecting" ? loc("连接中", "Connecting")
        : connected ? loc("已连接", "Connected") : loc("未连接", "Disconnected")
    readonly property string description: "Houdini" + (info.version ? " " + info.version : "") + " · " + status
    readonly property bool canChange: info.external && !working && (!controller || !controller.running)
    function loc(zh, en) { return controller && controller.lang === "en" ? en : zh }
    function perform(action) {
        menu.close()
        if (controller) controller.houdiniAction(action)
    }
    function openMenu() {
        menu.open()
        if (controller && info.external) controller.houdiniAction("refresh")
    }
    onXChanged: if (menu && menu.visible) Qt.callLater(menu.refreshAnchor)
    onYChanged: if (menu && menu.visible) Qt.callLater(menu.refreshAnchor)
    onWidthChanged: if (menu && menu.visible) Qt.callLater(menu.refreshAnchor)
    onHeightChanged: if (menu && menu.visible) Qt.callLater(menu.refreshAnchor)
    component ConnectionAction: AbstractButton {
        id: actionButton
        property bool selected: false
        implicitHeight: Theme.fs(32)
        leftPadding: Theme.sp(10); rightPadding: Theme.sp(10)
        hoverEnabled: true
        Accessible.name: text
        HoverHandler { enabled: actionButton.enabled; cursorShape: Qt.PointingHandCursor }
        ToolTip.visible: hovered
        ToolTip.delay: 650
        ToolTip.text: text
        background: Rectangle {
            radius: Theme.radSm
            color: actionButton.hovered || actionButton.down || actionButton.visualFocus
                ? Qt.tint(Theme.panel, Theme.border) : Theme.surface2
        }
        contentItem: RowLayout {
            spacing: Theme.sp(6)
            Text {
                Layout.fillWidth: true
                text: actionButton.text; elide: Text.ElideRight
                color: actionButton.enabled ? Theme.textBright : Theme.textMute
                font.family: Theme.fontBody; font.pixelSize: Theme.fSm
            }
            AppIcon {
                visible: actionButton.selected
                name: "check"; color: button.statusColor
                Layout.preferredWidth: Theme.fs(14); Layout.preferredHeight: Theme.fs(14)
            }
        }
    }
    implicitWidth: Math.ceil(label.implicitWidth) + Theme.sp(24) + Theme.fs(6)
    implicitHeight: Theme.controlHeight
    radius: height / 2
    color: hover.containsMouse || menu.visible ? Theme.surface2 : "transparent"
    activeFocusOnTab: true
    Accessible.role: Accessible.Button
    Accessible.name: description
    Keys.onReturnPressed: openMenu()
    Keys.onSpacePressed: openMenu()
    RowLayout {
        anchors.fill: parent; anchors.leftMargin: Theme.sp(9); anchors.rightMargin: Theme.sp(9)
        spacing: Theme.sp(6)
        opacity: button.connected ? 1 : button.statusBrightness
        Rectangle {
            objectName: "houdiniStatusDot"
            Layout.preferredWidth: Theme.fs(6); Layout.preferredHeight: Theme.fs(6)
            radius: width / 2
            color: button.statusColor
        }
        Text {
            id: label
            objectName: "houdiniStatusLabel"
            Layout.fillWidth: true; Layout.minimumWidth: implicitWidth
            text: "Houdini"
            elide: Text.ElideNone
            color: button.statusColor; font.family: Theme.fontBody; font.pixelSize: Theme.fSm
        }
    }
    MouseArea { id: hover; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor; onClicked: button.openMenu() }
    ToolTip.visible: hover.containsMouse && !menu.visible
    ToolTip.text: description
    ToolTip.delay: 500
    Connections {
        target: controller
        function onOpenHoudiniMenu() { button.openMenu() }
    }
    Popup {
        id: menu
        objectName: "houdiniConnectionMenu"
        parent: Overlay.overlay
        property point anchorBottom: Qt.point(0, 0)
        readonly property bool overflowing: body.implicitHeight > availableHeight + 1
        function refreshAnchor() {
            if (parent) anchorBottom = button.mapToItem(parent, button.width, button.height)
        }
        onAboutToShow: {
            refreshAnchor()
            if (sessionScroll.contentItem) sessionScroll.contentItem.contentY = 0
        }
        onOpened: refreshAnchor()
        Connections {
            target: menu.parent
            function onWidthChanged() { if (menu.visible) Qt.callLater(menu.refreshAnchor) }
            function onHeightChanged() { if (menu.visible) Qt.callLater(menu.refreshAnchor) }
        }
        width: Math.min(Theme.fs(220), parent ? parent.width - Theme.sp(24) : Theme.fs(220))
        x: Math.max(Theme.sp(12), Math.min(anchorBottom.x - width,
            parent ? parent.width - width - Theme.sp(12) : 0))
        y: anchorBottom.y + Theme.sp(6)
        height: Math.max(0, Math.min(body.implicitHeight + topPadding + bottomPadding,
            parent ? Math.min(parent.height / 3, parent.height - y - Theme.sp(12)) : Theme.fs(480)))
        padding: Theme.sp(12)
        focus: true
        closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutside
        background: Rectangle { color: Theme.light ? Theme.panel : Qt.lighter(Theme.panel, 1.15); radius: Theme.radMd }
        contentItem: PanelScrollView {
            id: sessionScroll
            objectName: "houdiniMenuScrollView"
            contentWidth: availableWidth
            contentHeight: body.implicitHeight
            ScrollBar.vertical.objectName: "houdiniMenuScrollBar"
            ScrollBar.vertical.policy: menu.overflowing ? ScrollBar.AlwaysOn : ScrollBar.AlwaysOff
            ColumnLayout {
                id: body
                width: sessionScroll.availableWidth
                spacing: Theme.sp(6)
                Text {
                    Layout.fillWidth: true
                    visible: button.info.state === "embedded"
                    text: button.loc("当前运行在 Houdini 内", "Running inside Houdini")
                    color: Theme.textMute; font.family: Theme.fontBody; font.pixelSize: Theme.fXs; wrapMode: Text.Wrap
                }
                RowLayout {
                    Layout.fillWidth: true
                    visible: !!button.info.external
                    Text {
                        Layout.fillWidth: true
                        text: button.info.busy ? button.loc("正在查找会话…", "Finding sessions…") : button.loc("可连接的会话", "Available sessions")
                        color: Theme.textMute; font.family: Theme.fontBody; font.pixelSize: Theme.fXs; font.weight: Font.DemiBold
                    }
                    IconButton {
                        objectName: "disconnectHoudini"
                        icon: "close"; tooltip: button.loc("断开连接", "Disconnect")
                        visible: button.connected
                        enabled: button.canChange
                        onClicked: button.perform("disconnect")
                    }
                    IconButton {
                        icon: "refresh"; tooltip: button.loc("刷新会话", "Refresh sessions")
                        enabled: !button.info.busy
                        onClicked: if (controller) controller.houdiniAction("refresh")
                    }
                }
                Repeater {
                    model: button.info.sessions || []
                    delegate: ConnectionAction {
                        required property var modelData
                        objectName: "houdiniSession_" + modelData.port
                        Layout.fillWidth: true
                        text: "Houdini " + modelData.version + " · " + modelData.port
                        selected: button.connected && button.info.port === modelData.port
                        enabled: button.canChange
                        onClicked: button.perform("connect:" + modelData.port)
                    }
                }
                Text {
                    Layout.fillWidth: true
                    visible: !!button.info.external && !button.info.busy && !(button.info.sessions || []).length
                    text: button.loc("暂未发现 Bridge 会话", "No Bridge sessions found")
                    color: Theme.textMute; font.family: Theme.fontBody; font.pixelSize: Theme.fXs; font.weight: Font.DemiBold
                }
                Text {
                    Layout.fillWidth: true; Layout.topMargin: Theme.sp(6)
                    visible: !!button.info.external
                    text: button.loc("启动新会话", "Start a new session")
                    color: Theme.textMute; font.family: Theme.fontBody; font.pixelSize: Theme.fXs; font.weight: Font.DemiBold
                }
                Repeater {
                    model: button.info.installs || []
                    delegate: ConnectionAction {
                        required property int index
                        required property var modelData
                        objectName: "launchHoudini_" + index
                        Layout.fillWidth: true
                        text: button.loc("启动 Houdini ", "Start Houdini ") + modelData.version
                        enabled: button.canChange
                        onClicked: button.perform("launch:" + index)
                    }
                }
                Text {
                    Layout.fillWidth: true
                    visible: !!button.info.external && !(button.info.installs || []).length
                    text: button.loc("未找到 Houdini 19.5+ 安装", "No Houdini 19.5+ installation found")
                    color: Theme.textMute; font.family: Theme.fontBody; font.pixelSize: Theme.fXs; wrapMode: Text.Wrap
                }
            }
        }
    }
}
