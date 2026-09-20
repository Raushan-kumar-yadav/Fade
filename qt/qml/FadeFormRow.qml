import QtQuick 2.15
import QtQuick.Layouts 1.15
import Fade 1.0

RowLayout {
    spacing: 10
    property string label:  ""
    property alias  content: contentSlot.data

    Text {
        text:  label
        font.family:    FadeTheme.fontFamily
        font.pixelSize: FadeTheme.fontMd
        color: Qt.rgba(1, 1, 1, 0.7)
        Layout.preferredWidth: 110
        Layout.minimumWidth:   110
        wrapMode: Text.NoWrap
    }

    Item {
        id: contentSlot
        Layout.fillWidth: true
        implicitHeight: children.length > 0 ? children[0].implicitHeight : 0
    }
}
