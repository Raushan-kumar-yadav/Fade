import QtQuick 2.15
import QtQuick.Controls 2.15
import Fade 1.0

TextField {
    id: field
    property bool monoFont: false

    font.family:    monoFont ? FadeTheme.fontMono : FadeTheme.fontFamily
    font.pixelSize: FadeTheme.fontMd
    color:          FadeTheme.textPrimary
    leftPadding:  8; rightPadding:  8
    topPadding:   5; bottomPadding: 5

    background: Rectangle {
        radius: FadeTheme.radiusSm
        color:  FadeTheme.bgInput
        border.color: field.activeFocus ? FadeTheme.borderFocus : FadeTheme.borderStrong
        border.width: 1

        Rectangle {
            anchors.fill: parent
            anchors.margins: -2
            radius: parent.radius + 2
            color: "transparent"
            border.color: field.activeFocus ? Qt.rgba(0.49, 0.23, 0.93, 0.15) : "transparent"
            border.width: 2
        }

        Behavior on border.color { ColorAnimation { duration: FadeTheme.durationFast } }
    }

    placeholderTextColor: FadeTheme.textPlaceholder
}
