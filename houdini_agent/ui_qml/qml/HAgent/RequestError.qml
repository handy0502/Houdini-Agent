import QtQuick
import QtQuick.Layouts
import HAgent

ColumnLayout {
    id: root
    property var block: ({})
    spacing: Theme.sp(6)
    TextEdit {
        Layout.fillWidth: true
        text: (controller && controller.lang === "en" ? "Error: " : "错误：") + (root.block.text || "")
        textFormat: TextEdit.PlainText
        readOnly: true
        selectByMouse: true
        wrapMode: TextEdit.Wrap
        color: Theme.err
        font.family: Theme.fontBody
        font.pixelSize: Theme.fBody
    }
    Text {
        Layout.fillWidth: true
        visible: text.length > 0
        text: root.block.hint || ""
        textFormat: Text.PlainText
        wrapMode: Text.Wrap
        color: Theme.textDim
        font.family: Theme.fontBody
        font.pixelSize: Theme.fSm
    }
    Pill {
        objectName: "restoreFailedMessage_" + (root.block.request_id || "")
        visible: !!root.block.request_id
        enabled: controller && !controller.running
        opacity: enabled ? 1 : 0.4
        label: controller && controller.lang === "en" ? "Return to input" : "返回输入框"
        onClicked: if (controller) controller.restoreFailedMessage(root.block.request_id)
    }
}
