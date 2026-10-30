"""IoRacket receiver. Run from the host/ folder: python main.py"""
import sys

from PySide6 import QtWidgets

from src.ble_manager import BLEManager
from src.simulator import SimulatedDevice
from src.visualizer import MainWindow


def main():
    app = QtWidgets.QApplication(sys.argv)
    window = MainWindow(BLEManager(), SimulatedDevice())
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
