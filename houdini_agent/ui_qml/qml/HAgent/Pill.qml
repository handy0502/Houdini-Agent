import QtQuick
import QtQuick.Layouts
import HAgent

// Quiet compact button shared by selectors, toggles, and actions.
Item {
    id: pill
    property string label: ""
    property string detail: ""
    property bool active: false
    property bool caret: false
    property bool accent: false
    property bool dashed: false
    property bool uppercase: false
    property bool elideLabel: false   // 标签随宽度省略号截断（用于可收缩布局）
    signal clicked()

    implicitHeight: Theme.controlHeight
    implicitWidth: row.implicitWidth + 22

    Rectangle {
        id: bg
        objectName: "pillBackground"
        anchors.fill: parent
        radius: height / 2
        color: pill.active ? Theme.accentSoft : (ma.containsMouse ? Theme.surface : "transparent")
        border.width: 0
        Behavior on color { ColorAnimation { duration: 120 } }
    }

    RowLayout {
        id: row
        anchors.left: parent.left; anchors.right: parent.right
        anchors.verticalCenter: parent.verticalCenter
        anchors.leftMargin: 11; anchors.rightMargin: 11
        spacing: 5
        Text {
            Layout.fillWidth: pill.elideLabel
            text: pill.uppercase ? pill.label.toUpperCase() : pill.label
            color: pill.active ? Theme.accent : (pill.accent ? Theme.accent : Theme.textDim)
            font.family: Theme.fontBody
            font.pixelSize: Theme.fSm
            font.letterSpacing: pill.uppercase ? Theme.trackLabel : 0
            elide: pill.elideLabel ? Text.ElideRight : Text.ElideNone
        }
        Text {
            visible: pill.detail.length > 0
            text: pill.detail
            color: Theme.textMute
            font.family: Theme.fontBody
            font.pixelSize: Theme.fSm
        }
        AppIcon {
            visible: pill.caret
            name: "chevronDown"
            Layout.preferredWidth: Theme.fs(13)
            Layout.preferredHeight: Theme.fs(13)
            color: Theme.textMute
        }
    }

    MouseArea {
        id: ma
        anchors.fill: parent
        hoverEnabled: true
        cursorShape: Qt.PointingHandCursor
        onClicked: pill.clicked()
    }
}
