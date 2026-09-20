import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15
import Qt5Compat.GraphicalEffects
import Fade 1.0

Item {
    id: root
    anchors.fill: parent
    visible: false
    z: 9999

    property string projectName:   "My Project"
    property int    projectWidth:  1920
    property int    projectHeight: 1080
    property int    projectFps:    30
    property string folderPath:    ""
    property bool   saving:        false

    signal close()
    signal created(string name, int w, int h, int fps, string folder)

    onVisibleChanged: {
        if (visible) {
            overlay.opacity = 0
            panel.opacity   = 0
            panel.scale     = 0.97
            panel.y         = panel.parent.height / 2 - panel.height / 2 - 16
            showAnim.start()
        }
    }

    ParallelAnimation {
        id: showAnim
        NumberAnimation {
            target: overlay; property: "opacity"
            from: 0; to: 1; duration: 150
            easing.type: Easing.OutQuad
        }
        NumberAnimation {
            target: panel; property: "opacity"
            from: 0; to: 1; duration: 180
            easing.type: Easing.OutBack; easing.overshoot: 1.4
        }
        NumberAnimation {
            target: panel; property: "scale"
            from: 0.97; to: 1.0; duration: 180
            easing.type: Easing.OutBack; easing.overshoot: 1.4
        }
        NumberAnimation {
            target: panel; property: "y"
            to: panel.parent.height / 2 - panel.height / 2
            duration: 180
            easing.type: Easing.OutBack; easing.overshoot: 1.4
        }
    }

    Rectangle {
        id: overlay
        anchors.fill: parent
        color: FadeTheme.bgOverlay
        opacity: 0
        MouseArea { anchors.fill: parent; onClicked: root.close() }
    }

    Rectangle {
        id: panel
        width:  Math.min(500, root.width * 0.96)
        height: Math.min(panelColumn.implicitHeight, root.height * 0.90)
        x: root.width  / 2 - width  / 2
        y: root.height / 2 - height / 2
        color:  FadeTheme.bgPanel
        radius: FadeTheme.radiusLg
        border.color: FadeTheme.borderSubtle
        border.width: 1
        clip: true
        opacity: 0

        layer.enabled: true
        layer.effect: DropShadow {
            radius: 64; samples: 33
            verticalOffset: 24
            color: "#b3000000"
        }

        ColumnLayout {
            id: panelColumn
            anchors { left: parent.left; right: parent.right; top: parent.top }
            spacing: 0

            RowLayout {
                Layout.fillWidth:   true
                Layout.leftMargin:  22; Layout.rightMargin: 22
                Layout.topMargin:   18; Layout.bottomMargin: 14
                spacing: 0

                Text {
                    text: "New Project"
                    font.family:    FadeTheme.fontFamily
                    font.pixelSize: FadeTheme.fontLg
                    font.weight:    Font.DemiBold
                    color:          FadeTheme.textPrimary
                }
                Item { Layout.fillWidth: true }

                Rectangle {
                    width: 28; height: 28
                    radius: FadeTheme.radiusSm
                    color: closeArea.containsMouse ? Qt.rgba(1, 1, 1, 0.12) : Qt.rgba(1, 1, 1, 0.06)
                    Behavior on color { ColorAnimation { duration: FadeTheme.durationFast } }

                    Text {
                        anchors.centerIn: parent
                        text: "✕"
                        font.pixelSize: 13
                        color: closeArea.containsMouse ? "#ffffff" : Qt.rgba(1, 1, 1, 0.5)
                        Behavior on color { ColorAnimation { duration: FadeTheme.durationFast } }
                    }
                    MouseArea {
                        id: closeArea
                        anchors.fill: parent
                        hoverEnabled: true
                        cursorShape:  Qt.PointingHandCursor
                        onClicked:    root.close()
                    }
                }
            }

            Rectangle { Layout.fillWidth: true; height: 1; color: Qt.rgba(1, 1, 1, 0.07) }

            ScrollView {
                Layout.fillWidth: true
                Layout.preferredHeight: Math.min(sectionsCol.implicitHeight, root.height * 0.90 - 140)
                contentWidth: availableWidth
                ScrollBar.horizontal.policy: ScrollBar.AlwaysOff

                ColumnLayout {
                    id: sectionsCol
                    width: parent.width
                    spacing: 0

                    ColumnLayout {
                        Layout.fillWidth:   true
                        Layout.leftMargin:  22; Layout.rightMargin: 22
                        Layout.topMargin:   16; Layout.bottomMargin: 16
                        spacing: 10

                        Text {
                            text: "PROJECT"
                            font.family:        FadeTheme.fontFamily
                            font.pixelSize:     FadeTheme.fontSm
                            font.weight:        Font.DemiBold
                            font.letterSpacing: 0.9
                            color: Qt.rgba(1, 1, 1, 0.30)
                        }

                        FadeFormRow {
                            label: "Name"
                            Layout.fillWidth: true
                            content: FadeInput {
                                Layout.fillWidth: true
                                placeholderText: "My Project"
                                text: root.projectName
                                onTextChanged: root.projectName = text
                            }
                        }

                        FadeFormRow {
                            label: "Resolution"
                            Layout.fillWidth: true
                            content: RowLayout {
                                spacing: 8
                                FadeInput {
                                    Layout.preferredWidth: 90
                                    text: root.projectWidth.toString()
                                    inputMethodHints: Qt.ImhDigitsOnly
                                    horizontalAlignment: TextInput.AlignHCenter
                                    onTextChanged: root.projectWidth = parseInt(text) || 1920
                                }
                                Text { text: "×"; color: FadeTheme.textDim; font.pixelSize: FadeTheme.fontMd }
                                FadeInput {
                                    Layout.preferredWidth: 90
                                    text: root.projectHeight.toString()
                                    inputMethodHints: Qt.ImhDigitsOnly
                                    horizontalAlignment: TextInput.AlignHCenter
                                    onTextChanged: root.projectHeight = parseInt(text) || 1080
                                }
                            }
                        }

                        FadeFormRow {
                            label: "Frame Rate"
                            Layout.fillWidth: true
                            content: FadeSelect {
                                Layout.fillWidth: true
                                model: [24, 25, 30, 60]
                                displayText: currentText + " fps"
                                onCurrentValueChanged: root.projectFps = currentValue
                            }
                        }
                    }

                    Rectangle { Layout.fillWidth: true; height: 1; color: Qt.rgba(1, 1, 1, 0.06) }

                    ColumnLayout {
                        Layout.fillWidth:   true
                        Layout.leftMargin:  22; Layout.rightMargin: 22
                        Layout.topMargin:   16; Layout.bottomMargin: 16
                        spacing: 10

                        Text {
                            text: "LOCATION"
                            font.family:        FadeTheme.fontFamily
                            font.pixelSize:     FadeTheme.fontSm
                            font.weight:        Font.DemiBold
                            font.letterSpacing: 0.9
                            color: Qt.rgba(1, 1, 1, 0.30)
                        }

                        RowLayout {
                            Layout.fillWidth: true
                            spacing: 10

                            Text {
                                text: "Folder"
                                font.family:    FadeTheme.fontFamily
                                font.pixelSize: FadeTheme.fontMd
                                color: Qt.rgba(1, 1, 1, 0.7)
                                Layout.preferredWidth: 110
                            }

                            Rectangle {
                                Layout.fillWidth: true
                                height: 28
                                color:  Qt.rgba(1, 1, 1, 0.04)
                                radius: FadeTheme.radiusSm
                                border.color: Qt.rgba(1, 1, 1, 0.12)
                                border.width: 1
                                clip: true

                                Text {
                                    anchors { left: parent.left; right: parent.right; verticalCenter: parent.verticalCenter }
                                    leftPadding: 10; rightPadding: 10
                                    text: root.folderPath === "" ? "No folder selected" : root.folderPath
                                    font.family:    FadeTheme.fontFamily
                                    font.pixelSize: FadeTheme.fontBase
                                    color: root.folderPath === "" ? Qt.rgba(1, 1, 1, 0.25) : "#e0e0e8"
                                    font.italic: root.folderPath === ""
                                    elide: Text.ElideLeft
                                }
                            }

                            FadeButton {
                                text: "Browse"
                                variant: "browse"
                                onClicked: folderDialog.open()
                            }
                        }

                        RowLayout {
                            visible: root.folderPath !== ""
                            spacing: 8

                            Text {
                                text: "Will save to"
                                font.family:    FadeTheme.fontFamily
                                font.pixelSize: FadeTheme.fontSm
                                color: Qt.rgba(1, 1, 1, 0.30)
                            }
                            Text {
                                text: root.folderPath + "/" + root.projectName + ".fade"
                                font.family:    FadeTheme.fontMono
                                font.pixelSize: FadeTheme.fontSm
                                color: Qt.rgba(0.42, 0.39, 1, 0.85)
                                elide: Text.ElideLeft
                                Layout.fillWidth: true
                            }
                        }
                    }
                }
            }

            Rectangle { Layout.fillWidth: true; height: 1; color: Qt.rgba(1, 1, 1, 0.06) }

            RowLayout {
                Layout.fillWidth:   true
                Layout.leftMargin:  22; Layout.rightMargin: 22
                Layout.topMargin:   14; Layout.bottomMargin: 18
                spacing: 10

                Text {
                    id: savingText
                    text: "Saving…"
                    visible: root.saving
                    font.family:    FadeTheme.fontFamily
                    font.pixelSize: FadeTheme.fontBase
                    color: FadeTheme.teal

                    SequentialAnimation on opacity {
                        running: savingText.visible
                        loops:   Animation.Infinite
                        NumberAnimation { to: 0.4; duration: 500; easing.type: Easing.InOutSine }
                        NumberAnimation { to: 1.0; duration: 500; easing.type: Easing.InOutSine }
                    }
                }

                Item { Layout.fillWidth: true }

                FadeButton {
                    text: "Cancel"
                    variant: "default"
                    onClicked: root.close()
                }

                FadeButton {
                    text: root.saving ? "Creating…" : "Create Project"
                    variant: "primary"
                    enabled: root.folderPath !== "" && root.projectName !== "" && !root.saving
                    onClicked: {
                        root.saving = true
                        root.created(root.projectName, root.projectWidth,
                                     root.projectHeight, root.projectFps,
                                     root.folderPath)
                    }
                }
            }
        }
    }

    FolderDialog {
        id: folderDialog
        onAccepted: root.folderPath = selectedFolder.toString().replace("file:///", "")
    }
}
