import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import HAgent

// Lightweight themed dropdown. items: [{label, val, checked}]
Popup {
    id: pop
    property var items: []
    property bool checkable: false
    property int menuWidth: 178
    readonly property real viewportHeight: Overlay.overlay ? Overlay.overlay.height : 480
    property real maximumHeight: Math.max(120, viewportHeight - 32)
    property bool aboveAnchor: false
    y: aboveAnchor ? -height - 8 : 0
    signal picked(string val)
    height: Math.min(menuColumn.implicitHeight + topPadding + bottomPadding,
                     maximumHeight)

    padding: 6
    modal: false
    focus: true
    closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutside

    background: Rectangle {
        color: Theme.panel
        border.color: Theme.border
        border.width: 1
        radius: Theme.radMd
    }

    contentItem: Flickable {
        implicitWidth: pop.menuWidth
        implicitHeight: menuColumn.implicitHeight
        contentWidth: width
        contentHeight: menuColumn.implicitHeight
        clip: true
        boundsBehavior: Flickable.StopAtBounds
        ScrollBar.vertical: SmartScrollBar {}
        ColumnLayout {
            id: menuColumn
            width: parent.width
            spacing: 1
            Repeater {
                model: pop.items
                delegate: Rectangle {
                    id: rowItem
                    required property var modelData
                    objectName: "menuItem_" + (modelData.val || "separator")
                    property bool isSep: rowItem.modelData.sep === true
                    Layout.fillWidth: true
                    Layout.preferredWidth: pop.menuWidth
                    implicitHeight: isSep ? 9 : Math.round(30 * Theme.scale)
                    radius: Theme.radSm
                    color: (!isSep && hover.containsMouse) ? Theme.surface : "transparent"
                    Rectangle {
                        visible: rowItem.isSep
                        anchors.verticalCenter: parent.verticalCenter
                        anchors.left: parent.left; anchors.right: parent.right
                        anchors.leftMargin: 8; anchors.rightMargin: 8
                        height: 1; color: Theme.border
                    }
                    RowLayout {
                        visible: !rowItem.isSep
                        anchors.fill: parent
                        anchors.leftMargin: 10
                        anchors.rightMargin: 10
                        spacing: 8
                        Text {
                            Layout.fillWidth: true
                            text: rowItem.modelData.label || ""
                            color: rowItem.modelData.checked ? Theme.accent : Theme.text
                            font.family: Theme.fontBody
                            font.pixelSize: Theme.fSm
                            elide: Text.ElideRight
                        }
                        Text {
                            visible: (pop.checkable || rowItem.modelData.checked !== undefined) && rowItem.modelData.checked
                            text: "✓"
                            color: Theme.accent
                            font.family: Theme.fontMono
                            font.pixelSize: Theme.fSm
                        }
                    }
                    MouseArea {
                        id: hover
                        anchors.fill: parent
                        enabled: !rowItem.isSep
                        hoverEnabled: true
                        cursorShape: Qt.PointingHandCursor
                        onClicked: { pop.picked(rowItem.modelData.val); pop.close() }
                    }
                }
            }
        }
    }
}
