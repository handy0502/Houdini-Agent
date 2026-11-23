import QtQuick
import QtQuick.Controls.Basic
import HAgent

// One quiet tick per user turn. Long histories can scroll within the rail.
ListView {
    id: rail
    property var entries: []
    signal activated(int row)
    implicitWidth: Theme.fs(24)
    implicitHeight: entries.length * Theme.fs(14)
    model: entries
    clip: true
    boundsBehavior: Flickable.StopAtBounds
    highlightFollowsCurrentItem: false
    function revealCurrent() {
        if (!pointer.hovered && currentIndex >= 0) positionViewAtIndex(currentIndex, ListView.Contain)
    }
    onCurrentIndexChanged: Qt.callLater(revealCurrent)
    HoverHandler { id: pointer; onHoveredChanged: if (!hovered) rail.revealCurrent() }
    delegate: Item {
        required property int index
        required property var modelData
        objectName: "chatMarker_" + modelData.row
        width: rail.width; height: Theme.fs(14)
        Accessible.role: Accessible.Button
        Accessible.name: modelData.text || ""
        activeFocusOnTab: true
        Keys.onReturnPressed: rail.activated(modelData.row)
        Keys.onSpacePressed: rail.activated(modelData.row)
        Rectangle {
            anchors.centerIn: parent
            width: index === rail.currentIndex || hover.containsMouse ? Theme.fs(10) : Theme.fs(6)
            height: Theme.fs(2); radius: height / 2
            color: index === rail.currentIndex || hover.containsMouse ? Theme.textDim : Theme.scrollThumbHover
        }
        MouseArea {
            id: hover; anchors.fill: parent; hoverEnabled: true
            cursorShape: Qt.PointingHandCursor
            onClicked: rail.activated(modelData.row)
        }
        ToolTip {
            id: preview
            visible: hover.containsMouse
            delay: 350
            text: String(modelData.text || "").slice(0, 180)
            width: Math.min(Theme.fs(280), implicitWidth)
            contentItem: Text {
                text: preview.text; textFormat: Text.PlainText; wrapMode: Text.Wrap
                color: Theme.text; font.family: Theme.fontBody; font.pixelSize: Theme.fXs
            }
            background: Rectangle { color: Theme.panel; radius: Theme.radSm; border.width: 1; border.color: Theme.border }
        }
    }
}
