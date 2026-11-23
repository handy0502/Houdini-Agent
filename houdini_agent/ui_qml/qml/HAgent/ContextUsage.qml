import QtQuick
import QtQuick.Controls.Basic
import HAgent

Item {
    id: usage
    implicitWidth: Theme.controlHeight
    implicitHeight: Theme.controlHeight
    property var stats: ({})
    readonly property real used: Math.max(0, Number(stats.ctx_used) || 0)
    readonly property real limit: Math.max(0, Number(stats.ctx_limit) || 0)
    readonly property real fraction: limit > 0 ? Math.max(0, Math.min(1, used / limit)) : 0
    readonly property color ringColor: fraction >= 1 ? Theme.err : fraction >= 0.9 ? Theme.warn : Theme.textDim
    function loc(zh, en) { return controller && controller.lang === "en" ? en : zh }
    function raw(value) { return Math.round(value).toLocaleString(Qt.locale(), "f", 0) }
    function refresh() { stats = controller ? controller.tokenStats() : ({}) }
    Component.onCompleted: refresh()
    Connections {
        target: controller
        ignoreUnknownSignals: true
        function onTokensChanged() { usage.refresh() }
        function onModelChanged() { usage.refresh() }
        function onProviderChanged() { usage.refresh() }
    }
    Accessible.role: Accessible.ProgressBar
    Accessible.name: loc("上下文用量", "Context usage")
    Accessible.description: details.text

    Canvas {
        id: ring
        anchors.centerIn: parent
        width: Theme.fs(18); height: width
        onWidthChanged: requestPaint()
        onHeightChanged: requestPaint()
        Connections {
            target: usage
            function onFractionChanged() { ring.requestPaint() }
            function onRingColorChanged() { ring.requestPaint() }
        }
        Connections {
            target: Theme
            function onTextMuteChanged() { ring.requestPaint() }
        }
        onPaint: {
            var c = getContext("2d")
            c.reset()
            var stroke = Math.max(1.5, Theme.scale * 1.5)
            var radius = (width - stroke) / 2
            c.lineWidth = stroke
            c.strokeStyle = Qt.rgba(Theme.textMute.r, Theme.textMute.g, Theme.textMute.b, 0.4)
            c.beginPath()
            c.arc(width / 2, height / 2, radius, 0, Math.PI * 2)
            c.stroke()
            if (usage.fraction > 0) {
                c.strokeStyle = usage.ringColor
                c.lineCap = "round"
                c.beginPath()
                c.arc(width / 2, height / 2, radius, -Math.PI / 2,
                      -Math.PI / 2 + Math.PI * 2 * usage.fraction)
                c.stroke()
            }
        }
    }
    MouseArea { id: hover; anchors.fill: parent; hoverEnabled: true }
    ToolTip {
        id: details
        objectName: "contextUsageTooltip"
        visible: hover.containsMouse
        delay: 350
        text: usage.limit > 0
            ? usage.loc("上下文已用 ", "Context used: ") + Math.round(usage.fraction * 100) + "%\n"
              + usage.loc("已使用：", "Used: ") + usage.raw(usage.used) + " tokens\n"
              + usage.loc("总长度：", "Capacity: ") + usage.raw(usage.limit) + " tokens"
            : usage.loc("上下文长度暂不可用", "Context capacity unavailable")
        font.family: Theme.fontBody
        font.pixelSize: Theme.fXs
        padding: Theme.sp(10)
        contentItem: Text {
            text: details.text
            color: Theme.text
            font: details.font
        }
        background: Rectangle { color: Theme.panel; radius: Theme.radMd; border.color: Theme.border; border.width: 1 }
    }
}
