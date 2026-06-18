#!/usr/bin/env python3
"""
LMT spacetime-trajectory applet (intent-driven)
===============================================

Live ARTIQ applet that reads the broadcast ``pulse_intent_record`` dataset,
reconstructs the spacetime trajectory of the most recently recorded LMT
sequence and draws it the same way the ``lmt_sim`` simulator does: a two-panel
space-time / momentum diagram.

On the declarative-LMT stack the trajectory is *recorded*, not inferred: every
atom-affecting event archives what it does to the populations (see
``repository.lib.pulse_intent``), so this applet walks that intent stream
exactly -- no Rabi-probability guesswork. The reconstruction lives in
``repository.lib.physics.lmt_spacetime``; this module only does the drawing, in
the usual icl_experiments pyqtgraph idiom (black background, white text, colours
encouraged).

Top panel:    z position (mm) vs time (µs)
Bottom panel: momentum  v_z (recoils) vs time (µs), x-linked to the top.

Each branch (cloud) gets its own colour. Ground-state segments are solid,
excited-state segments dotted. Pulses are shaded blue (up beam, ``delta_m > 0``)
or red (down beam, ``delta_m < 0``); the bottom panel overlays each pulse's
addressed momentum band. Cleared branches are dotted and end in a cross.

Launch (e.g. from an experiment via the CCB, or by hand)::

    ${python} -m repository.lib.applets.lmt_trajectory_applet pulse_intent_record
"""

import logging

import numpy as np
import pyqtgraph as pg
from artiq.applets.simple import TitleApplet
from pyqtgraph.Qt import QtCore
from pyqtgraph.Qt import QtWidgets

from repository.lib.physics import lmt_spacetime as st

logger = logging.getLogger(__name__)

pg.setConfigOption("background", "k")
pg.setConfigOption("foreground", "w")
pg.setConfigOptions(antialias=True)

# Beam-direction colours (RGB): up beam (delta_m > 0) = blue, down = red.
PULSE_RGB = {+1: (66, 135, 245), -1: (235, 64, 52)}
CLEAROUT_RGB = (44, 160, 44)


