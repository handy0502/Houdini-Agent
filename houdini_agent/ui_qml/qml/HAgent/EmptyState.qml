import QtQuick
import QtQuick.Layouts
import HAgent

Item {
    id: empty
    implicitHeight: content.implicitHeight
    function loc(zh, en) { return controller && controller.lang === "en" ? en : zh }
    ColumnLayout {
        id: content
        width: parent.width
        spacing: 0
        Text {
            Layout.fillWidth: true
            text: empty.loc("你想在 Houdini 里做什么？", "What would you like to create?")
            color: Theme.textBright
            font.family: Theme.fontBody; font.pixelSize: Theme.fs(empty.width < 480 ? 24 : 28)
            font.weight: Font.DemiBold; horizontalAlignment: Text.AlignHCenter
            wrapMode: Text.Wrap
        }
        Text {
            Layout.fillWidth: true; Layout.topMargin: 12; Layout.bottomMargin: 32
            text: empty.loc("检查场景、搭建节点，或把一个想法变成作品。", "Explore your scene, build a network, or bring an idea to life.")
            color: Theme.textMute; font.family: Theme.fontBody; font.pixelSize: Theme.fSm
            horizontalAlignment: Text.AlignHCenter; wrapMode: Text.Wrap
        }
        Flow {
            Layout.fillWidth: true
            spacing: Theme.sp(10)
            Repeater {
                model: [
                    {icon: "search", zh: "检查当前场景", en: "Inspect the scene", sub: "了解节点结构与报错", enSub: "Understand nodes and errors",
                     prompt: "检查当前场景和选中的节点，解释节点网络并找出错误。", enPrompt: "Inspect my scene and selected nodes. Explain the network and identify errors."},
                    {icon: "cube", zh: "搭建节点网络", en: "Build a node network", sub: "从描述开始程序化建模", enSub: "Model procedurally from a prompt",
                     prompt: "在 /obj 下创建一个球体，添加噪声变形并整理节点布局。", enPrompt: "Create a sphere in /obj, add a noise deformation, and arrange the nodes."},
                    {icon: "spark", zh: "编写 VEX", en: "Write VEX", sub: "把几何处理想法变成代码", enSub: "Turn a geometry idea into code",
                     prompt: "读取选中的几何节点，用 VEX 根据高度生成一个颜色渐变。", enPrompt: "Read the selected geometry and use VEX to create a color gradient based on height."},
                    {icon: "folder", zh: "生成 3D 资产", en: "Generate a 3D asset", sub: "用 Meshy 生成并导入场景", enSub: "Create with Meshy and import it",
                     prompt: "用 Meshy 生成一个低多边形风格的石头喷泉，并导入 Houdini。", enPrompt: "Generate a low-poly stone fountain with Meshy and import it into Houdini."}
                ]
                delegate: Rectangle {
                    id: suggestion
                    required property var modelData
                    width: empty.width >= 520 ? (parent.width - Theme.sp(10)) / 2 : parent.width
                    height: Theme.fs(82)
                    radius: Theme.radMd
                    color: hover.containsMouse ? Theme.surface : "transparent"
                    RowLayout {
                        anchors.fill: parent; anchors.margins: Theme.sp(16); spacing: 13
                        AppIcon { name: suggestion.modelData.icon; color: Theme.textDim; Layout.alignment: Qt.AlignTop; Layout.topMargin: 3 }
                        ColumnLayout {
                            Layout.fillWidth: true; spacing: 5
                            Text {
                                Layout.fillWidth: true
                                text: empty.loc(suggestion.modelData.zh, suggestion.modelData.en)
                                color: Theme.text; font.family: Theme.fontBody; font.pixelSize: Theme.fSm
                                elide: Text.ElideRight
                            }
                            Text {
                                Layout.fillWidth: true
                                text: empty.loc(suggestion.modelData.sub, suggestion.modelData.enSub)
                                color: Theme.textMute; font.family: Theme.fontBody; font.pixelSize: Theme.fXs
                                elide: Text.ElideRight
                            }
                        }
                    }
                    MouseArea {
                        id: hover; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor
                        onClicked: if (controller) controller.insertTemplate(empty.loc(suggestion.modelData.prompt, suggestion.modelData.enPrompt))
                    }
                }
            }
        }
        Pill {
            Layout.alignment: Qt.AlignHCenter; Layout.topMargin: 20
            label: empty.loc("浏览提示词模板", "Browse prompt templates")
            onClicked: if (controller) controller.openTemplateLibrary()
        }
    }
}
