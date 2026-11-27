import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import HAgent

Popup {
    id: dlg
    objectName: "actionDialog"
    property string mode: "info"
    property string dialogTitle: ""
    property string body: ""
    property string provider: ""
    property string confirmToken: ""
    property bool sessionDelete: false
    property bool anthropic: false
    property bool supportsVision: false
    function loc(s) { return controller ? (controller.lang, controller.tr(s)) : s }
    function openInfo(t, b) { mode = "info"; dialogTitle = t; body = b; open() }
    // 手动检查更新的对话框与侧栏更新按钮共用 startUpdate 入口。
    function openUpdate(t, b) { mode = "update"; dialogTitle = t; body = b; open() }
    function openApi(p) { mode = "api"; provider = p; dialogTitle = "API Key · " + p; apiField.text = ""; open() }
    function openConfirm(t, b, token) {
        mode = "confirm"; dialogTitle = t; body = b; confirmToken = token
        sessionDelete = !!controller && controller.isSessionDeleteConfirmation(token)
        dontAskDelete.checked = false
        open()
    }
    function openCustom(url, key, model, isAnthropic, contextLimit, visionFlag) {
        mode = "custom"; dialogTitle = "Custom Provider"
        urlField.text = url || ""; customKeyField.text = key || ""; modelField.text = model || ""
        contextField.text = contextLimit || "128000"
        anthropic = !!isAnthropic; supportsVision = !!visionFlag; open()
    }

    parent: Overlay.overlay
    anchors.centerIn: parent
    width: Math.min(420, parent ? parent.width - 36 : 420)
    padding: Theme.panelPadding
    modal: true
    focus: true
    closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutside
    onClosed: {
        if (mode === "custom" && controller) controller.cancelCustomProvider()
        if (mode === "confirm" && controller) controller.cancelDialogConfirm(confirmToken)
    }
    background: Rectangle { color: Theme.panel; border.color: Theme.border; border.width: 1; radius: Theme.radMd }

    contentItem: ColumnLayout {
        spacing: 14
        Text {
            Layout.fillWidth: true
            text: dlg.dialogTitle
            color: Theme.textBright
            font.family: Theme.fontDisplay; font.pixelSize: Theme.fLg; font.weight: Font.Medium
            wrapMode: Text.Wrap
        }
        Rectangle { Layout.fillWidth: true; height: 1; color: Theme.border }

        TextArea {
            visible: dlg.mode === "info" || dlg.mode === "update"
            Layout.fillWidth: true
            Layout.preferredHeight: Math.min(260, Math.max(90, contentHeight + 18))
            text: dlg.body
            readOnly: true
            wrapMode: TextArea.Wrap
            color: Theme.text
            selectedTextColor: Theme.bg
            selectionColor: Theme.accent
            font.family: Theme.fontBody; font.pixelSize: Theme.fSm
            background: Rectangle { color: Theme.surface; border.color: Theme.borderSoft; radius: Theme.radSm }
        }

        Text {
            visible: dlg.mode === "confirm"
            Layout.fillWidth: true
            text: dlg.body
            textFormat: Text.PlainText
            wrapMode: Text.Wrap
            color: Theme.err
            font.family: Theme.fontBody; font.pixelSize: Theme.fSm
        }

        ColumnLayout {
            visible: dlg.mode === "api"
            Layout.fillWidth: true
            spacing: 8
            Text { text: "API Key"; color: Theme.textDim; font.family: Theme.fontMono; font.pixelSize: Theme.fMicro }
            TextField {
                id: apiField
                Layout.fillWidth: true
                echoMode: TextInput.Password
                color: Theme.textBright
                placeholderText: "sk-..."
                placeholderTextColor: Theme.textMute
                font.family: Theme.fontMono; font.pixelSize: Theme.fSm
                background: Rectangle { color: Theme.surface; border.color: apiField.activeFocus ? Theme.accentLine : Theme.border; radius: Theme.radSm }
            }
        }

        ColumnLayout {
            visible: dlg.mode === "custom"
            Layout.fillWidth: true
            spacing: 10
            LabeledField { id: urlField; label: "API URL"; placeholder: "https://api.example.com/v1" }
            LabeledField { id: customKeyField; label: "API Key"; password: true; placeholder: "optional" }
            LabeledField { id: modelField; label: "Model"; placeholder: "model-name" }
            LabeledField { id: contextField; label: "Max context window"; placeholder: "128000" }
            RowLayout {
                spacing: 8
                Text { text: "Protocol"; color: Theme.textDim; font.family: Theme.fontMono; font.pixelSize: Theme.fMicro }
                Item { Layout.fillWidth: true }
                Pill { label: "OpenAI"; active: !dlg.anthropic; onClicked: dlg.anthropic = false }
                Pill { label: "Anthropic"; active: dlg.anthropic; onClicked: dlg.anthropic = true }
            }
            RowLayout {
                spacing: 8
                Text { text: dlg.loc("图片输入"); color: Theme.textDim; font.family: Theme.fontMono; font.pixelSize: Theme.fMicro }
                Item { Layout.fillWidth: true }
                Pill { label: dlg.loc("支持"); active: dlg.supportsVision; onClicked: dlg.supportsVision = true }
                Pill { label: dlg.loc("不支持"); active: !dlg.supportsVision; onClicked: dlg.supportsVision = false }
            }
        }

        CheckBox {
            id: dontAskDelete
            objectName: "dontAskDeleteSession"
            visible: dlg.mode === "confirm" && dlg.sessionDelete
            Layout.fillWidth: true
            Layout.minimumHeight: Theme.controlHeight
            text: dlg.loc("以后删除不再询问（可在 设置 › 会话 中恢复）")
            font.family: Theme.fontBody; font.pixelSize: Theme.fSm
            spacing: Theme.sp(8)
            indicator: Rectangle {
                implicitWidth: Theme.fs(18); implicitHeight: width
                x: dontAskDelete.leftPadding; y: (dontAskDelete.height - height) / 2
                radius: Theme.fs(4)
                color: dontAskDelete.checked ? Theme.switchOn : Theme.surface2
                AppIcon {
                    anchors.centerIn: parent
                    visible: dontAskDelete.checked
                    name: "check"; color: Theme.switchThumbOn
                    width: Theme.fs(13); height: width
                }
            }
            contentItem: Text {
                text: dontAskDelete.text; font: dontAskDelete.font; color: Theme.textDim
                leftPadding: dontAskDelete.indicator.width + dontAskDelete.spacing
                verticalAlignment: Text.AlignVCenter
                wrapMode: Text.Wrap
            }
        }

        RowLayout {
            Layout.fillWidth: true
            Item { Layout.fillWidth: true }
            Pill {
                label: dlg.loc("关闭")
                visible: dlg.mode === "info"
                accent: true
                onClicked: dlg.close()
            }
            Pill {
                label: dlg.loc("稍后")
                visible: dlg.mode === "update"
                onClicked: dlg.close()
            }
            Pill {
                label: dlg.loc("立即更新")
                // 只在可更新时出现；正在下载 / 等待 / 安装时点了也不会重复触发
                visible: dlg.mode === "update" && !!controller && controller.updateState === "available"
                accent: true
                onClicked: { if (controller) controller.startUpdate(); dlg.close() }
            }
            Pill {
                label: dlg.loc("取消")
                visible: dlg.mode !== "info" && dlg.mode !== "update"
                onClicked: { if (dlg.mode === "confirm" && controller) controller.cancelDialogConfirm(dlg.confirmToken); dlg.close() }
            }
            Pill {
                objectName: "confirmApiKeyButton"
                label: dlg.loc("确认")
                visible: dlg.mode === "api"
                accent: true
                onClicked: { if (!controller || controller.submitApiKey(dlg.provider, apiField.text)) dlg.close() }
            }
            Pill {
                objectName: "submitCustomDialog"
                label: dlg.loc("提交")
                visible: dlg.mode === "custom"
                accent: true
                onClicked: { if (!controller || controller.submitCustomProvider(urlField.text, customKeyField.text, modelField.text, dlg.anthropic, contextField.text, dlg.supportsVision)) dlg.close() }
            }
            Pill {
                objectName: "confirmDialogButton"
                label: dlg.loc("确认")
                visible: dlg.mode === "confirm"
                accent: true
                onClicked: {
                    if (controller) {
                        if (dlg.sessionDelete && dontAskDelete.checked) controller.setAskDeleteSession(false)
                        controller.acceptDialogConfirm(dlg.confirmToken)
                    }
                    dlg.close()
                }
            }
        }
    }
}
