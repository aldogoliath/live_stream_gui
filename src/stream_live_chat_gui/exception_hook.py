#!/usr/bin/env python3
"""Qt5 Exception Handler for Python 3.5+

Additions copyright 2019, 2020 Stephan Sokolow

Demonstration::

    python3 qtexcepthook.py [--report-button]

Usage::

    import qtexcepthook
    app = QApplication(sys.argv)
    QtExceptHook().enable()

Adapted from gtkexcepthook.py::

    (c) 2003 Gustavo J A M Carneiro gjc at inescporto.pt
        2004-2005 Filip Van Raemdonck
        2009, 2011, 2019 Stephan Sokolow

    http://www.daa.com.au/pipermail/pygtk/2003-August/005775.html
    Message-ID: <1062087716.1196.5.camel@emperor.homelinux.net>
        "The license is whatever you want."

Changes made to the Van Raemdonck version before porting off GTK+ 2.x:

- Switched from auto-enable to ``gtkexcepthook.enable()`` to silence false
  positive complaints from PyFlakes. (Borrowed naming convention from
  :mod:`cgitb`)

Changes made since the port to PyQt 5.x:

- Heavily refactored for maintainability
- Replaced most of the code with a call to
  :meth:`traceback.TracebackException.format` after updating the minimum
  supported Python version to 3.5.
- Split out the email support into an easily-replaced callback
- Integrated :meth:`QCoreApplication.applicationName` into the example e-mails.
- Add a command-line parser to the demonstration code to make it easy to test
  both with and without a reporting callback set.
"""

__author__ = "Stephan Sokolow; Filip Van Raemdonck; Gustavo J A M Carneiro"
__license__ = "Public Domain"


import sys
import traceback
from gettext import gettext as _
from typing import Callable

# pylint: disable=no-name-in-module
from PyQt5.QtCore import QCommandLineOption, QCommandLineParser, QEvent
from PyQt5.QtGui import QTextOption
from PyQt5.QtWidgets import QApplication, QMessageBox, QSizePolicy, QTextEdit

# pylint: disable=unused-import,wrong-import-order
from typing import Dict  # noqa
from PyQt5.QtWidgets import QPushButton  # noqa

#: The :meth:`QCoreApplication.translate` context for strings in this file
TR_ID = "excepthook"


def _tr(*args):
    """Helper to make :meth:`QCoreApplication.translate` more concise."""
    return QApplication.translate(TR_ID, *args)


class ResizableMessageBox(QMessageBox):  # pylint: disable=R0903
    """QMessageBox which allows the detailed text expander to be resized
    and sets it to display non-wrapping monospace text.

    Adapted from `Resizing a QMessageBox?
    <https://www.qtcentre.org/threads/24888-Resizing-a-QMessageBox>`_ on
    Qt Center.

    .. todo:: For some reason, calling :meth:`QWidget.setMaximumSize` in this
        causes KWin to misalign the titlebar's right button box under Kubuntu
        16.04 LTS until the window is moved or resized.
    """

    def __init__(self, *args, **kwargs):
        super(ResizableMessageBox, self).__init__(*args, *kwargs)
        self.setStyleSheet("QTextEdit { font-family: monospace; }")

    def event(self, event):
        """Override :meth:`QWidget.event` to hook in our customizations *after*
        Qt tries to force settings on us.

        (Use :class:`LayoutRequest <QEvent>` because it only gets fired two to
        four times under typical operation and happens at the right time.)
        """
        res = QMessageBox.event(self, event)

        # Skip events we don't care about
        if event.type() != QEvent.LayoutRequest:
            return res

        # Only do all this stuff once the TextWidget is here
        details = self.findChild(QTextEdit)
        if details:
            self.setSizeGripEnabled(True)
            self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
            self.setMaximumSize(16777215, 16777215)

            details.setWordWrapMode(QTextOption.NoWrap)
            details.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
            details.setMaximumSize(16777215, 16777215)

        return res


