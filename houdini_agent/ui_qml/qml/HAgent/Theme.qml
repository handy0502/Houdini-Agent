pragma Singleton
import QtQuick

// ============================================================
// Neutral desktop UI — design tokens (single source of truth)
// Scale-aware + theme-aware. The whole app re-skins by changing
// the four state keys below (driven by Controller via Main.qml).
// All historical token NAMES are preserved so existing QML keeps working.
// ============================================================
QtObject {
    id: theme

    // ---- user-driven appearance state (set from Main <- controller) ----
    property string mode: "graphite"     // noir | graphite | midnight | day
    property string accentKey: "neutral" // warm | steel | celadon | clay | neutral
    property string typeKey: "modern"    // editorial | modern | mono
    property string densityKey: "normal"  // compact | normal | roomy
    property real scale: 1.0

    readonly property bool light: mode === "day"

    // ---- palette lookup (per mode) ----
    function _palette(m) {
        if (m === "day") return {
            bg:"#ffffff", codeBg:"#f7f7f8", panel:"#f6f6f6", panelDeep:"#f9f9f9",
            surface:Qt.rgba(0,0,0,0.035), surface2:Qt.rgba(0,0,0,0.065),
            border:Qt.rgba(0,0,0,0.12), borderSoft:Qt.rgba(0,0,0,0.065),
            text:"#303030", textBright:"#171717", textDim:"#626262", textMute:"#767676",
            ok:"#5d7a3f", okA:Qt.rgba(0.36,0.48,0.25,0.14), warn:"#9a5a2a", warnA:Qt.rgba(0.6,0.35,0.16,0.12), err:"#a8484f",
            userFg:"#1c1910", userBorder:Qt.rgba(0,0,0,0.24),
            synCom:"#9c9483", synKw:"#5b4f37", synFn:"#7a6a3f", synAttr:"#8a583a", synNum:"#5f7a45", synStr:"#8a583a"
        }
        if (m === "graphite") return {
            bg:"#212121", codeBg:"#191919", panel:"#2c2c2c", panelDeep:"#181818",
            surface:Qt.rgba(1,1,1,0.05), surface2:Qt.rgba(1,1,1,0.085),
            border:Qt.rgba(1,1,1,0.12), borderSoft:Qt.rgba(1,1,1,0.06),
            text:"#e8e8e8", textBright:"#fafafa", textDim:"#b4b4b4", textMute:"#939393",
            ok:"#8fbea0", okA:Qt.rgba(0.56,0.75,0.63,0.12), warn:"#d5b27a", warnA:Qt.rgba(0.83,0.70,0.48,0.10), err:"#e69b9b",
            userFg:"#fafafa", userBorder:Qt.rgba(1,1,1,0.20),
            synCom:"#5e5b54", synKw:"#e8e2d4", synFn:"#c9b896", synAttr:"#d4a373", synNum:"#a3b18a", synStr:"#bc9b7a"
        }
        if (m === "midnight") return {
            bg:"#0c0e13", codeBg:"#07090d", panel:"#10131a", panelDeep:"#0a0c11",
            surface:Qt.rgba(1,1,1,0.045), surface2:Qt.rgba(1,1,1,0.075),
            border:Qt.rgba(1,1,1,0.12), borderSoft:Qt.rgba(1,1,1,0.08),
            text:"#e3e4e2", textBright:"#ffffff", textDim:"#b8bcc4", textMute:"#888d98",
            ok:"#b8c5a0", okA:Qt.rgba(0.72,0.77,0.63,0.12), warn:"#d4a373", warnA:Qt.rgba(0.83,0.64,0.45,0.10), err:"#dd9999",
            userFg:"#fafafa", userBorder:Qt.rgba(1,1,1,0.20),
            synCom:"#5e5b54", synKw:"#e8e2d4", synFn:"#c9b896", synAttr:"#d4a373", synNum:"#a3b18a", synStr:"#bc9b7a"
        }
        // noir (default)
        return {
            bg:"#0d0d0d", codeBg:"#080808", panel:"#101010", panelDeep:"#0c0c0c",
            surface:Qt.rgba(1,1,1,0.04), surface2:Qt.rgba(1,1,1,0.07),
            border:Qt.rgba(1,1,1,0.12), borderSoft:Qt.rgba(1,1,1,0.08),
            text:"#e8e8e8", textBright:"#fafafa", textDim:"#b4b4b4", textMute:"#939393",
            ok:"#b8c5a0", okA:Qt.rgba(0.72,0.77,0.63,0.12), warn:"#d4a373", warnA:Qt.rgba(0.83,0.64,0.45,0.10), err:"#dd9999",
            userFg:"#fafafa", userBorder:Qt.rgba(1,1,1,0.20),
            synCom:"#5e5b54", synKw:"#e8e2d4", synFn:"#c9b896", synAttr:"#d4a373", synNum:"#a3b18a", synStr:"#bc9b7a"
        }
    }
    readonly property var _pal: _palette(mode)

    // ---- palette ----
    readonly property color bg:         _pal.bg
    readonly property color codeBg:     _pal.codeBg
    readonly property color panel:      _pal.panel
    readonly property color panelDeep:  _pal.panelDeep
    readonly property color surface:    _pal.surface
    readonly property color surface2:   _pal.surface2
    readonly property color border:     _pal.border
    readonly property color borderSoft: _pal.borderSoft

    readonly property color text:       _pal.text
    readonly property color textBright: _pal.textBright
    readonly property color textDim:    _pal.textDim
    readonly property color textMute:   _pal.textMute

    // ---- accent (hue picked by accentKey; darkened for foreground on light) ----
    function _hue(k) {
        if (k === "steel")   return "#aec4d6"
        if (k === "celadon") return "#aecdb8"
        if (k === "clay")    return "#e0b48c"
        if (k === "neutral") return "#e5e5e5"
        return "#e8e2d4" // warm (default)
    }
    readonly property color accentHue: _hue(accentKey)
    readonly property color accent:     light ? (accentKey === "neutral" ? "#262626" : Qt.darker(accentHue, 1.72)) : accentHue
    readonly property color accentSoft: Qt.rgba(accent.r, accent.g, accent.b, light ? 0.13 : 0.10)
    readonly property color accentLine: Qt.rgba(accent.r, accent.g, accent.b, light ? 0.42 : 0.30)

    function mutedSwatch(sample) {
        var gray = (sample.r + sample.g + sample.b) / 3
        return Qt.tint("#3b3b3b", Qt.rgba((sample.r + gray) / 2,
            (sample.g + gray) / 2, (sample.b + gray) / 2, 0.18))
    }
    function swatchInk(sample) {
        return sample.r * 0.2126 + sample.g * 0.7152 + sample.b * 0.0722 > 0.55
            ? "#1c1c1c" : "#f5f5f5"
    }

    // ---- Meshy brand (green) — for Meshy-related UI only ----
    readonly property color meshy:      "#c5f955"
    readonly property color meshyHover: "#a8e328"
    readonly property color meshyInk:   "#0e0e0e"
    readonly property color meshySoft:  Qt.rgba(0.773, 0.976, 0.333, 0.12)
    readonly property color meshyLine:  Qt.rgba(0.773, 0.976, 0.333, 0.38)

    readonly property color ok:         _pal.ok
    readonly property color okSoft:     _pal.okA
    readonly property color warn:       _pal.warn
    readonly property color warnSoft:   _pal.warnA
    readonly property color err:        _pal.err

    readonly property color userFg:     _pal.userFg
    readonly property color userBorder: accentKey === "neutral" ? _pal.userBorder : accentLine

    // ---- syntax highlight ----
    readonly property color synCom:  _pal.synCom
    readonly property color synKw:   _pal.synKw
    readonly property color synFn:   _pal.synFn
    readonly property color synAttr: _pal.synAttr
    readonly property color synNum:  _pal.synNum
    readonly property color synStr:  _pal.synStr

    readonly property color sidebar: panelDeep
    readonly property color inputBg: light ? "#f7f7f7" : panel
    readonly property color userBg: accentKey === "neutral"
        ? (light ? "#f1f1f1" : Qt.tint(bg, Qt.rgba(1, 1, 1, 0.07)))
        : Qt.tint(light ? "#f1f1f1" : bg, Qt.rgba(accentHue.r, accentHue.g, accentHue.b, 0.18))
    readonly property int contentMaxWidth: fs(760)
    readonly property int sidebarWidth: fs(236)
    readonly property int controlHeight: fs(28)
    readonly property int fieldHeight: fs(32)
    readonly property int panelHeaderHeight: fs(52)
    readonly property int panelPadding: sp(20)
    readonly property color fieldBg: light ? "#ffffff" : codeBg
    readonly property color switchOff: light ? "#b5b5b5" : "#606060"
    readonly property color switchOn: light ? "#22864f" : "#58b881"
    readonly property color switchThumbOn: bg
    readonly property color switchThumbOff: light ? "#ffffff" : "#e8e8e8"
    readonly property color scrollThumb: light ? Qt.darker(panel, 1.2) : Qt.lighter(panel, 1.5)
    readonly property color scrollThumbHover: light ? Qt.darker(panel, 1.3) : Qt.lighter(panel, 1.75)
    readonly property color scrollThumbPressed: light ? Qt.darker(panel, 1.4) : Qt.lighter(panel, 2.0)

    // Consistent, restrained rounding across controls and content.
    readonly property int radSm: fs(7)
    readonly property int radMd: fs(12)
    readonly property int radLg: fs(18)

    // ---- typography ----
    function _fam(role) {
        if (typeKey === "mono") return "Cascadia Code"
        if (typeKey === "modern") return role === "mono" ? "Cascadia Code" : "Segoe UI"
        // editorial (default)
        return role === "display" ? "Fraunces" : role === "mono" ? "Space Mono" : "Newsreader"
    }
    readonly property string fontDisplay: _fam("display")
    readonly property string fontBody:    _fam("body")
    readonly property string fontMono:    _fam("mono")

    function fs(px) { return Math.round(px * scale) }

    readonly property int fMicro: fs(11)
    readonly property int fXs:    fs(12)
    readonly property int fSm:    fs(13)
    readonly property int fBody:  fs(14)
    readonly property int fMd:    fs(15)
    readonly property int fLg:    fs(17)
    readonly property int fXl:    fs(24)

    // Avoid tracked uppercase micro-labels in the default UI.
    readonly property real trackLabel: 0

    // ---- density (spacing only; does not touch font size) ----
    readonly property real density: densityKey === "compact" ? 0.82
                                   : densityKey === "roomy"   ? 1.22 : 1.0
    function sp(px) { return Math.round(px * scale * density) }
    readonly property int gap:   sp(14)   // between chat messages
    readonly property int gapLg: sp(20)
    readonly property int pad:   sp(14)   // pane padding
}
