# -*- coding: utf-8 -*-
from qgis.core import QgsApplication


class EiaModelBridgePlugin:
    def __init__(self, iface):
        self.iface = iface
        self.provider = None

    def initProcessing(self):  # noqa: N802
        from .provider import EiaProvider

        self.provider = EiaProvider()
        QgsApplication.processingRegistry().addProvider(self.provider)

    def initGui(self):  # noqa: N802
        self.initProcessing()

    def unload(self):
        prov, self.provider = self.provider, None
        if prov is not None:
            try:  # the registry may already have deleted it (e.g. a second unload during a reload)
                QgsApplication.processingRegistry().removeProvider(prov)
            except RuntimeError:
                pass
