import QtQuick 2.15
import QtQuick.Window 2.15
import Fade 1.0

// ── Root window — replace this with your real layout ─────────────────────────
Window {
    id: root
    visible: true
    width:  1280
    height: 800
    title:  "Fade"
    color:  FadeTheme.bgBase   // #0f1117 — matches the app dark theme

    // ── Demo: show the CreateProjectModal on startup ──────────────────────────
    property bool showModal: true

    CreateProjectModal {
        visible:   root.showModal
        onClose:   root.showModal = false
        onCreated: (name, w, h, fps, folder) => {
            console.log("Create project:", name, w+"×"+h, fps+"fps", folder)
            root.showModal = false
        }
    }

    // ── Demo: RemoteMCPPanel on the right ─────────────────────────────────────
    RemoteMCPPanel {
        anchors { top: parent.top; bottom: parent.bottom; right: parent.right }
        width: 380
        connected: false
        messages: [
            { role: "user",      content: "Hello, can you help me?" },
            { role: "assistant", content: "Sure! What do you need?" },
            { role: "tool_call", content: "get_timeline_state()" },
            { role: "tool_result",content: "{ clips: 3, duration: 120 }" },
        ]
        onSendRequested: (text) => console.log("Send:", text)
        onConnectRequested:    console.log("Connect")
        onDisconnectRequested: console.log("Disconnect")
    }
}
