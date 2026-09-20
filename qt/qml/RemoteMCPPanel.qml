import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15
import Qt5Compat.GraphicalEffects
import Fade 1.0

Rectangle {
    id: root
    color: FadeTheme.bgBase
    clip:  true

    property bool   connected:  false
    property string serverUrl:  "http://localhost:7654/sse"
    property string backendUrl: "http://localhost:8000"
    property var    messages:   []
    property bool   streaming:  false

    signal sendRequested(string text)
    signal connectRequested()
    signal disconnectRequested()

    Rectangle {
        width: 1; height: parent.height
        color: FadeTheme.borderStrong
    }

    ColumnLayout {
        anchors.fill: parent
        spacing: 0

        Rectangle {
            Layout.fillWidth: true
            height: headerRow.implicitHeight + 20
            color: FadeTheme.bgSurface

            Rectangle {
                anchors { left: parent.left; right: parent.right; bottom: parent.bottom }
                height: 1; color: FadeTheme.borderStrong
            }

            RowLayout {
                id: headerRow
                anchors { left: parent.left; right: parent.right; verticalCenter: parent.verticalCenter }
                leftPadding: 14; rightPadding: 14
                spacing: 10

                RowLayout {
                    spacing: 10

                    Text {
                        text: "Remote MCP"
                        font.family:    FadeTheme.fontFamily
                        font.pixelSize: FadeTheme.fontMd
                        font.weight:    Font.DemiBold
                        color: FadeTheme.accentPurpleLight
                        font.letterSpacing: 0.26
                    }

                    Rectangle {
                        height: 20
                        width:  badgeText.implicitWidth + 16
                        radius: FadeTheme.radiusFull
                        color:  root.connected ? FadeTheme.greenBg : Qt.rgba(0.58, 0.64, 0.72, 0.10)
                        border.color: root.connected ? Qt.rgba(0.20, 0.83, 0.60, 0.30)
                                                     : Qt.rgba(0.58, 0.64, 0.72, 0.15)
                        border.width: 1

                        Text {
                            id: badgeText
                            anchors.centerIn: parent
                            text: root.connected ? "Connected" : "Disconnected"
                            font.family:    FadeTheme.fontFamily
                            font.pixelSize: FadeTheme.fontSm
                            font.weight:    Font.Medium
                            color: root.connected ? FadeTheme.green : "#64748b"
                        }
                    }
                }

                Item { Layout.fillWidth: true }

                FadeButton {
                    text: root.connected ? "Disconnect" : "Connect"
                    variant: root.connected ? "danger" : "primary"
                    onClicked: root.connected ? root.disconnectRequested() : root.connectRequested()
                }

                FadeButton {
                    text: "🗑"
                    variant: "ghost"
                    font.pixelSize: 16
                    onClicked: root.messages = []
                }
            }
        }

        Rectangle {
            Layout.fillWidth: true
            height: configCol.implicitHeight + 24
            color: FadeTheme.bgSurface

            Rectangle {
                anchors { left: parent.left; right: parent.right; bottom: parent.bottom }
                height: 1; color: FadeTheme.borderStrong
            }

            ColumnLayout {
                id: configCol
                anchors { left: parent.left; right: parent.right; verticalCenter: parent.verticalCenter }
                leftPadding: 14; rightPadding: 14
                spacing: 8

                GridLayout {
                    columns: 2
                    columnSpacing: 10
                    Layout.fillWidth: true

                    Text {
                        text: "Server URL"
                        font.family:    FadeTheme.fontFamily
                        font.pixelSize: FadeTheme.fontSm
                        font.weight:    Font.Medium
                        color: FadeTheme.textDisabled
                        horizontalAlignment: Text.AlignRight
                        Layout.preferredWidth: 90
                    }
                    FadeInput {
                        Layout.fillWidth: true
                        text: root.serverUrl
                        monoFont: true
                        onTextChanged: root.serverUrl = text
                    }

                    Text {
                        text: "Backend"
                        font.family:    FadeTheme.fontFamily
                        font.pixelSize: FadeTheme.fontSm
                        font.weight:    Font.Medium
                        color: FadeTheme.textDisabled
                        horizontalAlignment: Text.AlignRight
                        Layout.preferredWidth: 90
                    }
                    FadeInput {
                        Layout.fillWidth: true
                        text: root.backendUrl
                        monoFont: true
                        onTextChanged: root.backendUrl = text
                    }
                }
            }
        }

        ListView {
            id: messageList
            Layout.fillWidth:  true
            Layout.fillHeight: true
            topMargin: 12; bottomMargin: 12
            leftMargin: 14; rightMargin: 14
            spacing: 10
            clip: true
            model: root.messages

            ScrollBar.vertical: ScrollBar {
                width: 4
                contentItem: Rectangle { radius: 4; color: FadeTheme.borderStrong }
                background:  Rectangle { color: "transparent" }
            }

            onCountChanged: Qt.callLater(() => messageList.positionViewAtEnd())

            header: Item {
                width: messageList.width
                height: root.messages.length === 0 ? messageList.height : 0
                visible: root.messages.length === 0

                ColumnLayout {
                    anchors.centerIn: parent
                    spacing: 8

                    Text {
                        text: "⚡"
                        font.pixelSize: 36
                        Layout.alignment: Qt.AlignHCenter
                        color: FadeTheme.textPlaceholder
                    }
                    Text {
                        text: "Connect to an MCP server"
                        font.family:    FadeTheme.fontFamily
                        font.pixelSize: FadeTheme.fontMd
                        color: "#4b5563"
                        Layout.alignment: Qt.AlignHCenter
                    }
                    Text {
                        text: "Enter a server URL above and click Connect"
                        font.family:    FadeTheme.fontFamily
                        font.pixelSize: FadeTheme.fontBase
                        color: FadeTheme.textPlaceholder
                        Layout.alignment: Qt.AlignHCenter
                    }
                }
            }

            delegate: Item {
                id: msgItem
                width: messageList.width - messageList.leftMargin - messageList.rightMargin
                height: bubbleCol.implicitHeight

                opacity: 0
                transform: Translate { id: msgTranslate; y: 4 }

                Component.onCompleted: fadeInAnim.start()

                ParallelAnimation {
                    id: fadeInAnim
                    NumberAnimation { target: msgItem;      property: "opacity"; from: 0; to: 1; duration: 180; easing.type: Easing.OutQuad }
                    NumberAnimation { target: msgTranslate; property: "y";       from: 4; to: 0; duration: 180; easing.type: Easing.OutQuad }
                }

                property var msg: root.messages[index]

                ColumnLayout {
                    id: bubbleCol
                    width: parent.width
                    spacing: 4

                    Loader {
                        active: msg.role === "user"
                        Layout.alignment: Qt.AlignRight
                        Layout.maximumWidth: parent.width * 0.90
                        sourceComponent: Rectangle {
                            gradient: Gradient {
                                orientation: Gradient.Horizontal
                                GradientStop { position: 0.0; color: "#5b21b6" }
                                GradientStop { position: 1.0; color: "#4c1d95" }
                            }
                            radius: 14
                            width:  msgText.implicitWidth + 24
                            height: msgText.implicitHeight + 16

                            Text {
                                id: msgText
                                anchors { left: parent.left; right: parent.right; verticalCenter: parent.verticalCenter }
                                leftPadding: 12; rightPadding: 12
                                text: msg.content
                                font.family:    FadeTheme.fontFamily
                                font.pixelSize: FadeTheme.fontMd
                                color: "#ede9fe"
                                wrapMode: Text.WrapAtWordBoundaryOrAnywhere
                                lineHeight: 1.5
                            }
                        }
                    }

                    Loader {
                        active: msg.role === "assistant"
                        Layout.alignment: Qt.AlignLeft
                        Layout.maximumWidth: parent.width * 0.90
                        sourceComponent: Rectangle {
                            color:  FadeTheme.bgAssistant
                            radius: FadeTheme.radiusMd
                            border.color: FadeTheme.borderStrong
                            border.width: 1
                            width:  Math.min(aText.implicitWidth + 24, msgItem.width * 0.90)
                            height: aText.implicitHeight + 16

                            Text {
                                id: aText
                                anchors { left: parent.left; right: parent.right; verticalCenter: parent.verticalCenter }
                                leftPadding: 12; rightPadding: 12
                                text: msg.content
                                font.family:    FadeTheme.fontFamily
                                font.pixelSize: FadeTheme.fontMd
                                color: FadeTheme.textBody
                                wrapMode: Text.WrapAtWordBoundaryOrAnywhere
                                lineHeight: 1.6

                                Rectangle {
                                    visible: root.streaming && index === root.messages.length - 1
                                    width: 2; height: 14
                                    color: FadeTheme.accentPurpleLight
                                    anchors { left: parent.right; verticalCenter: parent.verticalCenter }

                                    SequentialAnimation on opacity {
                                        running: parent.visible
                                        loops:   Animation.Infinite
                                        NumberAnimation { to: 0; duration: 400; easing.type: Easing.Linear }
                                        NumberAnimation { to: 1; duration: 400; easing.type: Easing.Linear }
                                    }
                                }
                            }
                        }
                    }

                    Loader {
                        active: msg.role === "tool_call"
                        Layout.fillWidth: true
                        sourceComponent: Rectangle {
                            width:  parent.width
                            height: toolText.implicitHeight + 12
                            color:  FadeTheme.yellowBg
                            radius: FadeTheme.radiusMd
                            border.color: Qt.rgba(0.98, 0.75, 0.14, 0.20)
                            border.width: 1

                            Text {
                                id: toolText
                                anchors { left: parent.left; right: parent.right; verticalCenter: parent.verticalCenter }
                                leftPadding: 10; rightPadding: 10
                                text: msg.content
                                font.family:    FadeTheme.fontMono
                                font.pixelSize: FadeTheme.fontSm
                                color: FadeTheme.yellow
                                wrapMode: Text.WrapAtWordBoundaryOrAnywhere
                            }
                        }
                    }

                    Loader {
                        active: msg.role === "tool_result"
                        Layout.fillWidth: true
                        sourceComponent: Rectangle {
                            width:  parent.width
                            height: resultText.implicitHeight + 12
                            color:  FadeTheme.greenBg
                            radius: FadeTheme.radiusMd
                            border.color: Qt.rgba(0.20, 0.83, 0.60, 0.20)
                            border.width: 1

                            Text {
                                id: resultText
                                anchors { left: parent.left; right: parent.right; verticalCenter: parent.verticalCenter }
                                leftPadding: 10; rightPadding: 10
                                text: msg.content
                                font.family:    FadeTheme.fontMono
                                font.pixelSize: FadeTheme.fontSm
                                color: FadeTheme.green
                                wrapMode: Text.WrapAtWordBoundaryOrAnywhere
                            }
                        }
                    }

                    Loader {
                        active: msg.role === "error"
                        Layout.fillWidth: true
                        sourceComponent: Rectangle {
                            width:  parent.width
                            height: errText.implicitHeight + 16
                            color:  Qt.rgba(0.94, 0.27, 0.27, 0.08)
                            radius: FadeTheme.radiusMd
                            border.color: Qt.rgba(0.94, 0.27, 0.27, 0.25)
                            border.width: 1

                            Text {
                                id: errText
                                anchors { left: parent.left; right: parent.right; verticalCenter: parent.verticalCenter }
                                leftPadding: 12; rightPadding: 12
                                text: msg.content
                                font.family:    FadeTheme.fontFamily
                                font.pixelSize: FadeTheme.fontBase
                                color: FadeTheme.red
                                wrapMode: Text.WrapAtWordBoundaryOrAnywhere
                            }
                        }
                    }
                }
            }
        }

        Rectangle {
            Layout.fillWidth: true
            height: inputRow.implicitHeight + 20
            color: FadeTheme.bgSurface

            Rectangle {
                anchors { left: parent.left; right: parent.right; top: parent.top }
                height: 1; color: FadeTheme.borderStrong
            }

            RowLayout {
                id: inputRow
                anchors { left: parent.left; right: parent.right; verticalCenter: parent.verticalCenter }
                leftPadding: 14; rightPadding: 14
                spacing: 8

                ScrollView {
                    Layout.fillWidth: true
                    Layout.preferredHeight: Math.min(chatInput.implicitHeight, 120)
                    Layout.minimumHeight:   36
                    ScrollBar.horizontal.policy: ScrollBar.AlwaysOff

                    TextArea {
                        id: chatInput
                        placeholderText: "Send a message…"
                        font.family:    FadeTheme.fontFamily
                        font.pixelSize: FadeTheme.fontMd
                        color:          FadeTheme.textBody
                        wrapMode:       TextArea.Wrap
                        enabled:        !root.streaming
                        padding: 0
                        leftPadding: 12; rightPadding: 12
                        topPadding:   8; bottomPadding: 8

                        background: Rectangle {
                            color:  FadeTheme.bgInput
                            radius: FadeTheme.radiusMd
                            border.color: chatInput.activeFocus ? FadeTheme.borderFocus : FadeTheme.borderStrong
                            border.width: 1
                            Behavior on border.color { ColorAnimation { duration: FadeTheme.durationFast } }
                        }

                        Keys.onReturnPressed: (event) => {
                            if (event.modifiers & Qt.ControlModifier || !event.isAutoRepeat) {
                                sendBtn.clicked()
                                event.accepted = true
                            }
                        }
                    }
                }

                FadeButton {
                    id: sendBtn
                    text:    root.streaming ? "Stop" : "Send"
                    variant: root.streaming ? "danger" : "primary"
                    leftPadding: 18; rightPadding: 18
                    topPadding:   8; bottomPadding: 8
                    enabled: root.streaming || chatInput.text.trim() !== ""
                    onClicked: {
                        if (root.streaming) {
                            // TODO: emit stop signal
                        } else {
                            root.sendRequested(chatInput.text)
                            chatInput.clear()
                        }
                    }
                }
            }
        }
    }
}
