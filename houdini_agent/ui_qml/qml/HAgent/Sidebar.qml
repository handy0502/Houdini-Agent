import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import HAgent

Rectangle {
    id: sidebar
    color: Theme.sidebar
    radius: Theme.radMd
    signal navigated()
    property var items: controller ? controller.sessionItems() : []
    property string query: ""
    function loc(zh, en) { return controller && controller.lang === "en" ? en : zh }
    function removeChat(index) {
        if (!controller) return
        if (controller.askDeleteSession) controller.closeSession(index)
        else controller.deleteSession(index)
    }
    function filtered() {
        var rows = [], q = query.toLowerCase()
        for (var i = 0; i < items.length; i++) {
            var it = items[i]
            if (!q || (it.title || "").toLowerCase().indexOf(q) >= 0)
                rows.push({title: it.title, time: it.time, active: it.active, idx: i})
        }
        return rows
    }
    Connections {
        target: controller
        function onSessionsChanged() { sidebar.items = controller.sessionItems() }
        function onLangChanged() { sidebar.items = controller.sessionItems() }
    }
    ColumnLayout {
        anchors.fill: parent; anchors.margins: Theme.sp(12); spacing: Theme.sp(6)
        Rectangle {
            objectName: "newChatButton"
            Layout.fillWidth: true; implicitHeight: Theme.fs(38); radius: Theme.radSm
            color: newHover.containsMouse ? Theme.surface2 : Theme.surface
            RowLayout {
                anchors.fill: parent; anchors.leftMargin: 12; anchors.rightMargin: 12; spacing: 10
                AppIcon { name: "plus"; color: Theme.text }
                Text { Layout.fillWidth: true; text: sidebar.loc("新对话", "New chat"); color: Theme.text; font.family: Theme.fontBody; font.pixelSize: Theme.fSm }
            }
            MouseArea { id: newHover; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor; onClicked: if (controller) { controller.newSession(); sidebar.navigated() } }
        }
        Rectangle {
            Layout.fillWidth: true; implicitHeight: Theme.fs(36); radius: Theme.radSm
            color: Theme.surface
            RowLayout {
                anchors.fill: parent; anchors.leftMargin: 12; anchors.rightMargin: 10; spacing: 10
                AppIcon { name: "search"; color: Theme.textMute }
                TextField {
                    id: search; objectName: "sessionSearch"; Layout.fillWidth: true
                    placeholderText: sidebar.loc("搜索对话", "Search chats")
                    placeholderTextColor: Theme.textMute; color: Theme.text
                    font.family: Theme.fontBody; font.pixelSize: Theme.fSm
                    leftPadding: 0; rightPadding: 0; background: null
                    onTextChanged: sidebar.query = text
                }
            }
        }
        Text {
            Layout.leftMargin: 12; Layout.topMargin: 20; Layout.bottomMargin: 6
            text: sidebar.loc("最近对话", "Recent chats")
            font.family: Theme.fontBody; font.pixelSize: Theme.fXs; color: Theme.textMute
        }
        ListView {
            id: sessions; objectName: "sidebarSessions"
            Layout.fillWidth: true; Layout.fillHeight: true
            clip: true; spacing: 3; model: sidebar.filtered()
            boundsBehavior: Flickable.StopAtBounds
            ScrollBar.vertical: SmartScrollBar {}
            delegate: Rectangle {
                id: sessionRow; required property var modelData
                objectName: "sessionRow_" + modelData.idx
                readonly property bool showDelete: sidebar.items.length > 1 && rowPointer.hovered
                width: ListView.view.width; height: Theme.fs(40); radius: Theme.radSm
                color: modelData.active ? Theme.accentSoft : rowPointer.hovered ? Theme.surface : "transparent"
                // Observe the whole row independently of its clickable children.
                // Moving into the delete hit area must not end the row's hover.
                HoverHandler { id: rowPointer }
                MouseArea {
                    anchors.fill: parent; cursorShape: Qt.PointingHandCursor
                    onClicked: if (controller) { controller.switchSession(sessionRow.modelData.idx); sidebar.navigated() }
                }
                RowLayout {
                    anchors.fill: parent; anchors.leftMargin: Theme.sp(12); anchors.rightMargin: Theme.sp(6); spacing: Theme.sp(8)
                    Text {
                        Layout.fillWidth: true; text: sessionRow.modelData.title || sidebar.loc("新对话", "New chat")
                        color: sessionRow.modelData.active ? Theme.textBright : Theme.textDim
                        font.family: Theme.fontBody; font.pixelSize: Theme.fSm; elide: Text.ElideRight
                    }
                    Item {
                        // Reserve a stable trailing area when time and delete swap.
                        Layout.preferredWidth: Math.max(timestamp.implicitWidth, Theme.controlHeight)
                        Layout.preferredHeight: Theme.controlHeight
                        Text {
                            id: timestamp
                            objectName: "sessionTime_" + sessionRow.modelData.idx
                            anchors.right: parent.right; anchors.verticalCenter: parent.verticalCenter
                            visible: !sessionRow.showDelete
                            text: sessionRow.modelData.time || ""; color: Theme.textMute
                            font.family: Theme.fontBody; font.pixelSize: Theme.fMicro
                        }
                        Rectangle {
                            objectName: "deleteSession_" + sessionRow.modelData.idx
                            anchors.right: parent.right; anchors.verticalCenter: parent.verticalCenter
                            width: Theme.controlHeight; height: width; radius: height / 2
                            visible: sessionRow.showDelete
                            color: deleteHover.containsMouse ? Theme.surface2 : "transparent"
                            activeFocusOnTab: true
                            Accessible.role: Accessible.Button
                            Accessible.name: sidebar.loc("删除对话", "Delete chat")
                            Keys.onReturnPressed: sidebar.removeChat(sessionRow.modelData.idx)
                            Keys.onSpacePressed: sidebar.removeChat(sessionRow.modelData.idx)
                            TrashIcon { anchors.centerIn: parent; size: Theme.fs(14); color: deleteHover.containsMouse ? Theme.err : Theme.textMute }
                            MouseArea {
                                id: deleteHover; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor
                                onClicked: sidebar.removeChat(sessionRow.modelData.idx)
                            }
                        }
                    }
                }
            }
            Text {
                anchors.top: parent.top; anchors.topMargin: 12; anchors.horizontalCenter: parent.horizontalCenter
                visible: sessions.count === 0; text: sidebar.loc("没有匹配的对话", "No matching chats")
                color: Theme.textMute; font.family: Theme.fontBody; font.pixelSize: Theme.fXs
            }
        }
        IconButton {
            objectName: "settingsButton"
            Layout.alignment: Qt.AlignRight
            Layout.rightMargin: Theme.sp(6)
            icon: "gear"; circular: true
            tooltip: sidebar.loc("设置", "Settings")
            onClicked: if (controller) controller.menuAction("settings")
        }
    }
}
