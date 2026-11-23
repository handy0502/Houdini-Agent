import QtQuick
import QtQuick.Controls.Basic
import HAgent

Rectangle {
    id: button
    property string icon: "plus"
    property string tooltip: ""
    property bool active: false
    property bool circular: false
    signal clicked()
    implicitWidth: Theme.controlHeight
    implicitHeight: Theme.controlHeight
    radius: circular ? Math.min(width, height) / 2 : Theme.radSm
    color: active || area.containsMouse ? Theme.surface2 : "transparent"
    opacity: enabled ? 1 : 0.4
    activeFocusOnTab: true
    Accessible.role: Accessible.Button
    Accessible.name: tooltip
    Keys.onReturnPressed: clicked()
    Keys.onSpacePressed: clicked()
    AppIcon { anchors.centerIn: parent; name: button.icon; color: button.active ? Theme.textBright : Theme.textDim }
    MouseArea {
        id: area
        anchors.fill: parent
        hoverEnabled: true
        cursorShape: Qt.PointingHandCursor
        onClicked: button.clicked()
    }
    ToolTip.visible: area.containsMouse && tooltip.length > 0
    ToolTip.delay: 650
    ToolTip.text: tooltip
}
