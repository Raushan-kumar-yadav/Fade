import QtQuick 2.15
import QtQuick.Controls 2.15
import Fade 1.0

Button {
    id: btn
    property string variant: "default"

    font.family:    FadeTheme.fontFamily
    font.pixelSize: FadeTheme.fontMd
    font.weight:    Font.Medium
    leftPadding:  20; rightPadding: 20
    topPadding:    7; bottomPadding: 7

    background: Rectangle {
        radius: FadeTheme.radiusSm + 1

        color: {
            if (!btn.enabled) {
                if (btn.variant === "primary") return Qt.rgba(0.42, 0.39, 1, 0.30)
                return Qt.rgba(1, 1, 1, 0.04)
            }
            switch (btn.variant) {
                case "primary": return btn.hovered ? FadeTheme.accentPurple : Qt.rgba(0.42, 0.39, 1, 0.85)
                case "danger":  return btn.hovered ? Qt.rgba(0.94, 0.27, 0.27, 0.25) : Qt.rgba(0.94, 0.27, 0.27, 0.15)
                case "ghost":   return "transparent"
                case "browse":  return btn.hovered ? Qt.rgba(1, 1, 1, 0.12) : Qt.rgba(1, 1, 1, 0.07)
                default:        return btn.hovered ? Qt.rgba(1, 1, 1, 0.12) : Qt.rgba(1, 1, 1, 0.07)
            }
        }

        border.width: (btn.variant === "browse" || btn.variant === "danger") ? 1 : 0
        border.color: {
            if (btn.variant === "browse") return Qt.rgba(1, 1, 1, 0.14)
            if (btn.variant === "danger") return Qt.rgba(0.94, 0.27, 0.27, 0.25)
            return "transparent"
        }

        Behavior on color { ColorAnimation { duration: FadeTheme.durationFast } }
    }

    contentItem: Text {
        text: btn.text
        font: btn.font
        horizontalAlignment: Text.AlignHCenter
        verticalAlignment:   Text.AlignVCenter

        color: {
            if (!btn.enabled) return Qt.rgba(1, 1, 1, 0.35)
            switch (btn.variant) {
                case "primary": return "#ffffff"
                case "danger":  return FadeTheme.red
                case "ghost":   return btn.hovered ? FadeTheme.accentPurpleLight : FadeTheme.textDisabled
                case "browse":  return btn.hovered ? "#ffffff" : Qt.rgba(1, 1, 1, 0.8)
                default:        return btn.hovered ? "#ffffff" : Qt.rgba(1, 1, 1, 0.75)
            }
        }
        Behavior on color { ColorAnimation { duration: FadeTheme.durationFast } }
    }

    transform: Translate {
        y: (btn.variant === "primary" && btn.hovered && btn.enabled) ? -1 : 0
        Behavior on y { NumberAnimation { duration: FadeTheme.durationFast } }
    }
}
