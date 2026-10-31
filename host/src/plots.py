"""Six-axis plot grid shared by the live view and the replay window.

Layout: 3 rows x 2 columns, acceleration on the left, angular velocity on the right, one axis per plot,
all x axes linked. By default the y range is fixed to the sensor range with dashed limit lines, so a
saturated signal visibly sits on the line; autoscale can be switched on to see small movements.
"""
import numpy as np
import pyqtgraph as pg
from PySide6 import QtCore

AXIS_COLORS = ["#e74c3c", "#27ae60", "#2e86de"]  # x, y, z


class SixAxisPlot(pg.GraphicsLayoutWidget):
    def __init__(self, accel_range_g=16, gyro_range_dps=2000):
        super().__init__()
        self.ranges = [accel_range_g, gyro_range_dps]
        self.plots = [[None] * 3 for _ in range(2)]   # [column][axis]
        self.curves = [[None] * 3 for _ in range(2)]
        self.markers = [[None] * 3 for _ in range(2)]  # red dots on saturated samples
        self.cursors = []                               # vertical line at the video position, one per plot
        limit_pen = pg.mkPen("#c0392b", width=1, style=QtCore.Qt.DashLine)

        for col, (name, unit) in enumerate((("加速度", "g"), ("角速度", "°/s"))):
            for axis in range(3):
                p = self.addPlot(row=axis, col=col)
                p.setTitle(f"{name} {'XYZ'[axis]}", size="9pt")
                p.setLabel("left", unit)
                p.showGrid(x=True, y=True, alpha=0.25)
                if axis < 2:
                    p.getAxis("bottom").setStyle(showValues=False)
                else:
                    p.setLabel("bottom", "时间", units="s")
                if self.plots[0][0] is not None:
                    p.setXLink(self.plots[0][0])
                for sign in (1, -1):
                    p.addItem(pg.InfiniteLine(pos=sign * self.ranges[col], angle=0, pen=limit_pen))
                self.curves[col][axis] = p.plot(pen=pg.mkPen(AXIS_COLORS[axis], width=1.2), connect="finite")
                self.markers[col][axis] = p.plot(pen=None, symbol="o", symbolSize=4,
                                                 symbolBrush="#c0392b", symbolPen=None)
                cursor = pg.InfiniteLine(angle=90, pen=pg.mkPen("#f1c40f", width=1.5))
                cursor.setVisible(False)
                p.addItem(cursor)
                self.cursors.append(cursor)
                self.plots[col][axis] = p
        self.set_autoscale(False)

    def all_plots(self):
        return [p for column in self.plots for p in column]

    def set_autoscale(self, on: bool):
        for col in range(2):
            for p in self.plots[col]:
                if on:
                    p.enableAutoRange(axis="y")
                else:
                    r = self.ranges[col] * 1.08
                    p.setYRange(-r, r, padding=0)

    def set_data(self, t, acc, gyro, saturated=None):
        """t: (n,), acc/gyro: (n, 3) in g and deg/s, saturated: optional (n, 6) bool mask to mark."""
        for col, values in enumerate((acc, gyro)):
            for axis in range(3):
                self.curves[col][axis].setData(t, values[:, axis])
                if saturated is not None:
                    m = saturated[:, col * 3 + axis]
                    self.markers[col][axis].setData(t[m], values[m, axis])

    def set_x_range(self, start, end):
        self.plots[0][0].setXRange(start, end, padding=0)

    def set_cursor(self, x=None):
        """Show a vertical cursor at x (same units as t), or hide it with None."""
        for c in self.cursors:
            c.setVisible(x is not None)
            if x is not None:
                c.setPos(x)
