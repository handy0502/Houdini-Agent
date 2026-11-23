import QtQuick
import QtQuick.Layouts
import HAgent

// Houdini network path + selection indicator.
Rectangle {
    id: ctx
    color: "transparent"
    implicitHeight: Math.round(30 * Theme.scale)

    RowLayout {
        anchors.fill: parent
        anchors.leftMargin: 16; anchors.rightMargin: 14
        spacing: 8

        Text {
            text: controller ? controller.scenePath : "/obj/geo1"
            color: Theme.textMute
            font.family: Theme.fontMono
            font.pixelSize: Theme.fXs
        }
        Text { text: "·"; color: Theme.textMute; font.pixelSize: Theme.fXs }
        Text {
            Layout.fillWidth: true
            text: controller ? controller.sceneSelection : "2 nodes selected"
            color: Theme.textMute
            font.family: Theme.fontBody
            font.pixelSize: Theme.fXs
            elide: Text.ElideRight
        }
        IconButton {
            icon: "refresh"
            implicitWidth: 24; implicitHeight: 24
            tooltip: controller && controller.lang === "en" ? "Refresh scene context" : "刷新场景上下文"
            onClicked: if (controller) controller.refreshContext()
        }
    }
}
