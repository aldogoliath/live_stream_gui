import sys

from PyQt5.QtWidgets import QApplication
from stream_live_chat_gui.reply_gui import AnswersUi
from stream_live_chat_gui.controller import AppController
from stream_live_chat_gui import create_db

import logging

log = logging.getLogger(__name__)


def main():
    create_db()

    # Application instance
    gui = QApplication(sys.argv)  # To create executable
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
