# Copyright © 2026 Nguyễn Thị Thuý Nga, Phú Cường Phát (Team PCP). Licensed GPL-2.0-or-later.
# -*- coding: utf-8 -*-
"""PCP-EIA Pollution Modeling: QGIS plugin entry point."""


def classFactory(iface):  # noqa: N802 (QGIS naming)
    from .plugin import EiaModelBridgePlugin

    return EiaModelBridgePlugin(iface)
