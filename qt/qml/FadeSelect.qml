import QtQuick 2.15
import QtQuick.Controls 2.15
import Fade 1.0

ComboBox {
    id: combo
    font.family: FadeTheme.fontFamily
    font.pixelSize: FadeTheme.fontMd

    background: Rectangle {
        radius: FadeTheme.radiusSm
        color:  Qt.rgba(1, 1, 1, 0.06)
        border.color: combo.activeFocus || combo.popup.visible
                      ? FadeTheme.borderFocus : FadeTheme.borderStrong
        border.width: 1
        Behavior on border.color { ColorAnimation { duration: FadeTheme.durationFast } }
    }

    contentItem: Text {
        leftPadding: 8
        text:  combo.displayText
        font: combo.font
        color: FadeTheme.textPrimary
        verticalAlignment: Text.AlignVCenter
    }

    indicator: Text {
        x: combo.width - width - 8
        y: combo.height / 2 - height / 2
        text: "▾"
        font.pixelSize: 10
        color: FadeTheme.textDim
    }

    popup: Popup {
        y: combo.height + 3
        width: combo.width
        padding: 0
        background: Rectangle {
            color:  "#1e1e28"
            radius: FadeTheme.radiusSm
            border.color: Qt.rgba(1, 1, 1, 0.10)
            border.width: 1
        }
        contentItem: ListView {
            implicitHeight: Math.min(contentHeight, 200)
            model: combo.delegateModel
            clip:  true
            ScrollBar.vertical: ScrollBar {}
        }
    }

    delegate: ItemDelegate {
        width: parent ? parent.width : 0
        contentItem: Text {
            text:  modelData !== undefined ? modelData : combo.model[index]
            font:  combo.font
            color: FadeTheme.textPrimary
            verticalAlignment: Text.AlignVCenter
            leftPadding: 8
        }
        background: Rectangle {
            color: parent.hovered ? Qt.rgba(1, 1, 1, 0.08) : "transparent"
        }
    }
}
