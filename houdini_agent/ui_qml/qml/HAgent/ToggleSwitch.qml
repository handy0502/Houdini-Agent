import QtQuick
import QtQuick.Controls.Basic
import HAgent

// Shared switch: a green track and checked thumb distinguish On from Off.
AbstractButton {
    id: toggle
    property alias on: toggle.checked
    checkable: true
    hoverEnabled: true
    implicitWidth: Theme.fs(40)
    implicitHeight: Theme.controlHeight
    padding: 0
    opacity: enabled ? 1 : 0.4
    Accessible.role: Accessible.CheckBox
    background: Rectangle {
        radius: height / 2
        color: toggle.visualFocus ? Theme.surface2 : "transparent"
    }
    contentItem: Item {
        Rectangle {
            id: track
            objectName: "switchTrack"
            anchors.centerIn: parent
            width: Theme.fs(36); height: Theme.fs(20); radius: height / 2
            color: toggle.checked ? Theme.switchOn : Theme.switchOff
            opacity: toggle.hovered && !toggle.down ? 0.85 : 1
            Behavior on color { ColorAnimation { duration: 120 } }
            Rectangle {
                id: thumb
                objectName: "switchThumb"
                width: Theme.fs(16); height: width; radius: width / 2
                anchors.verticalCenter: parent.verticalCenter
                x: toggle.checked ? track.width - width - Theme.fs(2) : Theme.fs(2)
                color: toggle.checked ? Theme.switchThumbOn : Theme.switchThumbOff
                Behavior on x { NumberAnimation { duration: 120; easing.type: Easing.OutCubic } }
                Behavior on color { ColorAnimation { duration: 120 } }
                AppIcon {
                    anchors.centerIn: parent
                    visible: toggle.checked
                    name: "check"; color: Theme.switchOn
                    width: Theme.fs(11); height: width
                }
            }
        }
    }
}
