import QtQuick
import QtQuick.Layouts
import HAgent

Rectangle {
    id: header
    color: "transparent"
    implicitHeight: Theme.fs(58)
    property var sessions: controller ? controller.sessionItems() : []
    function loc(zh, en) { return controller && controller.lang === "en" ? en : zh }
    function title() {
        for (var i = 0; i < sessions.length; i++) if (sessions[i].active) return sessions[i].title
        return loc("新对话", "New chat")
    }
    Connections {
        target: controller
        function onSessionsChanged() { header.sessions = controller.sessionItems() }
        function onLangChanged() { header.sessions = controller.sessionItems() }
    }
    RowLayout {
        anchors.fill: parent; anchors.leftMargin: Theme.sp(16); anchors.rightMargin: Theme.sp(16)
        spacing: Theme.sp(8)
        Text {
            Layout.fillWidth: true; Layout.minimumWidth: 40
            text: header.title(); elide: Text.ElideRight
            color: Theme.textBright; font.family: Theme.fontBody; font.pixelSize: Theme.fBody; font.weight: Font.Medium
        }
        IconButton {
            objectName: "settingsButton"
            icon: "more"; circular: true
            tooltip: header.loc("设置", "Settings")
            onClicked: if (controller) controller.menuAction("settings")
        }
    }
}
