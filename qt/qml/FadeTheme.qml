pragma Singleton
import QtQuick 2.15

QtObject {
    readonly property color bgBase: "#0f1117"
    readonly property color bgPanel: "#16161a"
    readonly property color bgSurface: "#131720"
    readonly property color bgInput: "#0d1117"
    readonly property color bgAssistant:  "#1a2035"
    readonly property color bgOverlay: "#99000000"

    readonly property color borderSubtle: "#14ffffff"
    readonly property color borderMuted:  "#0fffffff"
    readonly property color borderStrong: "#1e2433"
    readonly property color borderFocus:  "#7c3aed"

    readonly property color textPrimary: "#f0f0f2"
    readonly property color textBody: "#e2e8f0"
    readonly property color textMuted: "#b3ffffff"
    readonly property color textDim:         "#66ffffff"
    readonly property color textVeryDim: "#4dffffff"
    readonly property color textDisabled: "#64748b"
    readonly property color textPlaceholder: "#374151"

    readonly property color accentPurple:       "#7c3aed"
    readonly property color accentPurpleLight:  "#a78bfa"
    readonly property color accentPurpleDark:   "#6d28d9"
    readonly property color accentPurpleDarker: "#4c1d95"

    readonly property color green:    "#34d399"
    readonly property color greenBg:  "#2634d399"
    readonly property color red:      "#f87171"
    readonly property color redBg:    "#26ef4444"
    readonly property color yellow:   "#fbbf24"
    readonly property color yellowBg: "#0dfbbf24"
    readonly property color teal:     "#00d4aa"

    readonly property int radiusXs:    4
    readonly property int radiusSm:    6
    readonly property int radiusMd:    8
    readonly property int radiusLg:   14
    readonly property int radiusFull: 99

    readonly property string fontFamily: "Inter"
    readonly property string fontMono:   "JetBrains Mono"
    readonly property int fontXs:   10
    readonly property int fontSm:   11
    readonly property int fontBase: 12
    readonly property int fontMd:   13
    readonly property int fontLg:   15

    readonly property int durationFast:   150
    readonly property int durationNormal: 200
    readonly property int durationSlow:   300
}
