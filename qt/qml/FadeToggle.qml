import QtQuick 2.15
import QtQuick.Controls 2.15
import Fade 1.0

Switch {
    id: toggle
    implicitWidth:  32
    implicitHeight: 18

    indicator: Rectangle {
        x: 0; y: 0
        width: 32; height: 18
        radius: 18
        color: toggle.checked ? Qt.rgba(0.49, 0.23, 0.93, 0.40) : FadeTheme.borderStrong
        Behavior on color { ColorAnimation { duration: FadeTheme.durationNormal } }

        Rectangle {
            x: toggle.checked ? 17 : 3
            y: 3
            width: 12; height: 12
            radius: 12
            color: toggle.checked ? FadeTheme.accentPurpleLight : "#4b5563"
            Behavior on x     { NumberAnimation { duration: FadeTheme.durationNormal; easing.type: Easing.OutCubic } }
            Behavior on color { ColorAnimation  { duration: FadeTheme.durationNormal } }
        }
    }

    contentItem: Item {}
}
