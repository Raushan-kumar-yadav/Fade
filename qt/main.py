 

import sys
from pathlib import Path
from PySide6.QtGui import QGuiApplication, QFontDatabase
from PySide6.QtQml import QQmlApplicationEngine, qmlRegisterSingletonType, qmlRegisterType
from PySide6.QtCore import QUrl

#   Resource path helper  
def qrc(path: str) -> QUrl:
    """Return a QUrl pointing into the embedded .qrc at prefix /fade/"""
    return QUrl(f"qrc:/fade/{path}")

def main():
    app = QGuiApplication(sys.argv)
    app.setApplicationName("Fade")
    app.setOrganizationName("FadeTeam")

    #   Load Inter font  
  
    for weight in ("Regular", "Medium", "SemiBold", "Bold"):
        QFontDatabase.addApplicationFont(f":/fade/fonts/Inter-{weight}.ttf")

    engine = QQmlApplicationEngine()

    # Tell the engine  
    engine.addImportPath("qrc:/")

 
    qmlRegisterSingletonType(
        qrc("qml/FadeTheme.qml"),   
        "Fade", # module URI
        1, 0, # major, minor version
        "FadeTheme" 
    )

    #  Register reusable components  
    components = [
        ("FadeButton", "qml/FadeButton.qml"),
        ("FadeInput", "qml/FadeInput.qml"),
        ("FadeSelect", "qml/FadeSelect.qml"),
        ("FadeToggle", "qml/FadeToggle.qml"),
        ("FadeFormRow", "qml/FadeFormRow.qml"),
        ("CreateProjectModal",  "qml/CreateProjectModal.qml"),
        ("RemoteMCPPanel", "qml/RemoteMCPPanel.qml"),
    ]
    for name, path in components:
        qmlRegisterType(qrc(path), "Fade", 1, 0, name)

    #   Load root window  
    engine.load(qrc("qml/main.qml"))

    if not engine.rootObjects():
        sys.exit(-1)

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
