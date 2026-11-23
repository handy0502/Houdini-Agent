import QtQuick
import HAgent

// Small vector icons drawn at the current scale, without a symbol font.
Canvas {
    id: icon
    property string name: "chat"
    property color color: Theme.textDim
    implicitWidth: Theme.fs(18)
    implicitHeight: Theme.fs(18)
    onNameChanged: requestPaint()
    onColorChanged: requestPaint()
    onWidthChanged: requestPaint()
    onHeightChanged: requestPaint()
    onPaint: {
        var c = getContext("2d")
        c.reset()
        c.scale(width / 24, height / 24)
        c.strokeStyle = color
        c.lineWidth = 1.65
        c.lineCap = "round"
        c.lineJoin = "round"
        function line(x, y, a, b) { c.moveTo(x, y); c.lineTo(a, b) }
        c.beginPath()
        if (name === "sidebar") {
            c.roundedRect(3, 4, 18, 16, 2, 2); line(9, 4, 9, 20)
        } else if (name === "plus") {
            line(12, 5, 12, 19); line(5, 12, 19, 12)
        } else if (name === "search") {
            c.arc(10.5, 10.5, 6, 0, Math.PI * 2); line(15, 15, 20, 20)
        } else if (name === "arrowUp") {
            line(12, 19, 12, 5); line(6, 11, 12, 5); line(12, 5, 18, 11)
        } else if (name === "arrowLeft") {
            line(19, 12, 5, 12); line(11, 6, 5, 12); line(5, 12, 11, 18)
        } else if (name === "chevronDown") {
            line(7, 10, 12, 15); line(12, 15, 17, 10)
        } else if (name === "close") {
            line(6, 6, 18, 18); line(18, 6, 6, 18)
        } else if (name === "copy") {
            c.roundedRect(8, 8, 12, 13, 2, 2)
            c.moveTo(6, 16); c.lineTo(4, 16); c.lineTo(4, 3); c.lineTo(16, 3); c.lineTo(16, 5)
        } else if (name === "check") {
            line(5, 12, 10, 17); line(10, 17, 19, 7)
        } else if (name === "minus") {
            line(5, 12, 19, 12)
        } else if (name === "more") {
            for (var i = 0; i < 3; i++) { c.moveTo(6 + i * 6, 12); c.arc(6 + i * 6, 12, 0.8, 0, Math.PI * 2) }
        } else if (name === "cube") {
            line(12, 3, 21, 8); line(21, 8, 21, 17); line(21, 17, 12, 22)
            line(12, 22, 3, 17); line(3, 17, 3, 8); line(3, 8, 12, 3)
            line(3, 8, 12, 13); line(12, 13, 21, 8); line(12, 13, 12, 22)
        } else if (name === "gear") {
            for (var g = 0; g < 32; g++) {
                var radius = (g % 4 === 1 || g % 4 === 2) ? 9 : 7
                var angle = -Math.PI / 2 + g * Math.PI / 16
                var gx = 12 + radius * Math.cos(angle), gy = 12 + radius * Math.sin(angle)
                if (g === 0) c.moveTo(gx, gy)
                else c.lineTo(gx, gy)
            }
            c.closePath()
            c.moveTo(15, 12); c.arc(12, 12, 3, 0, Math.PI * 2)
        } else if (name === "settings") {
            line(4, 7, 20, 7); line(4, 17, 20, 17)
            c.moveTo(11, 7); c.arc(8, 7, 3, 0, Math.PI * 2)
            c.moveTo(19, 17); c.arc(16, 17, 3, 0, Math.PI * 2)
        } else if (name === "folder") {
            c.moveTo(3, 7); c.lineTo(3, 19); c.lineTo(21, 19); c.lineTo(21, 7)
            c.lineTo(12, 7); c.lineTo(10, 4); c.lineTo(3, 4); c.lineTo(3, 7)
        } else if (name === "refresh") {
            c.arc(12, 12, 7, -Math.PI * 0.8, Math.PI * 0.85)
            line(5, 4, 5, 9); line(5, 9, 10, 9)
        } else if (name === "spark") {
            line(12, 3, 14.5, 9.5); line(14.5, 9.5, 21, 12)
            line(21, 12, 14.5, 14.5); line(14.5, 14.5, 12, 21)
            line(12, 21, 9.5, 14.5); line(9.5, 14.5, 3, 12)
            line(3, 12, 9.5, 9.5); line(9.5, 9.5, 12, 3)
        } else {
            c.roundedRect(3, 4, 18, 14, 3, 3); line(8, 18, 5, 21); line(5, 21, 5, 18)
        }
        c.stroke()
    }
}
