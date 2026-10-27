"""Entry point: python main.py"""
import sys

from PySide6.QtWidgets import QApplication

from desktop.main_window import MainWindow


def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
