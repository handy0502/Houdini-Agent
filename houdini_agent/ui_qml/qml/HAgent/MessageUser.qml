import QtQuick
import QtQuick.Layouts
import QtQuick.Controls.Basic
import HAgent

// User message — a right-aligned bubble on a soft neutral surface.
// Shows attached image thumbnails (if any) above the text.
Item {
    id: root
    property var msg: ({})
    property int messageRow: -1
    property var images: (msg && msg.images) ? msg.images : []
    implicitHeight: col.height

    Column {
        id: col
        anchors.right: parent.right
        width: parent.width
        spacing: 6

        // attached image thumbnails (right-aligned, wraps for multiple)
        Flow {
            anchors.right: parent.right
            width: Math.min(parent.width * 0.86, 320)
            layoutDirection: Qt.RightToLeft
            spacing: 6
            visible: root.images.length > 0
            Repeater {
                model: root.images
                delegate: Rectangle {
                    required property var modelData
                    width: 76; height: 76
                    color: Theme.codeBg
                    radius: Theme.radSm
                    clip: true
                    ThumbnailImage {
                        anchors.fill: parent
                        source: "" + modelData
                        asynchronous: true
                        sourceSize: Qt.size(160, 160)
                    }
                }
            }
        }

        // text bubble
        Rectangle {
            id: bubble
            objectName: "userMessageBubble"
            anchors.right: parent.right
            visible: txt.text.length > 0
            width: Math.min(parent.width * 0.86, txt.implicitWidth + 32)
            height: txt.implicitHeight + 24
            color: Theme.userBg
            radius: Theme.radLg

            TextEdit {
                id: txt
                anchors.left: parent.left; anchors.right: parent.right
                anchors.verticalCenter: parent.verticalCenter
                anchors.leftMargin: 14; anchors.rightMargin: 14
                text: root.msg && root.msg.text ? root.msg.text : ""
                readOnly: true
                selectByMouse: true
                wrapMode: TextEdit.Wrap
                color: Theme.userFg
                selectionColor: Theme.accentSoft
                selectedTextColor: Theme.textBright
                font.family: Theme.fontBody
                font.pixelSize: Theme.fBody
            }
        }
        RowLayout {
            anchors.right: parent.right
            spacing: Theme.sp(6)
            Text {
                objectName: "sentTime_" + root.messageRow
                visible: !!root.msg.sent_at
                text: visible ? Qt.formatDateTime(new Date(root.msg.sent_at * 1000), "HH:mm") : ""
                color: Theme.textMute
                font.family: Theme.fontBody
                font.pixelSize: Theme.fSm
                ToolTip.visible: timeHover.containsMouse
                ToolTip.text: root.msg.sent_at ? Qt.formatDateTime(new Date(root.msg.sent_at * 1000), "yyyy-MM-dd HH:mm:ss") : ""
                MouseArea { id: timeHover; anchors.fill: parent; hoverEnabled: true }
            }
            IconButton {
                objectName: "copyUserMessage_" + root.messageRow
                icon: "copy"
                tooltip: controller && controller.lang === "en" ? "Copy message" : "复制消息"
                visible: txt.text.length > 0
                onClicked: if (controller) controller.copyToClipboard(txt.text)
            }
        }
    }
}
