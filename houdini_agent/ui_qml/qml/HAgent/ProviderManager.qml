import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import HAgent

Item {
    id: pm
    property bool active: true
    property var customs: []
    property var builtins: []
    property string editingId: ""
    readonly property bool editingBuiltin: editingId.indexOf("builtin:") === 0
    readonly property string editingKey: editingBuiltin ? editingId.slice(8) : "custom:" + editingId
    property bool editingSubscription: false
    property string fName: ""
    property string fUrl: ""
    property string fKey: ""
    property bool fAnthropic: false
    property bool keyDirty: false
    property bool formDirty: false
    property int formRevision: 0
    function markDirty() { formDirty = true; formRevision++ }
    property int statusRevision: 0
    readonly property color activeProviderColor: Theme.light ? "#2563eb" : "#60a5fa"
    function loc(s) { return controller ? (controller.lang, controller.tr(s)) : s }
    function reload() {
        if (!controller) return
        customs = controller.customProviderItems()
        builtins = controller.builtinProviderItems()
        statusRevision++
    }
    onActiveChanged: if (active) { editingId = ""; reload() }
    Component.onCompleted: if (active) reload()
    Connections {
        target: controller
        ignoreUnknownSignals: true
        function onCustomProvidersChanged() { pm.reload() }
        function onProviderChanged() { pm.reload() }
        function onModelsChanged() {
            pm.reload()
            if (pm.editingBuiltin) pm.loadModels(controller.providerConfiguration(pm.editingKey).models)
        }
        function onModelChanged() { pm.reload() }
        function onProviderStatusChanged() { pm.reload() }
        function onSubscriptionChanged() { pm.reload() }
        function onLangChanged() { pm.reload() }
    }
    function loadModels(models) {
        modelModel.clear()
        for (var i = 0; i < models.length; i++)
            modelModel.append({mname: models[i].name, ctx: "" + models[i].context, vis: !!models[i].vision})
    }
    function resetFormScroll() {
        Qt.callLater(function() { if (editScroll.contentItem) editScroll.contentItem.contentY = 0 })
    }
    function startAdd() {
        editingId = "new"; editingSubscription = false
        fName = ""; fUrl = ""; fKey = ""; fAnthropic = false; keyDirty = false; formDirty = true
        loadModels([{name: "", context: 128000, vision: false}])
        resetFormScroll()
    }
    function startEdit(p) {
        editingId = p.id; editingSubscription = false
        fName = p.name; fUrl = p.base_url || ""; fKey = p.api_key || ""; fAnthropic = !!p.anthropic
        keyDirty = false; formDirty = false; loadModels(p.models)
        resetFormScroll()
    }
    function startBuiltin(p) {
        editingId = "builtin:" + p.key
        var config = controller.providerConfiguration(p.key)
        editingSubscription = config.subscription
        fName = p.name; fKey = config.key_preview; keyDirty = false; formDirty = false
        loadModels(config.models)
        resetFormScroll()
    }
    function persistForm() {
        if (editingBuiltin) {
            if (keyDirty && !controller.submitApiKey(editingKey, fKey)) return false
        } else {
            var models = []
            for (var i = 0; i < modelModel.count; i++) {
                var r = modelModel.get(i)
                if (("" + r.mname).trim()) models.push({name: r.mname, context: parseInt(r.ctx) || 128000, vision: r.vis === true})
            }
            var payload = {id: editingId === "new" ? "" : editingId, name: fName, base_url: fUrl,
                           anthropic: fAnthropic, models: models}
            if (keyDirty || editingId === "new") payload.api_key = fKey
            var res = controller.saveCustomProvider(JSON.stringify(payload))
            if (!res || !res.ok) {
                controller.showToast(res && res.error ? res.error : loc("无效数据")); return false
            }
            if (res.id) editingId = res.id
        }
        keyDirty = false; formDirty = false
        // Keep only a masked preview in the form after saving.
        fKey = controller.providerConfiguration(editingKey).key_preview || ""
        reload(); return true
    }
    function submit() { if (persistForm()) { editingId = ""; controller.showToast(loc("已保存")) } }
    readonly property bool formReady: canVerifyForm()
    function canVerifyForm() {
        var revision = formRevision + statusRevision
        var hasModel = false
        for (var i = 0; i < modelModel.count; i++)
            if (String(modelModel.get(i).mname).trim()) hasModel = true
        if (!hasModel) return false
        if (editingBuiltin) {
            if (!editingSubscription && keyDirty) return fKey.trim().length > 0
            return controller && controller.providerStatus(editingKey).configured
        }
        return fName.trim().length > 0 && /^https?:\/\/[^/\s]+/.test(fUrl.trim())
    }
    function verifyForm() {
        if (!formReady || !controller || controller.running) return
        if (formDirty && !persistForm()) return
        controller.verifyProvider(editingKey)
    }
    readonly property var configurationStatus: currentConfigurationStatus()
    function currentConfigurationStatus() {
        var revision = statusRevision
        if (formDirty) return {state: "unverified", configured: false, stateLabel: loc("配置已修改，可直接验证")}
        return controller ? controller.providerStatus(editingKey) : ({state: "missing", configured: false})
    }
    function statusColor(state) {
        return state === "ok" ? Theme.switchOn : state === "missing" || state === "error" || state === "busy" ? Theme.err : Theme.warn
    }
    ListModel { id: modelModel }

    component ProviderRow: Rectangle {
        id: entry
        property var item: ({})
        property bool custom: false
        readonly property string key: custom ? "custom:" + item.id : item.key
        HoverHandler { id: entryHover }
        Layout.fillWidth: true; Layout.bottomMargin: Theme.sp(6)
        implicitHeight: Theme.controlHeight + Theme.sp(16)
        radius: Theme.radMd; color: item.active ? Theme.surface2 : Theme.surface
        RowLayout {
            anchors.fill: parent; anchors.margins: Theme.sp(8); spacing: Theme.sp(8)
            Rectangle {
                objectName: "providerDot_" + entry.key
                width: Theme.fs(6); height: width; radius: width / 2
                color: entry.item.active ? pm.activeProviderColor : pm.statusColor(entry.item.state || "missing")
            }
            Text {
                Layout.fillWidth: true; Layout.minimumWidth: 0
                text: entry.item.name || ""; elide: Text.ElideRight
                color: Theme.textBright; font.family: Theme.fontBody; font.pixelSize: Theme.fSm
            }
            Item {
                Layout.preferredWidth: Math.max(currentLabel.implicitWidth, useProvider.implicitWidth)
                Layout.preferredHeight: Theme.controlHeight
                Text {
                    id: currentLabel
                    objectName: "providerCurrent_" + entry.key
                    anchors.centerIn: parent
                    visible: !!entry.item.active; text: pm.loc("当前使用")
                    color: Theme.textDim; font.family: Theme.fontBody; font.pixelSize: Theme.fXs
                }
                Pill {
                    id: useProvider
                    objectName: "providerUse_" + entry.key
                    anchors.centerIn: parent
                    visible: !entry.item.active && entryHover.hovered
                    label: pm.loc("使用")
                    enabled: !!entry.item.configured && controller && !controller.running
                    opacity: enabled ? 1 : 0.4
                    onClicked: controller.selectProviderModel(entry.key, "")
                }
            }
            Pill {
                objectName: "providerConfig_" + entry.key
                label: pm.loc("配置")
                onClicked: if (entry.custom) pm.startEdit(entry.item); else pm.startBuiltin(entry.item)
            }
        }
    }
    // 小工具组件
    component Field: Rectangle {
        id: fieldRoot
        property alias text: inp.text
        property string placeholder: ""
        property bool password: false
        // 仅在用户实际编辑时触发；用它做写回可避免与 text: <model> 的绑定形成回环。
        signal textEdited()
        implicitWidth: Math.round(120 * Theme.scale)
        implicitHeight: Theme.fieldHeight
        radius: Theme.radSm; color: Theme.fieldBg
        border.width: 1; border.color: inp.activeFocus ? Theme.accentLine : Theme.border
        TextField {
            id: inp
            objectName: fieldRoot.objectName + "_input"
            anchors.fill: parent
            leftPadding: Theme.fs(10); rightPadding: Theme.fs(10)
            verticalAlignment: TextInput.AlignVCenter
            echoMode: parent.password ? TextInput.Password : TextInput.Normal
            placeholderText: parent.placeholder
            placeholderTextColor: Theme.textMute
            color: Theme.text
            font.family: Theme.fontBody; font.pixelSize: Theme.fSm
            background: null
            onTextEdited: fieldRoot.textEdited()
            onActiveFocusChanged: if (activeFocus && fieldRoot.password && text === "••••••••") selectAll()
        }
    }
    component FieldLabel: Text {
        color: Theme.textDim; font.family: Theme.fontBody; font.pixelSize: Theme.fXs
        bottomPadding: Theme.sp(6); topPadding: Theme.sp(12)
    }
    component MiniToggle: ToggleSwitch {}


    PanelScrollView {
        id: providerScroll
        objectName: "providerListScroll"
        anchors.fill: parent; visible: pm.editingId === ""; clip: true
        contentWidth: availableWidth
        // 供应商列表是面板打开后才填进来的，ScrollView 不会自己重新测量
        contentImplicitHeight: providerColumn.implicitHeight
        ColumnLayout {
            id: providerColumn
            width: providerScroll.availableWidth; spacing: 0
            Text {
                Layout.fillWidth: true; Layout.bottomMargin: Theme.sp(14)
                text: pm.loc("进入配置页管理账号、模型和验证")
                color: Theme.textMute; font.family: Theme.fontBody; font.pixelSize: Theme.fSm; wrapMode: Text.Wrap
            }
            Text {
                text: pm.loc("内置供应商"); color: Theme.textMute; bottomPadding: Theme.sp(8)
                font.family: Theme.fontMono; font.pixelSize: Theme.fMicro
            }
            Repeater {
                model: pm.builtins
                delegate: ProviderRow { required property var modelData; item: modelData }
            }
            Text {
                text: pm.loc("自定义供应商"); color: Theme.textMute; topPadding: Theme.sp(18); bottomPadding: Theme.sp(8)
                font.family: Theme.fontMono; font.pixelSize: Theme.fMicro
            }
            Repeater {
                model: pm.customs
                delegate: ProviderRow { required property var modelData; item: modelData; custom: true }
            }
            Pill { objectName: "addProviderButton"; Layout.alignment: Qt.AlignHCenter
                label: "+ " + pm.loc("添加供应商"); onClicked: pm.startAdd() }
        }
    }

    ColumnLayout {
        anchors.fill: parent; visible: pm.editingId !== ""; spacing: Theme.sp(8)
        RowLayout {
            Layout.fillWidth: true
            Text {
                Layout.fillWidth: true; text: pm.editingId === "new" ? pm.loc("添加模型供应商") : pm.fName
                color: Theme.textBright; font.family: Theme.fontDisplay; font.pixelSize: Theme.fLg; elide: Text.ElideRight
            }
            IconButton { objectName: "backFromProviderConfig"; icon: "arrowLeft"; circular: true
                tooltip: pm.loc("返回"); onClicked: pm.editingId = "" }
        }
        PanelScrollView {
            id: editScroll
            objectName: "providerConfigScroll"
            Layout.fillWidth: true; Layout.fillHeight: true; clip: true; contentWidth: availableWidth
            // 表单随模型数量/订阅态增减字段，同样需要显式同步内容高度
            contentImplicitHeight: editColumn.implicitHeight
            ColumnLayout {
                id: editColumn
                width: editScroll.availableWidth; spacing: 0
                FieldLabel { visible: !pm.editingBuiltin; text: pm.loc("名称") }
                Field { objectName: "providerNameField"; visible: !pm.editingBuiltin; Layout.fillWidth: true; text: pm.fName
                    onTextEdited: { pm.fName = text; pm.markDirty() } }
                FieldLabel { visible: !pm.editingBuiltin; text: "Base URL" }
                Field { objectName: "providerUrlField"; visible: !pm.editingBuiltin; Layout.fillWidth: true; text: pm.fUrl; placeholder: "https://api.example.com/v1"
                    onTextEdited: { pm.fUrl = text; pm.markDirty() } }
                FieldLabel { visible: !pm.editingSubscription; text: "API Key" }
                Field {
                    objectName: "providerKeyField"
                    visible: !pm.editingSubscription; Layout.fillWidth: true
                    text: pm.fKey; placeholder: "sk-..."; password: true
                    onTextEdited: { pm.fKey = text; pm.keyDirty = true; pm.markDirty() }
                }
                Pill {
                    visible: pm.editingSubscription; label: pm.loc("订阅登录")
                    onClicked: controller.openProviderApiKey(pm.editingKey)
                }
                FieldLabel { visible: !pm.editingBuiltin; text: pm.loc("API 格式") }
                RowLayout {
                    visible: !pm.editingBuiltin; Layout.fillWidth: true
                    Pill { label: "OpenAI"; active: !pm.fAnthropic
                        onClicked: { pm.fAnthropic = false; pm.markDirty() } }
                    Pill { label: "Anthropic"; active: pm.fAnthropic
                        onClicked: { pm.fAnthropic = true; pm.markDirty() } }
                }
                RowLayout {
                    Layout.fillWidth: true; Layout.topMargin: Theme.sp(12)
                    Text {
                        objectName: "configProviderStatus"
                        Layout.fillWidth: true; wrapMode: Text.Wrap
                        text: pm.configurationStatus.stateLabel || ""
                        color: pm.statusColor(pm.configurationStatus.state)
                        font.family: Theme.fontBody; font.pixelSize: Theme.fXs
                    }
                    Pill {
                        objectName: "verifyConfigProvider"
                        filled: true
                        label: pm.configurationStatus.state === "ok" ? pm.loc("已验证") : pm.loc("验证")
                        enabled: controller && !controller.running && pm.formReady &&
                            pm.configurationStatus.state !== "checking" && pm.configurationStatus.state !== "ok"
                        opacity: enabled ? 1 : 0.4
                        onClicked: pm.verifyForm()
                    }
                }
                RowLayout {
                    Layout.fillWidth: true; Layout.topMargin: Theme.sp(12)
                    FieldLabel { Layout.fillWidth: true; text: pm.loc("模型列表") }
                    Pill { visible: pm.editingBuiltin; label: pm.loc("刷新模型")
                        enabled: controller && !controller.modelsRefreshing
                        onClicked: controller.refreshModels() }
                }
                Text {
                    Layout.fillWidth: true; Layout.bottomMargin: Theme.sp(10)
                    text: pm.loc("每个供应商仅使用第一个模型验证一次，配置不变时复用结果")
                    wrapMode: Text.Wrap; color: Theme.textMute; font.family: Theme.fontBody; font.pixelSize: Theme.fXs
                }
                Repeater {
                    model: modelModel
                    delegate: Rectangle {
                        id: modelCard
                        required property int index
                        required property var model
                        objectName: "providerModelRow_" + index
                        Layout.fillWidth: true; Layout.bottomMargin: Theme.sp(8)
                        implicitHeight: modelContent.implicitHeight + Theme.sp(16)
                        radius: Theme.radMd; color: Theme.surface
                        ColumnLayout {
                            id: modelContent
                            anchors.left: parent.left; anchors.right: parent.right; anchors.top: parent.top
                            anchors.margins: Theme.sp(8); spacing: Theme.sp(8)
                            Text {
                                visible: pm.editingBuiltin; Layout.fillWidth: true
                                text: controller ? controller.modelNameLabel(model.mname) : model.mname
                                color: Theme.text; font.family: Theme.fontBody; font.pixelSize: Theme.fSm
                            }
                            Field {
                                visible: !pm.editingBuiltin; objectName: "providerModelName_" + index
                                Layout.fillWidth: true; text: model.mname; placeholder: pm.loc("模型名")
                                onTextEdited: { modelModel.setProperty(index, "mname", text); pm.markDirty() }
                            }
                            GridLayout {
                                visible: !pm.editingBuiltin; Layout.fillWidth: true; columns: 3; columnSpacing: Theme.sp(8)
                                ColumnLayout {
                                    Layout.fillWidth: true
                                    Text { text: pm.loc("上下文窗口"); color: Theme.textDim; font.pixelSize: Theme.fXs }
                                    Field { Layout.fillWidth: true; text: model.ctx
                                        onTextEdited: { modelModel.setProperty(index, "ctx", text); pm.markDirty() } }
                                }
                                ColumnLayout {
                                    Text { text: pm.loc("图片"); color: Theme.textDim; font.pixelSize: Theme.fXs }
                                    MiniToggle {
                                        objectName: "providerVisionToggle_" + index
                                        Accessible.name: pm.loc("支持图片输入"); Layout.preferredHeight: Theme.fieldHeight
                                        on: model.vis === true
                                        onToggled: { modelModel.setProperty(index, "vis", checked); pm.markDirty() }
                                    }
                                }
                                IconButton { objectName: "removeProviderModel_" + index
                                    Layout.alignment: Qt.AlignBottom; icon: "close"; tooltip: pm.loc("移除模型"); circular: true
                                    onClicked: { if (modelModel.count > 1) modelModel.remove(index)
                                                 else modelModel.setProperty(index, "mname", "")
                                                 pm.markDirty() }
                                }
                            }

                        }
                    }
                }
                Pill { visible: !pm.editingBuiltin; label: "+ " + pm.loc("添加模型")
                    onClicked: { modelModel.append({mname: "", ctx: "128000", vis: false}); pm.markDirty() } }
            }
        }
        RowLayout {
            Layout.fillWidth: true; spacing: Theme.sp(8)
            Item { Layout.fillWidth: true }
            Pill { objectName: "deleteProviderButton"; filled: true
                visible: !pm.editingBuiltin && pm.editingId !== "new"; label: pm.loc("删除")
                onClicked: { controller.deleteCustomProvider(pm.editingId); pm.editingId = ""; pm.reload() } }
            Pill { objectName: "saveProviderButton"; label: pm.loc("保存"); filled: true; accent: true; onClicked: pm.submit() }
        }
    }
}
