import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import HAgent

// One popover owns both model selection and that model's supported effort range.
Popup {
    id: picker
    property var items: []
    property var effortOptions: []
    property bool modelListExpanded: false
    property real menuWidth: Theme.fs(200)
    property real maximumHeight: Math.max(120, viewportHeight - 32)
    readonly property real viewportHeight: Overlay.overlay ? Overlay.overlay.height : 480
    property bool aboveAnchor: true
    readonly property bool hasEffort: effortOptions.length > 0
    readonly property int effortIndex: {
        var current = controller ? controller.reasoningEffort : ""
        for (var i = 0; i < effortOptions.length; i++) if (effortOptions[i].val === current) return i
        return 0
    }
    function loc(zh, en) { return controller && controller.lang === "en" ? en : zh }
    function refresh() {
        items = controller ? controller.modelItems() : []
        effortOptions = controller ? controller.effortItems() : []
    }
    function chooseModel(value) {
        if (!controller) return
        // A model change refreshes the list and destroys its delegate. Finish
        // the action in the popup's stable context rather than in that row.
        controller.setModel(value)
        refresh()
        if (!hasEffort || String(value).indexOf("__") === 0) close()
        else modelListExpanded = false
    }
    onAboutToShow: {
        refresh()
        modelListExpanded = !hasEffort
    }
    Connections {
        target: controller
        ignoreUnknownSignals: true
        function onModelChanged() { if (picker.opened) picker.refresh() }
        function onProviderChanged() { if (picker.opened) picker.refresh() }
        function onEffortChanged() { if (picker.opened) picker.refresh() }
        function onLangChanged() { if (picker.opened) picker.refresh() }
        function onModelsChanged() { if (picker.opened) picker.refresh() }
    }
    y: aboveAnchor ? -height - 8 : 0
    width: menuWidth + leftPadding + rightPadding
    height: Math.min(body.implicitHeight + topPadding + bottomPadding, maximumHeight)
    padding: Theme.sp(12)
    modal: false
    focus: true
    closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutside
    background: Rectangle { color: Theme.panel; radius: Theme.radLg; border.width: 1; border.color: Theme.border }

    contentItem: ColumnLayout {
        id: body
        spacing: Theme.sp(10)
        clip: true
        ColumnLayout {
            id: effortPanel
            visible: picker.hasEffort
            Layout.fillWidth: true
            spacing: Theme.sp(14)
            Item {
                Layout.fillWidth: true
                implicitHeight: Theme.fs(58)
                AppIcon { anchors.left: parent.left; anchors.top: parent.top; anchors.topMargin: 6; name: "spark"; color: Theme.textBright }
                ColumnLayout {
                    anchors.top: parent.top; anchors.left: parent.left; anchors.right: parent.right
                    anchors.leftMargin: Theme.fs(30); anchors.rightMargin: Theme.fs(30)
                    spacing: 0
                    Text {
                        Layout.fillWidth: true
                        text: controller ? controller.reasoningEffortLabel.split(" · ").pop() : ""
                        color: Theme.textBright; font.family: Theme.fontBody
                        font.pixelSize: Theme.fs(20); font.weight: Font.DemiBold
                        horizontalAlignment: Text.AlignHCenter
                    }
                    Pill {
                        id: modelChoice
                        objectName: "pickerModelSelector"
                        Layout.alignment: Qt.AlignHCenter
                        Layout.maximumWidth: parent.width
                        label: controller ? controller.modelDisplayName : ""
                        caret: true; elideLabel: true
                        onClicked: picker.modelListExpanded = !picker.modelListExpanded
                    }
                }
                IconButton {
                    objectName: "resetEffortButton"
                    anchors.right: parent.right; anchors.top: parent.top
                    icon: "refresh"; circular: true
                    tooltip: picker.loc("恢复默认推理强度", "Reset reasoning effort")
                    enabled: !controller || !controller.running
                    onClicked: if (controller) controller.resetReasoningEffort()
                }
            }
            Slider {
                id: effortSlider
                objectName: "effortSlider"
                Layout.fillWidth: true
                Layout.preferredHeight: Theme.controlHeight
                from: 0
                to: Math.max(0, picker.effortOptions.length - 1)
                stepSize: 1
                snapMode: Slider.SnapAlways
                value: Math.max(from, Math.min(to, picker.effortIndex))
                enabled: picker.effortOptions.length > 1 && (!controller || !controller.running)
                Accessible.name: picker.loc("推理强度", "Reasoning effort")
                onMoved: {
                    var index = Math.round(value)
                    if (controller && picker.effortOptions[index]) controller.setReasoningEffort(picker.effortOptions[index].val)
                }
                background: Rectangle {
                    x: effortSlider.leftPadding
                    y: effortSlider.topPadding + (effortSlider.availableHeight - height) / 2
                    width: effortSlider.availableWidth
                    height: Theme.fs(25)
                    radius: height / 2
                    color: Theme.surface2
                    Rectangle {
                        height: parent.height
                        width: Math.min(parent.width, parent.height + effortSlider.visualPosition * (parent.width - parent.height))
                        radius: height / 2
                        color: Theme.textBright
                    }
                    Repeater {
                        model: picker.effortOptions.length
                        delegate: Rectangle {
                            required property int index
                            x: parent.height / 2 + index * (parent.width - parent.height) / Math.max(1, picker.effortOptions.length - 1) - width / 2
                            anchors.verticalCenter: parent.verticalCenter
                            width: Theme.fs(4); height: width; radius: width / 2
                            color: index <= effortSlider.value ? "transparent" : Theme.textMute
                        }
                    }
                }
                handle: Rectangle {
                    x: effortSlider.leftPadding + effortSlider.visualPosition * (effortSlider.availableWidth - width)
                    y: effortSlider.topPadding + (effortSlider.availableHeight - height) / 2
                    width: Theme.controlHeight; height: width; radius: width / 2
                    color: Theme.textBright
                }
            }
        }
        Rectangle { visible: picker.hasEffort && modelList.visible; Layout.fillWidth: true; height: 1; color: Theme.borderSoft }
        ListView {
            id: modelList
            objectName: "pickerModelList"
            visible: picker.modelListExpanded || !picker.hasEffort
            Layout.fillWidth: true
            Layout.preferredHeight: Math.min(contentHeight,
                Math.max(Theme.fs(45), picker.maximumHeight - (picker.hasEffort ? effortPanel.implicitHeight + Theme.sp(22) : 0) - picker.topPadding - picker.bottomPadding))
            model: picker.items
            clip: true
            onVisibleChanged: if (visible) Qt.callLater(function() { modelList.positionViewAtBeginning() })
            boundsBehavior: Flickable.StopAtBounds
            ScrollBar.vertical: SmartScrollBar {}
            delegate: Rectangle {
                id: option
                required property var modelData
                objectName: "menuItem_" + (modelData.val || "separator")
                readonly property bool separator: modelData.sep === true
                width: ListView.view.width
                height: separator ? 9 : Theme.controlHeight
                radius: Theme.radSm
                color: hover.containsMouse && !separator ? Theme.surface : "transparent"
                Rectangle { visible: option.separator; anchors.verticalCenter: parent.verticalCenter; width: parent.width; height: 1; color: Theme.borderSoft }
                RowLayout {
                    visible: !option.separator
                    anchors.fill: parent; anchors.leftMargin: 10; anchors.rightMargin: 10; spacing: 8
                    Text {
                        Layout.fillWidth: true; text: option.modelData.label || ""
                        elide: Text.ElideRight; color: option.modelData.checked ? Theme.textBright : Theme.textDim
                        font.family: Theme.fontBody; font.pixelSize: Theme.fSm
                    }
                    Text { visible: !!option.modelData.checked; text: "✓"; color: Theme.textBright; font.family: Theme.fontBody; font.pixelSize: Theme.fSm }
                }
                MouseArea {
                    id: hover; anchors.fill: parent; hoverEnabled: true
                    enabled: !option.separator && (!controller || !controller.running)
                    cursorShape: Qt.PointingHandCursor
                    onClicked: picker.chooseModel(option.modelData.val)
                }
            }
        }
    }
}
