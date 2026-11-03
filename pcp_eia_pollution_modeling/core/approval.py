# -*- coding: utf-8 -*-
"""Supervision gate. Level A free, B expert confirms, C locked (reason required).

The confirmation is a modal dialog inside the QGIS window, so an AI calling the
algorithm through any channel (Python console, MCP bridge, qgis_process) cannot
approve by itself. Headless runs are refused for levels B and C.
"""
import getpass
from datetime import datetime, timezone


class ApprovalRefused(Exception):
    pass


def _qt_ask(level, title, summary, need_reason):
    from qgis.PyQt.QtCore import QThread
    from qgis.PyQt.QtWidgets import QApplication, QInputDialog, QMessageBox

    app = QApplication.instance()
    if app is None or not hasattr(app, "activeWindow"):
        raise ApprovalRefused("no QGIS window: levels B and C cannot run headless")
    if QThread.currentThread() != app.thread():
        raise ApprovalRefused("approval must be asked on the main thread")
    if need_reason:
        text, ok = QInputDialog.getMultiLineText(
            None, "Level C override: %s" % title, summary + "\n\nReason (recorded in the audit log):"
        )
        return (text.strip(), True) if ok and text.strip() else (None, False)
    box = QMessageBox(QMessageBox.Question, "Expert approval: %s" % title, summary)
    box.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
    box.setDefaultButton(QMessageBox.No)
    return ("", box.exec() == QMessageBox.Yes)


def require(level, title, summary, ask=_qt_ask):
    """Return an approval record (dict) or raise ApprovalRefused.

    `ask(level, title, summary, need_reason) -> (reason_text, approved)` is injectable for tests.
    """
    if level == "A":
        return {"approved": True, "by": "auto", "level": "A"}
    if level not in ("B", "C"):
        raise ValueError("unknown level %r" % level)
    reason, ok = ask(level, title, summary, level == "C")
    if not ok:
        raise ApprovalRefused("expert did not approve (level %s): %s" % (level, title))
    return {
        "approved": True,
        "by": getpass.getuser(),
        "level": level,
        "reason": reason or None,
        "time_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
