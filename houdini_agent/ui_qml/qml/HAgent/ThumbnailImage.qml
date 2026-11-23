import QtQuick
import HAgent

// Edge-to-edge reference image. Paint only the outside corner cutouts so the
// rounded silhouette also works with Qt Quick's software renderer.
Item {
    id: thumbnail
    property alias source: picture.source
    property alias asynchronous: picture.asynchronous
    property alias sourceSize: picture.sourceSize
    property real radius: Theme.radSm
    property color cornerColor: Theme.bg

    Image {
        id: picture
        anchors.fill: parent
        fillMode: Image.PreserveAspectCrop
        smooth: true
    }
    Canvas {
        id: corners
        anchors.fill: parent
        antialiasing: true
        onWidthChanged: requestPaint()
        onHeightChanged: requestPaint()
        Connections {
            target: thumbnail
            function onRadiusChanged() { corners.requestPaint() }
            function onCornerColorChanged() { corners.requestPaint() }
        }
        onPaint: {
            var c = getContext("2d")
            c.reset()
            c.clearRect(0, 0, width, height)
            var r = Math.max(0, Math.min(thumbnail.radius, width / 2, height / 2))
            if (!r) return
            c.fillStyle = thumbnail.cornerColor
            c.beginPath()
            c.moveTo(0, r); c.lineTo(0, 0); c.lineTo(r, 0)
            c.arc(r, r, r, -Math.PI / 2, -Math.PI, true); c.closePath()
            c.moveTo(width - r, 0); c.lineTo(width, 0); c.lineTo(width, r)
            c.arc(width - r, r, r, 0, -Math.PI / 2, true); c.closePath()
            c.moveTo(width, height - r); c.lineTo(width, height); c.lineTo(width - r, height)
            c.arc(width - r, height - r, r, Math.PI / 2, 0, true); c.closePath()
            c.moveTo(r, height); c.lineTo(0, height); c.lineTo(0, height - r)
            c.arc(r, height - r, r, Math.PI, Math.PI / 2, true); c.closePath()
            c.fill()
        }
    }
}
