import QtQuick
import QtQuick.Controls
import HAgent

// Scrollable conversation. Top-level rows: user | ai | plan.
Flickable {
    id: view
    clip: true
    contentWidth: width
    contentHeight: Math.max(height, rows.y + rows.implicitHeight + 18)
    boundsBehavior: Flickable.StopAtBounds
    boundsMovement: Flickable.StopAtBounds
    pixelAligned: false
    flickDeceleration: 3600
    maximumFlickVelocity: 7200

    // Keep every message instantiated instead of virtualizing variable-height
    // rows. This avoids scrollbar thumb jumps while dragging across mixed
    // user/AI/plan message heights.
    property bool stick: true
    property var navigationEntries: []
    property int jumpTarget: -1
    readonly property real navigationGutter: navigationEntries.length > 1 ? Theme.fs(28) : 0
    readonly property int activeTurn: {
        var active = navigationEntries.length ? 0 : -1
        for (var i = 0; i < navigationEntries.length; i++) {
            var row = rep.itemAt(navigationEntries[i].row)
            if (row && row.topInContent <= contentY + Theme.sp(20)) active = i
        }
        return active
    }
    function refreshNavigation() {
        var entries = []
        for (var i = 0; i < rep.count; i++) {
            var row = rep.itemAt(i)
            if (row && row.rtype === "user") entries.push({row: i, text: row.payload.text || ""})
        }
        navigationEntries = entries
    }
    function positionAtTarget() {
        var row = rep.itemAt(jumpTarget)
        if (row) contentY = Math.max(0, Math.min(bottomY(), row.topInContent - Theme.sp(12)))
    }
    function jumpToMessage(index) {
        if (index < 0 || index >= rep.count) return
        cancelFlick()
        jumpTarget = index
        stick = false
        var row = rep.itemAt(index)
        if (row) row.asynchronous = false
        Qt.callLater(positionAtTarget)
    }
    function nearBottom() {
        return contentHeight <= height || (contentY >= contentHeight - height - 48)
    }
    function bottomY() {
        return Math.max(0, contentHeight - height)
    }
    function scrollToEndIfSticky() {
        if (jumpTarget >= 0) positionAtTarget()
        else if (stick && !vbar.pressed) contentY = bottomY()
    }
    onHeightChanged: Qt.callLater(scrollToEndIfSticky)
    onContentHeightChanged: Qt.callLater(scrollToEndIfSticky)
    onMovementStarted: { jumpTarget = -1; stick = false }
    // 打开 / 切换会话（模型重置）时回到底部并保持贴底：较早的消息是分帧异步创建的，
    // 会陆续插到上方，贴底才能让视图稳定停在最新消息处。
    Connections {
        target: chatModel
        function onModelReset() {
            view.jumpTarget = -1
            view.stick = true
            Qt.callLater(view.refreshNavigation)
            Qt.callLater(view.scrollToEndIfSticky)
        }
        function onDataChanged() { Qt.callLater(view.refreshNavigation) }
    }
    onMovementEnded: if (jumpTarget < 0) stick = nearBottom()
    onFlickEnded: if (jumpTarget < 0) stick = nearBottom()

    Column {
        id: rows
        x: (view.width - view.navigationGutter - width) / 2
        y: rep.count === 0 ? Math.max(Theme.sp(36), (view.height - implicitHeight) * 0.40) : Theme.sp(28)
        width: Math.max(0, Math.min(Theme.contentMaxWidth, view.width - view.navigationGutter - Theme.sp(40)))
        spacing: Theme.sp(28)

        // 空会话起手式（仅在没有任何消息时显示）
        EmptyState {
            width: rows.width
            visible: rep.count === 0
            height: visible ? implicitHeight : 0
        }

        Repeater {
            id: rep
            model: chatModel
            delegate: Loader {
                id: ld
                objectName: "chatMessage_" + index
                required property string rtype
                required property var payload
                required property int index
                // 打开长会话时，较早的消息在后续帧里分批创建（最近几条仍同步出现），
                // 避免一次性同步实例化全部历史把界面冻住近一秒。
                asynchronous: index < rep.count - 6
                width: rows.width
                height: item ? item.implicitHeight : 0
                // 每条消息独立成一个渲染批次根：流式更新最后一条消息时，
                // 只重建这一条的几何，不连带重建全部历史文字（长会话卡顿主因）。
                clip: true
                // 视口外（上下各留一屏余量）的消息不参与渲染：opacity 为 0 的子树
                // 会被渲染器整棵跳过，且不影响 Column 布局与高度。
                readonly property real topInContent: rows.y + y
                onTopInContentChanged: if (view.jumpTarget === index) Qt.callLater(view.positionAtTarget)
                opacity: (topInContent + height >= view.contentY - view.height
                          && topInContent <= view.contentY + 2 * view.height) ? 1 : 0
                sourceComponent: rtype === "user" ? cUser
                               : rtype === "plan" ? cPlan
                               : cAi
                Component { id: cUser; MessageUser { msg: ld.payload; width: ld.width } }
                Component { id: cAi;   MessageAI  { msg: ld.payload; width: ld.width } }
                Component { id: cPlan; PlanCard   { plan: ld.payload; width: ld.width } }
            }
            onCountChanged: { Qt.callLater(view.refreshNavigation); Qt.callLater(view.scrollToEndIfSticky) }
            onItemAdded: Qt.callLater(view.refreshNavigation)
            onItemRemoved: Qt.callLater(view.refreshNavigation)
        }
    }

    ChatTimeline {
        objectName: "chatTimeline"
        parent: view
        anchors.right: parent.right; anchors.rightMargin: Theme.fs(10)
        anchors.verticalCenter: parent.verticalCenter
        width: implicitWidth
        height: Math.max(0, Math.min(implicitHeight, view.height - Theme.sp(32)))
        visible: entries.length > 1
        entries: view.navigationEntries
        currentIndex: view.activeTurn
        onActivated: function(row) { view.jumpToMessage(row) }
    }

    ScrollBar.vertical: SmartScrollBar {
        id: vbar
        onPressedChanged: {
            if (pressed) { view.jumpTarget = -1; view.stick = false }
            else view.stick = view.nearBottom()
        }
    }
}
