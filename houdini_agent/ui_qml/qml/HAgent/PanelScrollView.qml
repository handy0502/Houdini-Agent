import QtQuick
import QtQuick.Controls.Basic
import HAgent

// ScrollView's default style owns bar geometry; custom bars need it too.
ScrollView {
    id: view
    clip: true

    // Qt 的 ScrollView 只在内容项挂载那一刻量一次 contentHeight。供应商列表、规则列表
    // 这类“面板打开后才填进来”的内容变高后不会被重新测量：contentHeight 停在空列表的
    // 高度，滚动条（size 恒为 1）永远不出现，底部内容只能被裁掉。
    //
    // 页面把内容根节点的 implicitHeight 接到这里；这里用命令式方式同步 contentHeight。
    // 不能用 `contentHeight: ...` 绑定：contentHeight 会改变 ScrollView 的 implicitHeight，
    // 进而影响父布局/弹窗尺寸，再回到 availableHeight，Qt 会判成 binding loop。
    property real contentImplicitHeight: 0
    property bool _syncing: false
    function syncContentHeight() {
        // 没接 contentImplicitHeight 的页面维持 Qt 原来的行为（挂载时同步一次）
        if (_syncing || contentImplicitHeight <= 0)
            return
        var target = Math.max(availableHeight, contentImplicitHeight)
        if (Math.abs(contentHeight - target) < 0.5)
            return
        _syncing = true
        contentHeight = target
        _syncing = false
    }
    onContentImplicitHeightChanged: {
        syncContentHeight()
        // 布局可能还没稳定（宽度、换行会让 implicitHeight 再变一次），下一帧再校一次
        Qt.callLater(syncContentHeight)
    }
    onAvailableHeightChanged: syncContentHeight()
    Component.onCompleted: syncContentHeight()

    // 滚动条槽位固定预留。改成“按滚动条显隐动态加 padding”时，内容宽度会随滚动条出现
    // 而变化，自动换行再改变内容高度，同步 contentHeight 时容易拿到中间态（实测
    // 设置页 contentHeight 会虚高 50%），滚动条位置也会跟着漂。
    readonly property int barGutter: Math.max(7, Math.round(7 * Theme.scale)) + Theme.sp(3)
    leftPadding: mirrored ? barGutter : 0
    rightPadding: mirrored ? 0 : barGutter
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
