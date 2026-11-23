import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import HAgent

ColumnLayout {
    id: root
    property alias text: field.text
    property string label: ""
    property string placeholder: ""
    property bool password: false
    spacing: Theme.sp(6)

    Text {
        text: root.label
        color: Theme.textDim
        font.family: Theme.fontBody
        font.pixelSize: Theme.fXs
    }
    TextField {
        id: field
        Layout.fillWidth: true
        Layout.preferredHeight: Theme.fieldHeight
        verticalAlignment: TextInput.AlignVCenter
        leftPadding: Theme.fs(10); rightPadding: Theme.fs(10)
        echoMode: root.password ? TextInput.Password : TextInput.Normal
        color: Theme.textBright
        placeholderText: root.placeholder
        placeholderTextColor: Theme.textMute
        font.family: Theme.fontBody
        font.pixelSize: Theme.fSm
        background: Rectangle {
            color: Theme.fieldBg
            border.color: field.activeFocus ? Theme.accentLine : Theme.border
            border.width: 1
            radius: Theme.radSm
        }
    }
}
