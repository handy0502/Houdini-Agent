import QtQuick
import QtQuick.Layouts
import QtQuick.Controls.Basic
import HAgent

Rectangle {
    id: root
    objectName: "messageQueuePanel"
    property real heightBudget: Theme.fs(130)
    readonly property int count: controller ? controller.queuedCount : 0
    readonly property bool paused: controller && controller.queuePaused
    function loc(zh, en) { return controller && controller.lang === "en" ? en : zh }
    visible: count > 0
    implicitHeight: visible ? Math.max(Theme.controlHeight + Theme.fs(24),
        Math.min(heightBudget, Theme.controlHeight * (count + 1) + Theme.sp(8))) : 0
    radius: Theme.radMd
    color: Theme.surface
    ColumnLayout {
        anchors.fill: parent
        anchors.margins: Theme.sp(4)
        spacing: 0
        RowLayout {
            Layout.fillWidth: true
            Layout.preferredHeight: Theme.controlHeight
            Text {
                Layout.fillWidth: true
                Layout.leftMargin: Theme.sp(8)
                text: root.count + root.loc(" 条消息排队", " queued messages")
                    + (root.paused ? root.loc(" · 已暂停", " · Paused") : "")
                elide: Text.ElideRight
                color: Theme.textDim
                font.family: Theme.fontBody; font.pixelSize: Theme.fXs
            }
            Pill {
                objectName: "resumeMessageQueue"
                visible: root.paused
                label: root.loc("继续", "Resume")
                onClicked: if (controller) controller.resumeMessageQueue()
            }
        }
        ListView {
            id: list
            objectName: "queuedMessageList"
            Layout.fillWidth: true; Layout.fillHeight: true
            clip: true
            boundsBehavior: Flickable.StopAtBounds
            ScrollBar.vertical: SmartScrollBar {}
            model: controller ? controller.queuedMessages : []
            delegate: RowLayout {
                required property var modelData
                width: list.width
                height: Theme.controlHeight
                spacing: Theme.sp(2)
                Text {
                    Layout.fillWidth: true
                    Layout.leftMargin: Theme.sp(8)
                    text: modelData.text.replace(/\s+/g, " ")
                        + (modelData.images > 0 ? " · " + modelData.images + root.loc(" 张图片", " images") : "")
                    textFormat: Text.PlainText
                    elide: Text.ElideRight
                    color: Theme.text
                    font.family: Theme.fontBody; font.pixelSize: Theme.fSm
                }
                IconButton {
                    objectName: "editQueuedMessage_" + modelData.id
                    icon: "arrowLeft"; tooltip: root.loc("返回输入框", "Return to input")
                    onClicked: if (controller) controller.editQueuedMessage(modelData.id)
                }
                IconButton {
                    objectName: "removeQueuedMessage_" + modelData.id
                    icon: "close"; tooltip: root.loc("取消排队", "Cancel queued message")
                    onClicked: if (controller) controller.removeQueuedMessage(modelData.id)
                }
            }
        }
    }
}
