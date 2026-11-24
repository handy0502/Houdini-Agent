import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import HAgent

// 统一设置浮窗（第一版）：左侧分类导航 + 右侧内容。大量复用 controller.menuAction 既有派发，
// 把散落在 ⋯ 菜单里的设置归并到一处。窄面板自适应缩放。
Popup {
    id: win
    objectName: "settingsWindow"
    function loc(s) { return controller ? (controller.lang, controller.tr(s)) : s }

    property string sec: "general"
    function action(value) {
        // Configuration dialogs keep this page behind them. Only actions that
        // intentionally return to the conversation dismiss the settings page.
        if (value === "library" || value === "clear") win.close()
        if (controller) controller.menuAction(value)
    }
    readonly property bool compact: width < Theme.fs(620)

    parent: Overlay.overlay
    anchors.centerIn: parent
    width: Math.min(Math.round(720 * Theme.scale), parent ? parent.width - 18 : 720)
    height: Math.min(Math.round(560 * Theme.scale), parent ? parent.height - 18 : 560)
    padding: 0
    modal: true
    focus: true
    closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutside
    background: Rectangle { color: Theme.panel; border.color: Theme.border; border.width: 1; radius: Theme.radMd }

    // ---- reusable inline pieces ----
    component Toggle: ToggleSwitch {}

    component FieldRow: ColumnLayout {
        property string name: ""
        property string desc: ""
        default property alias content: slot.data
        Layout.fillWidth: true
        spacing: 0
        GridLayout {
            id: fieldGrid
            Layout.fillWidth: true
            Layout.topMargin: Theme.sp(14); Layout.bottomMargin: Theme.sp(14)
            columns: width < Theme.fs(340) ? 1 : 2
            columnSpacing: Theme.sp(20); rowSpacing: Theme.sp(10)
            ColumnLayout {
                Layout.fillWidth: true; spacing: Theme.sp(4)
                Text { Layout.fillWidth: true; text: name; color: Theme.text; font.family: Theme.fontBody; font.pixelSize: Theme.fBody; wrapMode: Text.Wrap }
                Text {
                    visible: desc.length > 0; text: desc
                    Layout.fillWidth: true
                    color: Theme.textMute; font.family: Theme.fontBody; font.pixelSize: Theme.fXs
                    wrapMode: Text.Wrap; lineHeight: 1.35
                }
            }
            Item {
                id: slot
                Layout.alignment: Qt.AlignVCenter | (fieldGrid.columns === 1 ? Qt.AlignLeft : Qt.AlignRight)
                Layout.preferredWidth: childrenRect.width
                Layout.preferredHeight: childrenRect.height
            }
        }
        Rectangle { Layout.fillWidth: true; height: 1; color: Theme.borderSoft }
    }

    component SectionTitle: Text {
        color: Theme.textMute; font.family: Theme.fontBody; font.pixelSize: Theme.fXs
        bottomPadding: Theme.sp(6)
    }

    // small flat text button
    component TButton: Pill {}

    FontMetrics { id: dropdownMetrics; font.family: Theme.fontBody; font.pixelSize: Theme.fSm }
    FontMetrics { id: dropdownCheckMetrics; font.family: Theme.fontMono; font.pixelSize: Theme.fSm }
    function dropdownWidth(options) {
        var longest = 0
        for (var i = 0; i < options.length; i++)
            longest = Math.max(longest, dropdownMetrics.advanceWidth(options[i].label))
        // Reserve space for both the field arrow and a checked popup option.
        var padding = Math.max(dropdownMetrics.font.pixelSize * 4,
            40 + Math.max(dropdownCheckMetrics.font.pixelSize, dropdownCheckMetrics.advanceWidth("✓")))
        return Math.ceil(longest + padding)
    }

    component SettingDropdown: Rectangle {
        id: selector
        property var options: []
        property string current: ""
        property real sharedWidth: 0
        property string menuObjectName: objectName + "Menu"
        readonly property string label: {
            for (var i = 0; i < options.length; i++)
                if (options[i].key === current) return options[i].label
            return ""
        }
        signal picked(string key)
        implicitWidth: sharedWidth > 0 ? sharedWidth : win.dropdownWidth(options)
        implicitHeight: Theme.controlHeight
        radius: height / 2; color: selectorArea.containsMouse ? Theme.surface : Theme.surface2
        activeFocusOnTab: true
        function openMenu() {
            selectorMenu.items = selector.options.map(function(item) {
                return {label: item.label, val: item.key, checked: item.key === selector.current}
            })
            selectorMenu.open()
        }
        Keys.onSpacePressed: openMenu()
        Keys.onReturnPressed: openMenu()
        Text {
            objectName: selector.objectName + "Label"
            anchors.left: parent.left; anchors.leftMargin: Theme.fs(12)
            anchors.right: indicator.left; anchors.rightMargin: Theme.fs(8)
            anchors.verticalCenter: parent.verticalCenter
            text: selector.label; elide: Text.ElideRight
            color: Theme.textDim; font.family: Theme.fontBody; font.pixelSize: Theme.fSm
        }
        AppIcon {
            id: indicator
            objectName: selector.objectName + "Indicator"
            anchors.right: parent.right; anchors.rightMargin: Theme.fs(8)
            anchors.verticalCenter: parent.verticalCenter
            width: Theme.fs(14); height: width
            name: "chevronDown"; color: Theme.textMute
        }
        MouseArea {
            id: selectorArea
            anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor
            onClicked: selector.openMenu()
        }
        MenuPopup {
            id: selectorMenu
            objectName: selector.menuObjectName
            parent: selector
            x: 0; width: selector.width
            menuWidth: Math.max(0, Math.round(selector.width - leftPadding - rightPadding))
            aboveAnchor: true; checkable: true
            onPicked: function(val) { selector.picked(val) }
        }
    }

    // 选项胶囊（可带圆形色块）
    component OptChip: Rectangle {
        id: chip
        property string text: ""
        property bool on: false
        property color dot: "transparent"
        property bool showDot: false
        readonly property color ink: showDot ? (on ? Theme.swatchInk(dot) : "#d0d0d0")
                                            : (on ? Theme.accent : Theme.textDim)
        signal clicked()
        implicitHeight: Theme.controlHeight
        implicitWidth: ocRow.implicitWidth + Theme.fs(22)
        radius: height / 2
        color: showDot ? (on ? dot : (ocMa.containsMouse ? Qt.lighter(Theme.mutedSwatch(dot), 1.15) : Theme.mutedSwatch(dot)))
                       : (on ? Theme.accentSoft : (ocMa.containsMouse ? Theme.surface : "transparent"))
        Row {
            id: ocRow; anchors.centerIn: parent; spacing: Theme.sp(7)
            Rectangle {
                visible: chip.showDot; anchors.verticalCenter: parent.verticalCenter
                width: Theme.fs(12); height: width; radius: width / 2; color: chip.dot
                border.width: 1; border.color: Qt.rgba(chip.ink.r, chip.ink.g, chip.ink.b, 0.3)
            }
            Text {
                anchors.verticalCenter: parent.verticalCenter
                text: chip.text
                color: chip.ink
                font.family: Theme.fontBody; font.pixelSize: Theme.fSm
                font.weight: chip.on ? Font.DemiBold : Font.Normal
            }
            AppIcon {
                anchors.verticalCenter: parent.verticalCenter
                name: "check"; color: chip.ink
                width: Theme.fs(13); height: width
                opacity: chip.on ? 1 : 0
            }
        }
        MouseArea { id: ocMa; anchors.fill: parent; hoverEnabled: true
            cursorShape: Qt.PointingHandCursor; onClicked: chip.clicked() }
    }

    // 名称 + 说明 + 一排自动换行的选项（model: [{key,label,dot,showDot}]）
    component OptSection: ColumnLayout {
        id: secRoot
        property string name: ""
        property string desc: ""
        property var model: []
        property string current: ""
        property bool dropdown: false
        property real dropdownWidth: 0
        property string selectorName: ""
        signal picked(string key)
        Layout.fillWidth: true
        spacing: 0
        ColumnLayout {
            Layout.fillWidth: true; Layout.topMargin: Theme.sp(14); spacing: Theme.sp(4)
            Text { text: secRoot.name; color: Theme.text
                   font.family: Theme.fontBody; font.pixelSize: Theme.fBody }
            Text {
                visible: secRoot.desc.length > 0; text: secRoot.desc.replace(/[。.]$/, "")
                Layout.fillWidth: true
                color: Theme.textMute; font.family: Theme.fontBody; font.pixelSize: Theme.fXs
                wrapMode: Text.Wrap; lineHeight: 1.35
            }
        }
        Flow {
            visible: !secRoot.dropdown
            Layout.fillWidth: true; Layout.topMargin: Theme.sp(10); Layout.bottomMargin: Theme.sp(14); spacing: Theme.sp(6)
            Repeater {
                model: secRoot.dropdown ? [] : secRoot.model
                delegate: OptChip {
                    required property var modelData
                    objectName: "appearanceOption_" + modelData.key
                    text: modelData.label
                    showDot: modelData.showDot === true
                    dot: modelData.dot !== undefined ? modelData.dot : "transparent"
                    on: secRoot.current === modelData.key
                    onClicked: secRoot.picked(modelData.key)
                }
            }
        }
        SettingDropdown {
            objectName: secRoot.selectorName
            visible: secRoot.dropdown
            Layout.alignment: Qt.AlignLeft
            Layout.topMargin: Theme.sp(10); Layout.bottomMargin: Theme.sp(14)
            options: secRoot.model
            sharedWidth: secRoot.dropdownWidth
            current: secRoot.current
            onPicked: function(key) { secRoot.picked(key) }
        }
        Rectangle { Layout.fillWidth: true; height: 1; color: Theme.borderSoft }
    }

    property var navModel: [
        { grp: loc("设置") },
        { id: "general",    name: loc("常规") },
        { id: "appearance", name: loc("外观") },
        { id: "sessions",   name: loc("会话") },
        { id: "model",      name: loc("模型与 Provider") },
        { grp: loc("创作") },
        { id: "meshy",      name: "Meshy" },
        { id: "templates",  name: loc("提示词模板") },
        { grp: loc("扩展") },
        { id: "rules",      name: loc("规则") },
        { id: "plugins",    name: loc("插件") },
        { id: "memory",     name: loc("记忆") },
        { id: "about",      name: loc("关于") }
    ]
    function secName(id) {
        for (var i = 0; i < navModel.length; i++) if (navModel[i].id === id) return navModel[i].name
        return ""
    }

    contentItem: RowLayout {
        spacing: 0

        // ---------- left nav ----------
        Rectangle {
            objectName: "settingsNavigation"
            visible: !win.compact
            Layout.preferredWidth: Theme.fs(150)
            Layout.fillHeight: true
            color: Theme.panelDeep
            radius: Theme.radMd
            PanelScrollView {
                id: navigationScroll
                objectName: "settingsNavigationScroll"
                anchors.fill: parent
                anchors.margins: Theme.sp(10)
                clip: true
                contentWidth: availableWidth
                ColumnLayout {
                    width: navigationScroll.availableWidth
                    spacing: Theme.sp(2)
                    Repeater {
                        model: win.navModel
                        delegate: Item {
                            id: navd
                            required property int index
                            objectName: "settingsNav_" + (modelData.id || "group")
                            required property var modelData
                            Layout.fillWidth: true
                            implicitHeight: modelData.grp !== undefined
                                            ? Math.round(28 * Theme.scale) : Math.round(32 * Theme.scale)
                            // group label
                            Item {
                                objectName: "settingsGroup_" + index
                                visible: navd.modelData.grp !== undefined
                                anchors.fill: parent
                                anchors.topMargin: Theme.sp(3); anchors.bottomMargin: Theme.sp(3)
                                Text {
                                    anchors.left: parent.left; anchors.leftMargin: Theme.sp(10)
                                    anchors.verticalCenter: parent.verticalCenter
                                    text: navd.modelData.grp || ""
                                    color: Theme.textDim; font.family: Theme.fontBody; font.pixelSize: Theme.fXs
                                    font.weight: Font.Bold
                                }
                            }
                            // nav item
                            Rectangle {
                                visible: navd.modelData.id !== undefined
                                anchors.fill: parent
                                radius: Theme.radSm
                                color: navd.modelData.id === win.sec ? Theme.accentSoft
                                      : (niMa.containsMouse ? Theme.surface : "transparent")
                                Text {
                                    anchors.left: parent.left; anchors.leftMargin: Theme.sp(10)
                                    anchors.verticalCenter: parent.verticalCenter
                                    text: navd.modelData.name || ""
                                    color: navd.modelData.id === win.sec ? Theme.text : Theme.textDim
                                    font.family: Theme.fontBody; font.pixelSize: Theme.fSm
                                }
                                MouseArea {
                                    id: niMa; anchors.fill: parent; hoverEnabled: true
                                    cursorShape: Qt.PointingHandCursor
                                    onClicked: if (navd.modelData.id !== undefined) win.sec = navd.modelData.id
                                }
                            }
                        }
                    }
                }
            }
        }

        // ---------- right body ----------
        ColumnLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            spacing: 0

            // top bar
            RowLayout {
                id: settingsHeader
                Layout.fillWidth: true
                Layout.preferredHeight: Theme.panelHeaderHeight
                Layout.leftMargin: Theme.panelPadding; Layout.rightMargin: Theme.panelPadding
                spacing: Theme.sp(8)
                Text {
                    visible: !win.compact
                    Layout.fillWidth: true
                    text: win.secName(win.sec)
                    color: Theme.textBright
                    font.family: Theme.fontDisplay; font.pixelSize: Theme.fLg; font.weight: Font.Medium
                }
                Pill {
                    objectName: "settingsSectionSelector"
                    visible: win.compact
                    Layout.fillWidth: true
                    label: win.secName(win.sec); caret: true
                    onClicked: {
                        sectionMenu.items = win.navModel.filter(function(item) { return item.id !== undefined }).map(function(item) {
                            return {label: item.name, val: item.id, checked: item.id === win.sec}
                        })
                        sectionMenu.open()
                    }
                }
                IconButton {
                    objectName: "settingsCloseButton"
                    icon: "close"; circular: true; tooltip: win.loc("关闭")
                    onClicked: win.close()
                }
            }
            Rectangle { Layout.fillWidth: true; height: 1; color: Theme.borderSoft }

            // content
            Item {
                id: bodyArea
                Layout.fillWidth: true; Layout.fillHeight: true
                property bool isMgmt: win.sec === "rules" || win.sec === "plugins" || win.sec === "memory"
                property bool isProviders: win.sec === "model"

                // 配置类分区：可滚动的字段列
                PanelScrollView {
                    id: scroll
                    objectName: "settingsPageScroll"
                    anchors.fill: parent
                    visible: !bodyArea.isMgmt && !bodyArea.isProviders
                    clip: true
                    contentWidth: availableWidth
                    Item {
                        width: scroll.availableWidth
                        implicitHeight: secCol.implicitHeight + Theme.panelPadding * 2
                        ColumnLayout {
                            id: secCol
                            x: Theme.panelPadding; y: Theme.panelPadding
                            width: parent.width - Theme.panelPadding * 2
                            spacing: 0
                            Loader {
                                objectName: "settingsSectionLoader"
                                Layout.fillWidth: true
                                sourceComponent: win.sec === "general" ? cGeneral
                                               : win.sec === "appearance" ? cAppearance
                                               : win.sec === "sessions" ? cSessions
                                               : win.sec === "meshy" ? cMeshy
                                               : win.sec === "templates" ? cTemplates
                                               : cAbout
                            }
                        }
                    }
                }

                // 模型与 Provider：内嵌多供应商管理器
                ProviderManager {
                    objectName: "settingsProviders"
                    anchors.fill: parent
                    anchors.margins: Theme.panelPadding
                    visible: bodyArea.isProviders
                    active: bodyArea.isProviders
                }

                // 规则 / 插件 / 记忆：直接内嵌完整面板（不再弹独立窗口）
                ManagementContent {
                    objectName: "settingsManagement"
                    anchors.fill: parent
                    anchors.margins: Theme.panelPadding
                    visible: bodyArea.isMgmt
                    active: bodyArea.isMgmt
                    mode: win.sec === "rules" ? "rules" : win.sec === "plugins" ? "plugins" : "memory"
                }
            }
        }
    }

    MenuPopup {
        id: sectionMenu; objectName: "settingsSectionMenu"
        parent: win.contentItem
        x: Theme.panelPadding; y: Theme.panelHeaderHeight
        menuWidth: Math.min(Theme.fs(210), win.width - Theme.panelPadding * 2)
        maximumHeight: win.height - Theme.panelHeaderHeight - Theme.panelPadding
        checkable: true
        onPicked: function(val) { win.sec = val }
    }

    // ================= section contents =================
    Component {
        id: cGeneral
        ColumnLayout {
            id: genRoot
            spacing: 0
            property var meshyImgOpts: []
            property var codexImgOpts: []
            property string curImgModel: controller ? controller.defaultImageModel : "nano-banana"
            property bool codexOn: controller ? controller.codexLoggedIn : false
            function reloadImg() {
                if (!controller) return
                meshyImgOpts = controller.meshyImageModelOptions()
                codexImgOpts = controller.codexImageModelOptions()
                curImgModel = controller.defaultImageModel
                codexOn = controller.codexLoggedIn
            }
            Component.onCompleted: reloadImg()
            Connections {
                target: controller
                ignoreUnknownSignals: true
                function onImageModelChanged() { genRoot.reloadImg() }
                function onLangChanged() { genRoot.reloadImg() }
            }

            SectionTitle { text: win.loc("行为") }
            FieldRow {
                name: win.loc("显示思考过程")
                desc: win.loc("在回答里显示模型的思考过程（<think> 内容）。")
                Toggle { objectName: "thinkingToggle"; Accessible.name: win.loc("显示思考过程"); on: controller ? controller.showThinking : true
                    onToggled: if (controller) controller.setThink(!controller.showThinking) }
            }
            FieldRow {
                name: win.loc("实时 Cook")
                desc: win.loc("执行修改场景的工具后实时重算（cook）。关闭可在批量操作时提速。")
                Toggle { objectName: "cookToggle"; Accessible.name: win.loc("实时 Cook"); on: controller ? controller.cookRealtime : true
                    onToggled: if (controller) controller.menuAction("cook") }
            }
            FieldRow {
                name: win.loc("长期记忆")
                desc: win.loc("让助手跨会话记住你的偏好与项目信息。可在「记忆」分区查看与删除。")
                Toggle { objectName: "memoryToggle"; Accessible.name: win.loc("长期记忆"); on: controller ? controller.memoryEnabled : false
                    onToggled: if (controller) controller.menuAction("memory") }
            }
            Item { Layout.preferredHeight: 14 }
            SectionTitle { text: win.loc("图片生成") }
            ColumnLayout {
                Layout.fillWidth: true
                Layout.topMargin: 8
                Layout.bottomMargin: 14
                spacing: 0
                Text {
                    text: win.loc("默认生图模型")
                    color: Theme.text; font.family: Theme.fontBody; font.pixelSize: Theme.fMd
                }
                Text {
                    Layout.fillWidth: true; Layout.topMargin: 3
                    text: win.loc("选择文生图、图生图与概念图默认使用的生图后端。登录 ChatGPT 订阅后可直接使用 Codex 生图模型，无需 Meshy API Key。")
                    color: Theme.textMute; font.family: Theme.fontBody; font.pixelSize: Theme.fXs
                    wrapMode: Text.Wrap; lineHeight: 1.35
                }
                // Meshy 选项
                Text {
                    Layout.topMargin: 12
                    text: "MESHY"
                    color: Theme.textMute; font.family: Theme.fontMono
                    font.pixelSize: Theme.fMicro; font.letterSpacing: Theme.trackLabel
                }
                Flow {
                    Layout.fillWidth: true; Layout.topMargin: 7; spacing: 7
                    Repeater {
                        model: genRoot.meshyImgOpts
                        delegate: OptChip {
                            required property var modelData
                            text: modelData.label
                            on: genRoot.curImgModel === modelData.key
                            onClicked: if (controller) controller.setDefaultImageModel(modelData.key)
                        }
                    }
                }
                // ChatGPT 订阅（Codex）选项
                RowLayout {
                    Layout.fillWidth: true; Layout.topMargin: 13; spacing: 8
                    Text {
                        Layout.fillWidth: true
                        text: win.loc("ChatGPT 订阅") + " (CODEX)"
                        color: Theme.textMute; font.family: Theme.fontMono
                        font.pixelSize: Theme.fMicro; font.letterSpacing: Theme.trackLabel
                    }
                    TButton {
                        visible: genRoot.codexOn
                        label: (controller && controller.codexImageRefreshing) ? win.loc("同步中…") : win.loc("同步模型")
                        onClicked: if (controller) controller.refreshCodexImageModels()
                    }
                    TButton {
                        visible: !genRoot.codexOn
                        label: win.loc("登录 ChatGPT 订阅")
                        onClicked: if (controller) controller.openCodexSubscription()
                    }
                }
                Flow {
                    visible: genRoot.codexOn
                    Layout.fillWidth: true; Layout.topMargin: 7; spacing: 7
                    Repeater {
                        model: genRoot.codexImgOpts
                        delegate: OptChip {
                            required property var modelData
                            text: modelData.label
                            on: genRoot.curImgModel === modelData.key
                            onClicked: if (controller) controller.setDefaultImageModel(modelData.key)
                        }
                    }
                }
                Text {
                    visible: genRoot.codexOn
                    Layout.fillWidth: true; Layout.topMargin: 6
                    text: win.loc("自动同步自本机 ChatGPT 订阅（Codex）")
                    color: Theme.textMute; font.family: Theme.fontBody; font.pixelSize: Theme.fXs
                }
                Text {
                    visible: !genRoot.codexOn
                    Layout.fillWidth: true; Layout.topMargin: 6
                    text: win.loc("登录 ChatGPT 订阅后，即可自动同步并使用 Codex 生图模型（如 gpt-image-*）。")
                    color: Theme.textMute; font.family: Theme.fontBody; font.pixelSize: Theme.fXs
                    wrapMode: Text.Wrap; lineHeight: 1.35
                }
            }
            Rectangle { Layout.fillWidth: true; height: 1; color: Theme.borderSoft }
            Item { Layout.preferredHeight: 10 }
            SectionTitle { text: win.loc("常规") }
            FieldRow {
                name: win.loc("语言 / Language")
                SettingDropdown {
                    objectName: "languageSelector"
                    menuObjectName: "languageMenu"
                    options: [{key: "zh", label: "中文"}, {key: "en", label: "English"}]
                    current: controller ? controller.lang : "zh"
                    onPicked: function(key) {
                        if (controller && controller.lang !== key) controller.menuAction("lang_" + key)
                    }
                }
            }
        }
    }

    Component {
        id: cAppearance
        ColumnLayout {
            id: appearanceRoot
            property var fontOptions: [
                {key: "editorial", label: win.loc("编辑体")},
                {key: "modern", label: win.loc("现代")},
                {key: "mono", label: win.loc("等宽")}
            ]
            property var densityOptions: [
                {key: "compact", label: win.loc("紧凑")},
                {key: "normal", label: win.loc("标准")},
                {key: "roomy", label: win.loc("宽松")}
            ]
            readonly property real selectorWidth: win.dropdownWidth(fontOptions.concat(densityOptions))
            spacing: 0
            SectionTitle { text: win.loc("外观") }
            OptSection {
                name: win.loc("主题")
                desc: win.loc("深色三档，外加日光（浅色）。选日光会整体翻成浅色，强调色自动加深保证可读。")
                current: controller ? controller.appTheme : "graphite"
                model: [
                    { key: "noir",     label: win.loc("极夜"),   showDot: true, dot: "#0d0d0d" },
                    { key: "graphite", label: win.loc("石墨"),   showDot: true, dot: "#212121" },
                    { key: "midnight", label: win.loc("午夜蓝"), showDot: true, dot: "#0c0e13" },
                    { key: "day",      label: win.loc("日光"),   showDot: true, dot: "#ffffff" }
                ]
                onPicked: function(k) { if (controller) controller.setAppTheme(k) }
            }
            OptSection {
                name: win.loc("强调色")
                desc: win.loc("选中态、指示点与用户气泡的颜色。")
                current: controller ? controller.accentKey : "neutral"
                model: [
                    { key: "warm",    label: win.loc("暖米"), showDot: true, dot: "#e8e2d4" },
                    { key: "steel",   label: win.loc("冷钢"), showDot: true, dot: "#aec4d6" },
                    { key: "celadon", label: win.loc("青瓷"), showDot: true, dot: "#aecdb8" },
                    { key: "clay",    label: win.loc("暖砂"), showDot: true, dot: "#e0b48c" },
                    { key: "neutral", label: win.loc("中性"), showDot: true, dot: "#e5e5e5" }
                ]
                onPicked: function(k) { if (controller) controller.setAccentKey(k) }
            }
            OptSection {
                name: win.loc("字体方案")
                dropdown: true; selectorName: "fontFamilySelector"
                dropdownWidth: appearanceRoot.selectorWidth
                desc: win.loc("标题 / 正文 / 等宽三件套的整体气质。")
                current: controller ? controller.fontFamilyKey : "modern"
                model: appearanceRoot.fontOptions
                onPicked: function(k) { if (controller) controller.setFontFamilyKey(k) }
            }
            OptSection {
                name: win.loc("界面密度")
                dropdown: true; selectorName: "densitySelector"
                dropdownWidth: appearanceRoot.selectorWidth
                desc: win.loc("间距与行高的松紧，不改字号。")
                current: controller ? controller.densityKey : "normal"
                model: appearanceRoot.densityOptions
                onPicked: function(k) { if (controller) controller.setDensityKey(k) }
            }
            FieldRow {
                name: win.loc("界面字号")
                desc: win.loc("调整整个面板的字号缩放。").replace(/[。.]$/, "")
                RowLayout {
                    spacing: Theme.sp(4)
                    IconButton {
                        objectName: "fontScaleDown"
                        circular: true; icon: "minus"
                        tooltip: win.loc("缩小字号")
                        onClicked: if (controller) controller.setFontScale(controller.fontScale - 0.1)
                    }
                    Text {
                        Layout.preferredWidth: Theme.fs(48)
                        horizontalAlignment: Text.AlignHCenter
                        text: controller ? Math.round(controller.fontScale * 100) + "%" : "100%"
                        color: Theme.text; font.family: Theme.fontBody; font.pixelSize: Theme.fSm
                    }
                    IconButton {
                        objectName: "fontScaleUp"
                        circular: true; icon: "plus"
                        tooltip: win.loc("放大字号")
                        onClicked: if (controller) controller.setFontScale(controller.fontScale + 0.1)
                    }
                }
            }
        }
    }

    Component {
        id: cSessions
        ColumnLayout {
            spacing: 0
            SectionTitle { text: win.loc("会话") }
            FieldRow {
                name: win.loc("删除会话前需确认")
                desc: win.loc("关闭后删除会话不再弹确认框。在删除弹窗里勾选「不再询问」会自动关掉这里——随时可重新打开。")
                Toggle { objectName: "confirmSessionDeleteToggle"; on: controller ? controller.askDeleteSession : true
                    onToggled: if (controller) controller.setAskDeleteSession(!controller.askDeleteSession) }
            }
            FieldRow {
                name: win.loc("每步操作需批准（确认模式）")
                desc: win.loc("执行会修改场景或计费的工具前逐个弹确认卡。")
                Toggle { on: controller ? controller.confirmMode : false
                    onToggled: if (controller) controller.menuAction("confirm") }
            }
            FieldRow {
                name: win.loc("导出对话")
                Pill { objectName: "settingsExportChat"; label: win.loc("导出"); onClicked: win.action("export") }
            }
            FieldRow {
                name: win.loc("Token 分析")
                Pill { objectName: "settingsTokenAnalysis"; label: win.loc("查看"); onClicked: win.action("tokens") }
            }
            FieldRow {
                name: win.loc("压缩上下文")
                Pill { label: win.loc("压缩"); onClicked: win.action("optimize") }
            }
            FieldRow {
                name: win.loc("清空对话")
                Pill { label: win.loc("清空"); onClicked: win.action("clear") }
            }
        }
    }

    Component {
        id: cMeshy
        ColumnLayout {
            id: meshySettings
            objectName: "meshySettings"
            spacing: 0
            property var account: controller ? controller.meshyAccount() : ({})
            Connections {
                target: controller
                function onMeshyAccountChanged() { meshySettings.account = controller.meshyAccount() }
            }
            SectionTitle { text: win.loc("Meshy 账号") }
            FieldRow {
                name: meshySettings.account.connected ? win.loc("已连接 Meshy 账号。") : win.loc("未连接")
                desc: meshySettings.account.connected ? (meshySettings.account.key || "") : win.loc("API Key 是 Meshy 的登录凭证。")
                Pill {
                    objectName: "meshyConfigureKey"
                    label: win.loc("配置 API Key")
                    onClicked: if (controller) controller.openMeshyLogin()
                }
            }
            FieldRow {
                name: win.loc("余额")
                RowLayout {
                    spacing: Theme.sp(8)
                    Text {
                        text: meshySettings.account.balance >= 0 ? meshySettings.account.balance + " credits" : "—"
                        color: Theme.textDim; font.family: Theme.fontBody; font.pixelSize: Theme.fSm
                    }
                    Pill { label: win.loc("刷新"); onClicked: if (controller) controller.syncMeshyAccount() }
                }
            }
            FieldRow {
                name: win.loc("资产库")
                desc: win.loc("云资产 · 直接拉到 Houdini")
                Pill { objectName: "meshyOpenLibrary"; label: win.loc("打开"); onClicked: win.action("library") }
            }
            FieldRow {
                name: win.loc("Meshy · 3D 生成")
                Pill {
                    objectName: "meshyStartGeneration"
                    label: win.loc("开始")
                    onClicked: { win.close(); if (controller) controller.composePrefill(win.loc("用 Meshy 生成一个 ")) }
                }
            }
            Item { Layout.preferredHeight: Theme.sp(14) }
            Flow {
                Layout.fillWidth: true
                spacing: Theme.sp(6)
                Repeater {
                    model: controller ? controller.meshyMenuItems().filter(function(item) { return !item.sep }) : []
                    delegate: Pill {
                        required property var modelData
                        objectName: "meshyLink_" + modelData.val
                        label: modelData.label
                        onClicked: if (controller) controller.openMeshy(modelData.val)
                    }
                }
            }
        }
    }

    Component {
        id: cTemplates
        ColumnLayout {
            spacing: 0
            FieldRow {
                name: win.loc("提示词模板")
                Pill {
                    objectName: "settingsOpenTemplates"
                    label: win.loc("打开")
                    onClicked: if (controller) controller.openTemplateLibrary()
                }
            }
        }
    }

    Component {
        id: cAbout
        ColumnLayout {
            spacing: 0
            SectionTitle { text: win.loc("关于") }
            FieldRow {
                name: win.loc("版本")
                Text { text: "Houdini Agent · " + (controller ? controller.appVersion : "")
                    color: Theme.textDim; font.family: Theme.fontMono; font.pixelSize: Theme.fSm }
            }
            FieldRow {
                name: win.loc("检查更新")
                TButton { label: win.loc("检查更新"); onClicked: win.action("update") }
            }
            FieldRow {
                name: win.loc("缓存位置")
                Pill { objectName: "settingsCacheLocation"; label: win.loc("查看"); onClicked: win.action("cache") }
            }
        }
    }
}
