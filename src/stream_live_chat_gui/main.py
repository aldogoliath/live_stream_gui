from stream_live_chat_gui import create_db, get_log_file_name
import logging

# TODO: add logging for std.err
logging.basicConfig(
    filename=get_log_file_name(),
    filemode="a",
    format="%(asctime)s,%(msecs)d %(name)s %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
    encoding="utf-8",
    level=logging.DEBUG,
)

import sys
from PyQt5.QtWidgets import QApplication
from stream_live_chat_gui.reply_gui import AnswersUi
from stream_live_chat_gui.controller import AppController
from stream_live_chat_gui.exception_hook import QtExceptHook

log = logging.getLogger(__name__)


def main():
    log.debug(f"Log file name: {get_log_file_name()}")
    create_db()

    # Application instance
    gui = QApplication(sys.argv)  # To create executable

    # https://gist.github.com/ssokolow/f5219e4c8e4bddbba4d08101969445d1
    # To send sys.err for not handled exceptions to a pyqt message window
    ehook = QtExceptHook()
    ehook.enable()

    # The GUI instance
    win = AnswersUi()

    # Create the model (TODO: development)
    # The model contains the business logic
    model = None
    # Create the controller and run it
    controller = AppController(model=model, view=win)
    controller.run()

    sys.exit(gui.exec())


if __name__ == "__main__":
    main()
