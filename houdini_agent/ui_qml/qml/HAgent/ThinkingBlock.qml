import QtQuick
import HAgent

// Collapsible reasoning block.
Item {
    id: tb
    objectName: "thinkingBlock"
    property var block: ({})
    readonly property bool streaming: block.active === true
    property bool collapsed: !streaming
    onStreamingChanged: collapsed = !streaming
    readonly property string formattedDuration: durationLabel(block.dur || "")
    function durationLabel(value) {
        var match = /^(\d+(?:\.\d+)?)s$/.exec(String(value))
        if (!match) return String(value)
        var seconds = Math.floor(Number(match[1]))
        if (seconds < 60) return seconds + " s"
        return Math.floor(seconds / 60) + " min " + (seconds % 60) + " s"
    }
    implicitHeight: box.height

    Rectangle {
        id: box
        width: parent.width
        height: inner.implicitHeight
        color: "transparent"
        border.color: Theme.borderSoft
        border.width: tb.collapsed ? 0 : 1
        radius: Theme.radSm

        Column {
            id: inner
            width: parent.width

            Item {
                id: head
                objectName: "thinkingBlockHeader"
                width: parent.width
                height: Math.round(38 * Theme.scale)
                Row {
                    id: headerContent
                    anchors.left: parent.left; anchors.leftMargin: 13
                    anchors.verticalCenter: parent.verticalCenter
                    width: Math.max(0, head.width - 26 - Theme.fs(22) - 8)
                    spacing: 8
                    AppIcon { name: "spark"; color: Theme.textMute; anchors.verticalCenter: parent.verticalCenter }
                    Text {
                        anchors.verticalCenter: parent.verticalCenter
                        width: Math.max(0, headerContent.width - Theme.fs(18) - headerContent.spacing)
                        elide: Text.ElideRight
                        text: (controller && controller.lang === "en" ? "Thought for " : "思考用时 ") + tb.formattedDuration
                        color: Theme.textDim
                        font.family: Theme.fontBody
                        font.pixelSize: Theme.fSm
                        font.letterSpacing: Theme.trackLabel
                    }
                }
                AppIcon {
                    objectName: "thinkingCollapseIcon"
                    anchors.right: parent.right; anchors.rightMargin: 13
                    anchors.verticalCenter: parent.verticalCenter
                    width: Theme.fs(22); height: width
                    name: "chevronDown"; rotation: tb.collapsed ? -90 : 0
                    color: Theme.textDim
                }
                MouseArea { anchors.fill: parent; cursorShape: Qt.PointingHandCursor; onClicked: tb.collapsed = !tb.collapsed }
            }

            Rectangle { visible: !tb.collapsed; width: parent.width; height: 1; color: Theme.border }

            Text {
                visible: !tb.collapsed
                width: parent.width
                leftPadding: 13; rightPadding: 13; topPadding: 11; bottomPadding: 12
                // html：controller 转好的 StyledText（**标题** 加粗）；老会话没有 html 时按纯文本显示
                textFormat: tb.block.html ? Text.StyledText : Text.PlainText
                text: tb.block.html || tb.block.text || ""
                wrapMode: Text.Wrap
                color: Theme.textMute
                font.family: Theme.fontBody
                font.pixelSize: Theme.fSm
                lineHeight: 1.55
            }
        }
    }
}
