import QtQuick
import QtQuick.Controls.Basic
import HAgent

// ScrollView's default style owns bar geometry; custom bars need it too.
ScrollView {
    id: view
    clip: true
    leftPadding: mirrored && ScrollBar.vertical.visible ? ScrollBar.vertical.width + Theme.sp(3) : 0
    rightPadding: !mirrored && ScrollBar.vertical.visible ? ScrollBar.vertical.width + Theme.sp(3) : 0
    ScrollBar.vertical: SmartScrollBar {
        parent: view
        x: view.mirrored ? 0 : view.width - width
        y: view.topPadding
        height: view.availableHeight
    }
    ScrollBar.horizontal: SmartScrollBar {
        parent: view
        x: view.leftPadding
        y: view.height - height
        width: view.availableWidth
        policy: ScrollBar.AlwaysOff
    }
}