class LMTTrajectoryPlot(pg.GraphicsLayoutWidget):
    def __init__(self, args, req):
        super().__init__()
        self.args = args
        self.setWindowTitle("LMT spacetime trajectory")
        self.setBackground("k")

        self.ax_z = self.addPlot(row=0, col=0)
        self.ax_m = self.addPlot(row=1, col=0)
        # Position panel is taller, like the simulator's 3:2 split.
        self.ci.layout.setRowStretchFactor(0, 3)
        self.ci.layout.setRowStretchFactor(1, 2)
        self.ax_m.setXLink(self.ax_z)

        for ax in (self.ax_z, self.ax_m):
            ax.showGrid(x=True, y=True, alpha=0.3)
        self.ax_z.setLabel("left", "z position", units="mm")
        self.ax_m.setLabel("left", "v_z (recoils)")
        self.ax_m.setLabel("bottom", "time", units="µs")

    # -- drawing helpers -----------------------------------------------------

    def _draw_styled_polyline(self, ax, x, y, seg_ground, color):
        """Plot (x, y) splitting into solid (ground) / dotted (excited) runs.

        Segment ``s`` (vertices ``s``..``s+1``) uses the state of vertex
        ``s+1``, matching the simulator's ``ls = "-" if is_ground[j+1]`` rule.
        Consecutive same-style segments are merged into one polyline.
        """
        n = len(x)
        if n < 2:
            return
        s = 0
        nseg = n - 1
        while s < nseg:
            style = bool(seg_ground[s + 1])
            e = s
            while e < nseg and bool(seg_ground[e + 1]) == style:
                e += 1
            pen = pg.mkPen(
                color=color,
                width=2,
                style=QtCore.Qt.SolidLine if style else QtCore.Qt.DotLine,
            )
            ax.plot(x[s : e + 1], y[s : e + 1], pen=pen)
            s = e

    def _draw_clouds(self, sequence, clouds):
        all_m = []
        for cloud in clouds:
            color = st.TAB10_RGB[cloud.color_index % len(st.TAB10_RGB)]
            t_z, z, t_m, m, ground, m_ground = st.build_plot_trace(sequence, cloud)
            all_m.extend(m.tolist())

            t_z_us = t_z * 1e6
            z_mm = z * 1e3
            t_m_us = t_m * 1e6

            self._draw_styled_polyline(self.ax_z, t_z_us, z_mm, ground, color)
            self._draw_styled_polyline(self.ax_m, t_m_us, m, m_ground, color)

            if not cloud.alive:
                # Dots on every point, a cross on the (cleared) final one.
                self.ax_z.plot(
                    t_z_us[:-1],
                    z_mm[:-1],
                    pen=None,
                    symbol="o",
                    symbolSize=5,
                    symbolBrush=color,
                    symbolPen=None,
                )
                self.ax_z.plot(
                    t_z_us[-1:],
                    z_mm[-1:],
                    pen=None,
                    symbol="x",
                    symbolSize=9,
                    symbolPen=pg.mkPen(color, width=2),
                )
                self.ax_m.plot(
                    t_m_us[:-1],
                    m[:-1],
                    pen=None,
                    symbol="o",
                    symbolSize=5,
                    symbolBrush=color,
                    symbolPen=None,
                )
                self.ax_m.plot(
                    t_m_us[-1:],
                    m[-1:],
                    pen=None,
                    symbol="x",
                    symbolSize=9,
                    symbolPen=pg.mkPen(color, width=2),
                )
        return all_m

    def _draw_pulses(self, sequence):
        """Shade each pulse and overlay its addressed momentum band."""
        addressed_bar_padding = 0.05
        t_event = 0.0
        for event in sequence:
            if isinstance(event, st.Pulse):
                t0 = t_event * 1e6
                t1 = (t_event + event.duration) * 1e6
                r, g, b = PULSE_RGB[event.k]
                for ax in (self.ax_z, self.ax_m):
                    region = pg.LinearRegionItem(
                        values=[t0, t1],
                        movable=False,
                        brush=pg.mkBrush(r, g, b, 30),
                        pen=pg.mkPen(r, g, b, 110, width=1),
                    )
                    region.setZValue(-10)
                    ax.addItem(region, ignoreBounds=True)

                if event.m_low is not None:
                    m_low = event.m_low - addressed_bar_padding
                    m_high = event.m_high + addressed_bar_padding
                    rect = QtWidgets.QGraphicsRectItem(
                        t0, m_low, t1 - t0, m_high - m_low
                    )
                    rect.setBrush(pg.mkBrush(r, g, b, 70))
                    rect.setPen(pg.mkPen(r, g, b, 130, width=1))
                    rect.setZValue(-5)
                    self.ax_m.getViewBox().addItem(rect, ignoreBounds=True)
            t_event += event.duration

    def _draw_clearouts(self, clearout_times):
        for t_co in clearout_times:
            line = pg.InfiniteLine(
                pos=t_co * 1e6,
                angle=90,
                pen=pg.mkPen(*CLEAROUT_RGB, 130, width=4),
            )
            self.ax_z.addItem(line, ignoreBounds=True)

    def _add_legend(self):
        legend = self.ax_z.addLegend(offset=(10, 10))
        legend.addItem(
            pg.PlotDataItem(pen=pg.mkPen("w", width=2)), "|g⟩ ground (solid)"
        )
        legend.addItem(
            pg.PlotDataItem(pen=pg.mkPen("w", width=2, style=QtCore.Qt.DotLine)),
            "|e⟩ excited (dotted)",
        )
        legend.addItem(
            pg.PlotDataItem(pen=pg.mkPen(*PULSE_RGB[+1], 255, width=4)),
            "up beam (Δm > 0)",
        )
        legend.addItem(
            pg.PlotDataItem(pen=pg.mkPen(*PULSE_RGB[-1], 255, width=4)),
            "down beam (Δm < 0)",
        )

    # -- applet entry point --------------------------------------------------

    def data_changed(self, value, metadata, persist, mods, title):
        records = value.get(self.args.pulse_intent_record)

        self.ax_z.clear()
        self.ax_m.clear()
        self.ax_z.setTitle(title or "LMT spacetime diagram")

        if records is None or len(records) == 0:
            self.ax_z.setTitle(
                "LMT spacetime diagram — waiting for pulse_intent_record…"
            )
            return

        try:
            result = st.infer_trajectory_from_intent_record(records)
        except Exception as exc:  # noqa: BLE001 - surface, don't crash the applet
            logger.exception("Failed to reconstruct LMT trajectory")
            self.ax_z.setTitle(f"LMT spacetime diagram — error: {exc}")
            return

        if result is None:
            self.ax_z.setTitle("LMT spacetime diagram — no valid recorded sequence yet")
            return

        sequence, clouds, clearout_times = result

        self._draw_pulses(sequence)
        all_m = self._draw_clouds(sequence, clouds)
        self._draw_clearouts(clearout_times)

        # m=0 reference line.
        self.ax_m.addItem(
            pg.InfiniteLine(pos=0, angle=0, pen=pg.mkPen(150, 150, 150, 90, width=1)),
            ignoreBounds=True,
        )
        self._add_legend()

        m_max = int(np.abs(all_m).max()) if all_m else 0
        n_pulses = sum(isinstance(e, st.Pulse) for e in sequence)
        self.ax_m.setTitle(
            f"v_recoil = {st.RECOIL_VELOCITY * 1e3:.2f} mm/s  ·  "
            f"|m|max = {m_max}  ·  {n_pulses} pulses  ·  {len(clouds)} clouds"
        )


def main():
    applet = TitleApplet(LMTTrajectoryPlot)
    applet.add_dataset(
        "pulse_intent_record",
        "Broadcast pulse-intent-record dataset (from PulseDMARecording)",
    )
    applet.run()


if __name__ == "__main__":
    main()
