import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Dialogs
import HAgent

Rectangle {
    id: composer
    color: "transparent"
    implicitHeight: col.implicitHeight + Theme.sp(16)
    property var modes: ["Agent", "Ask", "Plan"]
    property int modeIndex: controller ? Math.max(0, modes.indexOf(controller.mode)) : 0
    readonly property real toolbarMinimumWidth: leadingControls.implicitWidth
        + Theme.controlHeight * 2 + 40 + Theme.sp(3) * 4 + 5
    readonly property bool compactToolbar: inputLayout.width < toolbarMinimumWidth
    property var imgUris: controller ? controller.pendingImageUris() : []
    // Budget scrollable previews and text after reserving the fixed controls.
    // Keep some conversation visible whenever the available height permits it.
    property real availableHeightBudget: parent ? parent.height : Theme.fs(560)
    readonly property real fixedHeight: pendingStrip.implicitHeight + runStatus.implicitHeight
        + queuedMessages.implicitHeight
        + toolbar.implicitHeight + inputLayout.spacing + toolbar.Layout.topMargin + Theme.sp(16) * 2
        + col.spacing * ((pendingStrip.implicitHeight > 0 ? 1 : 0) + (runStatus.active ? 1 : 0) + (imgUris.length > 0 ? 1 : 0) + (queuedMessages.visible ? 1 : 0))
    readonly property real heightBudget: Math.max(0, Math.min(availableHeightBudget,
        Math.max(fixedHeight + Theme.fs(32) + (imgUris.length > 0 ? Theme.fs(58) : 0),
                 availableHeightBudget - Math.min(Theme.fs(120), availableHeightBudget * 0.25))))
    readonly property real flexibleHeight: Math.max(0, heightBudget - fixedHeight)
    readonly property real attachmentHeight: imgUris.length > 0
        ? Math.max(0, Math.min(attachmentFlow.implicitHeight, Theme.fs(58) * 2 + attachmentFlow.spacing,
                              flexibleHeight - Math.min(Theme.fs(32), flexibleHeight))) : 0
    readonly property real inputHeightLimit: Math.min(Theme.fs(170), Math.max(0, flexibleHeight - attachmentHeight))
    function loc(s) { return controller ? (controller.lang, controller.tr(s)) : s }
    function label(zh, en) { return controller && controller.lang === "en" ? en : zh }
    function focusInput() { inputArea.forceActiveFocus() }
    function insertText(t) {
        if (!inputArea || !t) return
        var pos = inputArea.cursorPosition
        inputArea.insert(pos, t)
        inputArea.cursorPosition = pos + t.length
    }
    function openMenu(item, menu) {
        var p = item.mapToItem(inputRow, 0, 0)
        menu.maximumHeight = Math.max(100, inputRow.mapToItem(null, 0, 0).y - 12)
        menu.aboveAnchor = true
        menu.open()
        Qt.callLater(function() {
            menu.x = Math.max(0, Math.min(p.x, inputRow.width - menu.width))
        })
    }
    Connections {
        target: controller
        ignoreUnknownSignals: true
        function onImagesChanged() { composer.imgUris = controller.pendingImageUris() }
        function onModeChanged() { composer.modeIndex = composer.modes.indexOf(controller.mode) }
        function onRestoreFailedDraft(t) {
            var current = inputArea.text
            if (current !== t && current.indexOf(t + "\n\n") !== 0)
                inputArea.text = current.trim().length > 0 ? t + "\n\n" + current : t
            inputArea.cursorPosition = inputArea.text.length
            inputArea.forceActiveFocus()
        }
        function onPrefillComposer(t) {
            if (controller && controller.setMode("Agent")) composer.modeIndex = 0
            inputArea.text = t
            inputArea.cursorPosition = inputArea.text.length
            inputArea.forceActiveFocus()
        }
    }
    ColumnLayout {
        id: col
        anchors.left: parent.left; anchors.right: parent.right; anchors.top: parent.top
        anchors.leftMargin: Theme.sp(16); anchors.rightMargin: Theme.sp(16)
        anchors.topMargin: Theme.sp(4)
        spacing: Theme.sp(8)
        Rectangle {
            id: pendingStrip
            Layout.fillWidth: true
            visible: controller && controller.pendingOps > 0
            implicitHeight: visible ? Theme.fs(34) : 0
            color: Theme.surface; radius: Theme.radSm
            RowLayout {
                anchors.fill: parent; anchors.leftMargin: 12; anchors.rightMargin: 7; spacing: 8
                Text {
                    Layout.fillWidth: true
                    text: (controller ? controller.pendingOps : 0) + composer.loc(" 个操作待确认")
                    color: Theme.textDim; font.family: Theme.fontBody; font.pixelSize: Theme.fXs
                }
                Pill { label: composer.loc("全部撤销"); onClicked: if (controller) controller.undoAll() }
                Pill { label: composer.loc("全部保留"); accent: true; onClicked: if (controller) controller.keepAll() }
            }
        }
        StatusBar { id: runStatus; Layout.fillWidth: true }
        QueuedMessages {
            id: queuedMessages
            Layout.fillWidth: true
            heightBudget: Math.min(Theme.fs(130), composer.availableHeightBudget * 0.22)
        }
        PanelScrollView {
            id: attachmentScroll
            objectName: "attachmentViewport"
            Layout.fillWidth: true
            Layout.preferredHeight: composer.attachmentHeight
            visible: composer.imgUris.length > 0
            contentWidth: availableWidth
            contentHeight: attachmentFlow.implicitHeight
            Flow {
                id: attachmentFlow
                width: attachmentScroll.availableWidth
                spacing: Theme.sp(8)
                Repeater {
                    model: composer.imgUris
                    delegate: Rectangle {
                        required property int index
                        required property string modelData
                        objectName: "attachmentThumbnail_" + index
                        width: Theme.fs(58); height: Theme.fs(58)
                        color: Theme.codeBg; radius: Theme.radSm
                        clip: true
                        ThumbnailImage { anchors.fill: parent; source: modelData }
                        MouseArea { anchors.fill: parent; cursorShape: Qt.PointingHandCursor; onClicked: { fullImg.src = modelData; fullImg.open() } }
                        IconButton {
                            objectName: "removeAttachment_" + index
                            circular: true
                            anchors.top: parent.top; anchors.right: parent.right
                            implicitWidth: 20; implicitHeight: 20; color: Theme.panel
                            icon: "close"; tooltip: composer.label("移除图片", "Remove image")
                            onClicked: if (controller) controller.removeImage(index)
                        }
                    }
                }
            }
        }
        Rectangle {
            id: inputRow
            objectName: "composerCard"
            Layout.fillWidth: true
            implicitHeight: inputLayout.implicitHeight + Theme.sp(16)
            color: Theme.inputBg
            radius: Theme.radLg
            border.width: 1
            border.color: dropArea.containsDrag ? Theme.accent
                        : inputArea.activeFocus ? Theme.border : Theme.borderSoft
            DropArea {
                id: dropArea; anchors.fill: parent
                onDropped: function(drop) {
                    if (drop.hasUrls && controller) {
                        for (var i = 0; i < drop.urls.length; i++) controller.attachImage("" + drop.urls[i])
                        drop.accept()
                    }
                }
            }
            ColumnLayout {
                id: inputLayout
                anchors.left: parent.left; anchors.right: parent.right; anchors.top: parent.top
                anchors.leftMargin: Theme.sp(12); anchors.rightMargin: Theme.sp(12); anchors.topMargin: Theme.sp(8)
                spacing: Theme.sp(6)
                PanelScrollView {
                    id: inputScroll
                    objectName: "messageInputScroll"
                    Layout.fillWidth: true
                    contentWidth: availableWidth
                    rightPadding: ScrollBar.vertical.implicitWidth + Theme.sp(3)
                    Layout.preferredHeight: Math.min(composer.inputHeightLimit, Math.max(Theme.fs(44), inputArea.contentHeight + 12))
                    clip: true
                    PanelTextArea {
                        id: inputArea
                        objectName: "messageInput"
                        width: inputScroll.availableWidth
                        wrapMode: TextArea.Wrap
                        placeholderText: composer.modeIndex === 1
                            ? composer.label("询问场景、参数或节点…", "Ask about your scene, parameters, or nodes…")
                            : composer.modeIndex === 2
                            ? composer.label("描述目标，先一起制定计划…", "Describe your goal. Start with a plan…")
                            : composer.label("描述任务，@ 引用节点，/ 查看命令", "Describe a task, @ mention a node, / for commands")
                        color: Theme.text; placeholderTextColor: Theme.textMute
                        font.family: Theme.fontBody; font.pixelSize: Theme.fBody
                        leftPadding: 4; rightPadding: 4; topPadding: 3; bottomPadding: 3
                        background: null
                        selectByMouse: true
                        Keys.onReturnPressed: function(e) {
                            if (completer.opened && completer.items.length > 0) {
                                composer.applyCompletion(completer.items[0].text); e.accepted = true; return
                            }
                            if (e.modifiers & Qt.ShiftModifier) { e.accepted = false; return }
                            e.accepted = true
                            composer.submit()
                        }
                        Keys.onPressed: function(e) {
                            if ((e.modifiers & Qt.ControlModifier) && e.key === Qt.Key_V) {
                                if (controller) controller.pasteImage()
                            } else if (e.key === Qt.Key_Escape) completer.close()
                        }
                        onTextChanged: composer.updateCompleter(text, cursorPosition)
                    }
                }
                GridLayout {
                    id: toolbar
                    objectName: "composerToolbar"
                    Layout.fillWidth: true
                    Layout.topMargin: Theme.sp(4)
                    columns: composer.compactToolbar ? 1 : 2
                    columnSpacing: Theme.sp(3); rowSpacing: Theme.sp(6)
                    RowLayout {
                        id: leadingControls
                        Layout.fillWidth: composer.compactToolbar
                        Layout.alignment: Qt.AlignLeft
                        spacing: Theme.sp(3)
                        IconButton {
                            objectName: "attachmentButton"
                            circular: true
                            Layout.alignment: Qt.AlignVCenter
                            icon: "plus"; tooltip: composer.label("添加图片", "Attach image")
                            onClicked: imgDialog.open()
                        }
                        Pill {
                            id: modeButton
                            objectName: "modeSelector"
                            label: composer.modes[composer.modeIndex]
                            Layout.fillWidth: true
                            Layout.minimumWidth: Math.min(Theme.fs(48), Math.max(0,
                                inputLayout.width - Theme.controlHeight - Theme.sp(3)))
                            Layout.maximumWidth: implicitWidth
                            caret: true; elideLabel: true
                            Layout.alignment: Qt.AlignVCenter
                            onClicked: {
                                modeMenu.items = composer.modes.map(function(m) { return {label: m, val: m, checked: m === composer.modes[composer.modeIndex]} })
                                composer.openMenu(modeButton, modeMenu)
                            }
                        }
                        IconButton {
                            objectName: "stopButton"
                            circular: true
                            visible: controller && controller.running && inputArea.text.trim().length > 0
                            icon: "stop"; tooltip: composer.label("停止并暂停队列", "Stop and pause queue")
                            onClicked: if (controller) controller.stop()
                        }
                    }
                    GridLayout {
                        id: trailingControls
                        Layout.fillWidth: true
                        readonly property bool stacked: inputLayout.width < Theme.controlHeight * 2 + 40 + 5 + Theme.sp(3) * 3
                        columns: stacked ? 2 : 4
                        columnSpacing: Theme.sp(3); rowSpacing: Theme.sp(6)
                        Item { visible: !trailingControls.stacked; Layout.row: 0; Layout.column: 0; Layout.fillWidth: true }
                        ContextUsage {
                            objectName: "contextUsage"
                            Layout.row: 0
                            Layout.column: trailingControls.stacked ? 0 : 1
                            Layout.columnSpan: trailingControls.stacked ? 2 : 1
                            Layout.alignment: trailingControls.stacked ? Qt.AlignRight | Qt.AlignVCenter : Qt.AlignVCenter
                        }
                        Pill {
                            id: modelButton
                            objectName: "modelSelector"
                            label: controller ? controller.modelDisplayName : "Model"
                            detail: !composer.compactToolbar && controller && controller.reasoningEffort.length > 0
                                ? controller.reasoningEffortLabel.split(" · ").pop() : ""
                            caret: true; elideLabel: true
                            Layout.alignment: Qt.AlignVCenter
                            Layout.row: trailingControls.stacked ? 1 : 0
                            Layout.column: trailingControls.stacked ? 0 : 2
                            Layout.fillWidth: true
                            Layout.minimumWidth: 40
                            Layout.maximumWidth: Math.min(modelButton.implicitWidth, Theme.fs(180),
                                                          Math.max(80, composer.width * 0.33))
                            onClicked: {
                                composer.openMenu(modelButton, modelMenu)
                            }
                        }
                        Rectangle {
                            id: sendButton
                            objectName: "sendButton"
                            property bool busy: controller ? controller.running : false
                            property bool ready: inputArea.text.trim().length > 0
                            readonly property bool stopAction: busy && !ready
                            Layout.preferredWidth: Theme.controlHeight; Layout.preferredHeight: Theme.controlHeight
                            Layout.alignment: Qt.AlignVCenter
                            Layout.row: trailingControls.stacked ? 1 : 0
                            Layout.column: trailingControls.stacked ? 1 : 3
                            Layout.leftMargin: 5
                            radius: width / 2
                            color: Theme.textBright
                            opacity: busy || ready ? 1 : 0.45
                            Accessible.role: Accessible.Button
                            Accessible.name: stopAction ? composer.label("停止", "Stop")
                                : busy ? composer.label("加入队列", "Queue message") : composer.label("发送", "Send")
                            AppIcon { anchors.centerIn: parent; visible: !sendButton.stopAction; name: "arrowUp"; color: Theme.bg; width: Theme.fs(19); height: width }
                            Rectangle { anchors.centerIn: parent; visible: sendButton.stopAction; width: Theme.fs(11); height: width; radius: 2; color: Theme.bg }
                            MouseArea {
                                anchors.fill: parent; cursorShape: Qt.PointingHandCursor
                                onClicked: {
                                    if (sendButton.stopAction && controller) controller.stop()
                                    else composer.submit()
                                }
                            }
                        }
                    }
                }
            }
        }
    }
    ModelPicker {
        id: modelMenu; objectName: "modelMenu"; parent: inputRow
        menuWidth: Math.min(Theme.fs(200), inputRow.width - Theme.sp(24))
    }
    MenuPopup {
        id: modeMenu; objectName: "modeMenu"; parent: inputRow; menuWidth: 150; checkable: true
        onPicked: function(val) {
            if (!controller || controller.setMode(val)) composer.modeIndex = composer.modes.indexOf(val)
        }
    }

    function submit() {
        var t = inputArea.text
        if (t.trim().length === 0) return
        completer.close()
        if (!controller || controller.send(t)) inputArea.text = ""
    }

    function updateCompleter(text, pos) {
        var before = text.substring(0, pos)
        var m = before.match(/([@/])([^\s@/]*)$/)
        if (!m) { completer.close(); return }
        var trig = m[1], pref = m[2].toLowerCase()
        var list = []
        if (trig === "@") {
            var nodes = controller ? controller.nodePaths() : []
            for (var i = 0; i < nodes.length; i++)
                if (nodes[i].toLowerCase().indexOf(pref) >= 0) { list.push({text: nodes[i], sub: ""}); if (list.length >= 20) break }
        } else {
            var cmds = controller ? controller.slashCommands() : []
            for (var j = 0; j < cmds.length; j++)
                if (pref === "" || cmds[j].cmd.indexOf("/" + pref) === 0) list.push({text: cmds[j].cmd, sub: cmds[j].desc})
        }
        if (list.length === 0) { completer.close(); return }
        completer.trig = trig
        completer.tokenStart = pos - m[2].length - 1
        completer.items = list
        completer.open()
    }

    function applyCompletion(val) {
        var text = inputArea.text, start = completer.tokenStart, end = inputArea.cursorPosition
        if (completer.trig === "/") {
            inputArea.text = text.substring(0, start) + text.substring(end)
            completer.close()
            if (controller) controller.runSlash(val)
            return
        }
        inputArea.text = text.substring(0, start) + val + " " + text.substring(end)
        inputArea.cursorPosition = start + val.length + 1
        completer.close()
    }

    Popup {
        id: completer
        property string trig: "@"
        property int tokenStart: 0
        property var items: []
        parent: inputRow
        x: 0; y: -height - 4; width: inputRow.width
        padding: 6
        closePolicy: Popup.NoAutoClose
        background: Rectangle { color: Theme.panel; border.color: Theme.border; border.width: 1; radius: Theme.radSm }
        contentItem: ListView {
            implicitHeight: Math.min(contentHeight, 180)
            clip: true
            model: completer.items
            delegate: Rectangle {
                required property var modelData
                width: ListView.view ? ListView.view.width : 200
                height: Math.round(26 * Theme.scale)
                radius: Theme.radSm
                color: hov.containsMouse ? Theme.surface : "transparent"
                Row {
                    anchors.fill: parent; anchors.leftMargin: 8; anchors.rightMargin: 8; spacing: 8
                    Text { anchors.verticalCenter: parent.verticalCenter; text: modelData.text; color: Theme.text
                        font.family: Theme.fontMono; font.pixelSize: Theme.fXs }
                    Text { anchors.verticalCenter: parent.verticalCenter; text: modelData.sub || ""; color: Theme.textMute
                        font.pixelSize: Theme.fMicro }
                }
                MouseArea { id: hov; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor
                    onClicked: composer.applyCompletion(modelData.text) }
            }
        }
    }

    Popup {
        id: fullImg
        objectName: "attachmentPreview"
        property string src: ""
        parent: Overlay.overlay
        anchors.centerIn: parent
        width: parent ? parent.width * 0.9 : 420
        height: parent ? parent.height * 0.9 : 420
        modal: true
        focus: true
        closePolicy: Popup.CloseOnPressOutside | Popup.CloseOnEscape
        background: Rectangle { color: Theme.panel; border.color: Theme.border; border.width: 1 }
        contentItem: Image {
            source: fullImg.src; fillMode: Image.PreserveAspectFit
            MouseArea { anchors.fill: parent; onClicked: fullImg.close() }
        }
    }

    FileDialog {
        id: imgDialog
        title: composer.loc("选择图片")
        nameFilters: ["Images (*.png *.jpg *.jpeg *.gif *.webp)"]
        onAccepted: if (controller) controller.attachImage("" + selectedFile)
    }
}
