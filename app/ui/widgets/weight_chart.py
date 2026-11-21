"""График динамики веса (QtCharts) по vital_signs."""
from __future__ import annotations
from datetime import datetime

from PySide6.QtCharts import QChart, QChartView, QDateTimeAxis, QLineSeries, QScatterSeries, QValueAxis
from PySide6.QtCore import QDateTime, Qt
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QLabel, QStackedLayout, QWidget


class WeightChart(QWidget):
    def __init__(self):
        super().__init__()
        self.chart = QChart()
        self.chart.legend().hide()
        self.view = QChartView(self.chart)
        self.view.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.empty = QLabel("<h3>Нет данных</h3><p>Вес ещё не измерялся ни на одном приёме.</p>")
        self.empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.stack = QStackedLayout(self)
        self.stack.addWidget(self.view)
        self.stack.addWidget(self.empty)

    def set_points(self, points: list[tuple[str, float]]) -> None:
        self.chart.removeAllSeries()
        for ax in self.chart.axes():
            self.chart.removeAxis(ax)
        if not points:
            self.stack.setCurrentWidget(self.empty)
            return
        self.stack.setCurrentWidget(self.view)
        line, dots = QLineSeries(), QScatterSeries()
        dots.setMarkerSize(9)
        line.setPen(QPen(QColor("#0f766e"), 2.2))
        dots.setColor(QColor("#0f766e"))
        dots.setBorderColor(QColor("#ffffff"))
        for iso, kg in points:
            ms = QDateTime(datetime.fromisoformat(iso)).toMSecsSinceEpoch()
            line.append(ms, kg)
            dots.append(ms, kg)
        self.chart.addSeries(line)
        self.chart.addSeries(dots)
        x = QDateTimeAxis()
        x.setFormat("dd.MM.yy")
        x.setTitleText("Дата приёма")
        y = QValueAxis()
        y.setTitleText("Вес, кг")
        lo, hi = min(k for _, k in points), max(k for _, k in points)
        pad = max((hi - lo) * 0.2, 0.1)
        y.setRange(max(lo - pad, 0), hi + pad)
        y.setLabelFormat("%.2f")
        self.chart.addAxis(x, Qt.AlignmentFlag.AlignBottom)
        self.chart.addAxis(y, Qt.AlignmentFlag.AlignLeft)
        for s in (line, dots):
            s.attachAxis(x)
            s.attachAxis(y)
        if len(points) == 1:  # одна точка: расширить ось времени вокруг неё
            ms = QDateTime(datetime.fromisoformat(points[0][0])).toMSecsSinceEpoch()
            x.setRange(QDateTime.fromMSecsSinceEpoch(ms - 15 * 86400000), QDateTime.fromMSecsSinceEpoch(ms + 15 * 86400000))