class QtExceptHook(object):
    """GUI exception hook for PyQt 5.x applications

    :param reporting_cb: If provided, a :guilabel:`Report Bug...` button will
        be added which will call ``reporting_cb`` when clicked.
    """

    def __init__(self, reporting_cb: Callable[[str], None] = None):
        """Initialize as much as possible on application startup.

        (Maximize the chance that a bug in the exception handling system will
        show up as early as possible.)
        """
        self._extra_info = ""
        self._reporting_cb = reporting_cb

        self._dialog = ResizableMessageBox(
            QMessageBox.Warning,
            _tr("Bug Detected"),
            _tr(
                "<big><b>A programming error has been detected "
                "during the execution of this program.</b></big>"
            ),
        )

        secondary = _tr(
            "It probably isn't fatal, but should be "
            "reported to the developers nonetheless."
        )

        if self._reporting_cb:
            btn_report = self._dialog.addButton(
                _tr("Report Bug..."), QMessageBox.ActionRole
            )
            btn_report.clicked.disconnect()
            btn_report.clicked.connect(self._cb_report_bug)
        else:
            btn_copy = self._dialog.addButton(
                _tr("Copy Traceback..."), QMessageBox.ActionRole
            )
            btn_copy.clicked.disconnect()
            btn_copy.clicked.connect(self._cb_copy_to_clipboard)

            secondary += _tr(
                "\n\nPlease remember to include the "
                "traceback from the Details expander."
            )

        self._dialog.setInformativeText(secondary)

        # Workaround for the X button not working when details are available
        # Source: https://stackoverflow.com/a/32764190/435253
        btn_close = self._dialog.addButton(QMessageBox.Close)
        self._dialog.setEscapeButton(btn_close)

        self.b_quit = self._dialog.addButton(_("Quit"), QMessageBox.RejectRole)

    def _cb_copy_to_clipboard(self):
        """Qt slot for the :guilabel:`Copy Traceback...` button."""
        QApplication.instance().clipboard().setText(self._dialog.detailedText())

        QMessageBox(
            QMessageBox.Information,
            _tr("Traceback Copied"),
            _tr("The traceback has now been copied to the clipboard."),
        ).exec_()

    def _cb_report_bug(self):
        """Qt slot for the :guilabel:`Report Bug...` button. """
        self._reporting_cb(self._dialog.detailedText())

    def _excepthook(self, exc_type, exc_value, exc_traceback):
        """Replacement system exception handler callback"""
        # Construct the text of the bug report
        t_exception = traceback.TracebackException(
            exc_type, exc_value, exc_traceback, capture_locals=True
        )
        traceback_text = "\n".join(t_exception.format())
        if self._extra_info:
            traceback_text += "\n{}".format(self._extra_info)

        # Store it in the dialog where *everything* will retrieve it from
        self._dialog.setDetailedText(traceback_text)

        # Show the dialog
        self._dialog.exec_()
        if self._dialog.clickedButton() == self.b_quit:
            QApplication.instance().quit()

    def enable(self):
        """Replace the default exception handler with this one"""
        sys.excepthook = self._excepthook

    def set_extra_info(self, text: str):
        """Set some arbitrary text to be appended to the traceback"""
        self._extra_info = text or ""


if __name__ == "__main__":
    # Set up a mock application
    app = QApplication(sys.argv)
    app.setApplicationName("QtExceptHook Demo")

    # Set up a simple command-line parser so no editing is needed to try both
    # configurations
    reportOption = QCommandLineOption(
        "report-button",
        _tr("Initialize the exception hook with a bug-reporting callback"),
    )

    parser = QCommandLineParser()
    parser.addOption(reportOption)
    parser.addHelpOption()
    parser.process(app)

    # Attach the exception handler
    ehook = QtExceptHook()
    ehook.enable()
    ehook.set_extra_info("This is some extra info. Hello, world!")

    # Set up some mock data
    # pylint: disable=unused-variable,W0201,C0103,R0903
    class X(object):
        """Mock data for testing"""

        y = "Test"
        z = None

        def __repr__(self):
            """.. todo: Figure out how to avoid recursion with z"""
            return "X<y={!r}, z=...>".format(self.y)

    x = X()
    x.z = x  # type: ignore
    w = " e"

    def testfunc(testarg):
        """Function to demonstrate traceback"""
        a = "foo"  # NOQA
        raise Exception(testarg.z.y + w)

    # Raise an exception
    testfunc(x)
