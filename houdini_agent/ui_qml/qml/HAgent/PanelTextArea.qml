import QtQuick
import QtQuick.Templates as T
import HAgent

// Stable placeholder geometry across Houdini Qt 6.8 and standalone Linux Qt.
// Basic's private PlaceholderText can recursively size wrapped ScrollView editors.
T.TextArea {
    id: editor
    implicitWidth: Theme.fs(120)
    implicitHeight: Math.max(contentHeight, hint.implicitHeight) + topPadding + bottomPadding
    padding: 6
    activeFocusOnPress: true
    focus: false
    leftPadding: 10
    color: Theme.text
    placeholderTextColor: Theme.textMute
    selectionColor: Theme.accent
    selectedTextColor: Theme.bg
    Text {
        id: hint
        x: editor.leftPadding; y: editor.topPadding
        width: Math.max(0, editor.width - editor.leftPadding - editor.rightPadding)
        text: editor.placeholderText
        font: editor.font
        color: editor.placeholderTextColor
        wrapMode: Text.NoWrap
        elide: Text.ElideRight
        visible: !editor.length && !editor.preeditText
        renderType: editor.renderType
    }
}
