# -*- coding: utf-8 -*-
import os

from qgis.core import QgsProcessingOutputString

from ..core import cards
from ..provider import SETTING_AERMOD, SETTING_QUAL2KW, get_model_path
from .base import EiaAlgorithm


class CheckModelSetup(EiaAlgorithm):
    """Check that model programs are set in Processing settings and list the model cards."""

    LEVEL = "A"

    def name(self):
        return "check_model_setup"

    def displayName(self):
        return "Check model setup"

    def initAlgorithm(self, config=None):
        self.addOutput(QgsProcessingOutputString("REPORT", "Report"))

    def processAlgorithm(self, parameters, context, feedback):
        lines = []
        for label, key in (("AERMOD", SETTING_AERMOD), ("QUAL2Kw", SETTING_QUAL2KW)):
            p = get_model_path(key)
            state = "OK" if p and os.path.isfile(p) else ("path not found" if p else "not set")
            lines.append("%s: %s (%s)" % (label, state, p or "-"))
        for cid in cards.list_cards():
            card = cards.load_card(cid)
            lines.append("card %s v%s, unverified fields: %d" % (cid, card.get("_card_version"), len(cards.unverified_fields(card))))
        report = "\n".join(lines)
        for line in lines:
            feedback.pushInfo(line)
        return {"REPORT": report}
