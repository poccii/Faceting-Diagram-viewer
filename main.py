import sys
from PySide6.QtWidgets import QApplication
from ui_main import MainWindow

app = QApplication(sys.argv)

window = MainWindow()
window.show()
print("Debug: App starting")
sys.exit(app.exec())