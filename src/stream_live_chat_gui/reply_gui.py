from PyQt5.QtWidgets import (
    QMainWindow,
    QPushButton,
    QTableView,
    QVBoxLayout,
    QHBoxLayout,
    QWidget,
    QScrollArea,
    QLabel,
    QCheckBox,
    QTextEdit,
    QMessageBox,
    QPlainTextEdit,
    QLineEdit,
)
from PyQt5.QtGui import QFont, QTextCursor, QRegExpValidator
from PyQt5.QtCore import Qt, QObject, QRegExp, QTimer, QTime, pyqtSignal
from stream_live_chat_gui import (
    get_db_session,
    AlchemizedModelColumn,
    DATABASE_NAME,
)
from stream_live_chat_gui.alchemical_model import AlchemicalTableModel
from stream_live_chat_gui.database_model import Question
import sys
from typing import Optional


WINDOW_TITLE = "Live stream show"
QUESTIONS_COUNTER_PLACEHOLDER = "0"


class Stream(QObject):
    newText = pyqtSignal(str)

    def write(self, text):
        self.newText.emit(str(text))


class AnswersUi(QMainWindow):
    def __init__(self):
        super().__init__()

        # Window's properties
        self._set_window_properties()
        self.general_layout = QVBoxLayout()
        self._set_central_widget()
        self._create_top_layout()
        self._create_central_layout()
        self._create_bottom_layout()
        self.table_refresh_timer = QTimer()
        self._create_close_dialog_box()
        self._create_camera_reset_resources()
        self._create_live_chat_worker_error_message_box()
        self.show()
        sys.stdout = Stream(newText=self.on_update_text)

    def on_update_text(self, text):
        cursor = self.live_chat_feed_text_box.textCursor()
        cursor.movePosition(QTextCursor.End)
        cursor.insertText(text)
        self.live_chat_feed_text_box.setTextCursor(cursor)
        # TODO: Test this functionality
        self.live_chat_feed_text_box.ensureCursorVisible()

    def _create_close_dialog_box(self):
        self.close_dialog_box = QMessageBox(self)
        self.close_dialog_box.setText("Click the Stop Stream button first!")
        self.close_dialog_box.setWindowTitle("Stream is ACTIVE")
        self.close_dialog_box.setStandardButtons(QMessageBox.Ok)

    def _create_camera_reset_resources(self):
        self.camera_reset_dialog = QMessageBox(self)
        self.camera_reset_dialog.setText("Please reset the camera!")
        self.camera_reset_dialog.setWindowTitle("CAMERA RESET TIMER")
        self.camera_reset_timer = QTimer()

    def _create_live_chat_worker_error_message_box(self):
        self.error_message_box = QMessageBox(self)
        self.error_message_box.setText(
            "Click stop->start Stream button to restart the live chat\nand to be able to open questions again.\n"
            "REPLYING Questions is still possible"
        )
        self.error_message_box.setWindowTitle(
            "Underlying Live Chat API Thread, CRASHED"
        )
        self.error_message_box.setStandardButtons(QMessageBox.Ok)

    def _create_top_layout(self) -> None:
        """
        The top layout `Horizontal` one contains:
        - Start/Stop (general) Stream button (QPushButton)
        - Text Box (Scroll area widget) that shows current question being answered
        - Text Box (Scroll area widget) that shows ???
        - QVBoxLayout:
          - Label Box (Input for question limit for a session)
          - Label to display text regarding the session question limit
        """
        top_layout = QHBoxLayout()

        # Start/Stop Stream
        self.start_stream_button = QPushButton("Start Stream", self)
        self.start_stream_button.setCheckable(True)
        self.current_question_text = QLabel()
        self.current_question_text.setTextInteractionFlags(Qt.TextSelectableByMouse)
        current_question_display = QScrollArea()
        self._add_text_box_with_scroll_area(
            self.current_question_text,
            current_question_display,
            (300, 150, 400, 300),
        )

        questions_limit_per_session_block = QVBoxLayout()
        self.questions_limit_input = QLineEdit(self)
        self.questions_limit_input.setMaximumSize(200, 50)
        self.questions_limit_input.setAlignment(Qt.AlignHCenter)
        regexp = QRegExp("^([1-9][0-9]?)$")
        validator = QRegExpValidator(regexp)
        self.questions_limit_input.setValidator(validator)
        self.questions_limit_per_session_label = QLabel("Session questions limit")

        questions_limit_per_session_block.addWidget(self.questions_limit_input)
        questions_limit_per_session_block.addWidget(
            self.questions_limit_per_session_label
        )

        top_layout.addWidget(self.start_stream_button)
        top_layout.addWidget(current_question_display)
        top_layout.addLayout(questions_limit_per_session_block)

        # Add layout to the general one
        self.general_layout.addLayout(top_layout)

    def _add_text_box_with_scroll_area(
        self,
        text_box,
        scroll_area_display,
        geometry: tuple,
        text_to_set: str = None,
    ) -> None:
        """Text Box with scroll: current question
        args:
          - text_box (QLabel)
          - scroll_area_display (QScrollArea)
          - text_to_set (str)
        """

        text_box.setStyleSheet("background-color: white;")
        if text_to_set:
            text_box.setText(text_to_set)
        if isinstance(text_box, QLabel):
            text_box.setWordWrap(True)

        text_box.setFont(QFont("Times", 14))

        scroll_area_display.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOn)
        scroll_area_display.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll_area_display.setGeometry(*geometry)
        scroll_area_display.setWidgetResizable(True)
        scroll_area_display.setWidget(text_box)

    def _create_central_layout(self) -> None:
        """
        QHBoxLayout:
            - Table Left [SQLite connection/display]
            - QVBoxLayout:
                - Reply Auto Button
                - Reply Button
                - Reply Random
                - "Streamed:" [QLabel timer]
                - Delete Button
                - "Current:" [QLabel timer]
                - "Total:" [QLabel counter]
                - "Wait Avg:" [QLabel display]
                - "Ans Avg:" [QLabel display]
                - "Est. by ans:" [QLabel display]
            - Table Right [SQLite connection/display]
            - Scrolling Area Far Right [QScrollArea] -> Live Chat Feed
        """
        central_layout = QHBoxLayout()

        pending_questions_model = self.__alchemized_model_helper()
        pending_questions_model.setFilter(Question.is_replied == 0)
        self.pending_questions_view = QTableView()
        self.pending_questions_view.setModel(pending_questions_model)
        self.pending_questions_view.setSelectionBehavior(QTableView.SelectRows)

        replied_questions_model = self.__alchemized_model_helper()
        replied_questions_model.setFilter(Question.is_replied == 1)
        # '0' is the default id column number, but for the replied table we order by replied timestamp
        column_index_to_sort_by: int = self._get_column_index("replied_ts") or 0
        replied_questions_model.setSorting(column_index_to_sort_by, Qt.AscendingOrder)
        self.replied_questions_view = QTableView()
        self.replied_questions_view.setModel(replied_questions_model)
        self.replied_questions_view.setSelectionBehavior(QTableView.SelectRows)

        # live chat feed https://stackoverflow.com/a/44433766/2706103
        # https://doc.qt.io/qt-5/qplaintextedit.html (inherits QScrollArea)
        self.live_chat_feed_text_box = QPlainTextEdit()
        self.live_chat_feed_text_box.moveCursor(QTextCursor.Start)
        # TODO: Test this functionality
        self.live_chat_feed_text_box.ensureCursorVisible()
        # self.live_chat_feed_text_box.setLineWrapColumnOrWidth(500)
        self.live_chat_feed_text_box.setLineWrapMode(QPlainTextEdit.WidgetWidth)

        central_layout_column = QVBoxLayout()
        self.reply_auto_button = QPushButton("Reply Auto")
        self.reply_button = QPushButton("Reply")
        self.reply_random_button = QPushButton("Reply Random")
        self.stream_timer_header_label = QLabel("Streamed:")
        self.stream_timer = QTimer()
        self.stream_time = QTime(00, 00, 00)
        self.stream_timer_label = QLabel(f"{self.stream_time.toString()}")
        # TODO: pending implementation of slot (at controller.py)
        self.delete_pending_question_button = QPushButton("Delete")
        self.current_question_timer_header_label = QLabel("Current:")
        self.current_question_timer = QTimer()
        self.current_question_time = QTime(00, 00, 00)
        self.current_question_timer_label = QLabel(
            f"{self.current_question_time.toString()}"
        )
        # The 0 is an initializer static placeholder
        self.total_questions_label = QLabel(f"Total: {QUESTIONS_COUNTER_PLACEHOLDER}")
        self.wait_average_label = QLabel(
            f"Wait Avg:\n{self.current_question_time.toString()}"
        )
        self.answer_average_label = QLabel(
            f"Ans Avg:\n{self.current_question_time.toString()}"
        )
        self.estimated_by_answer_label = QLabel(
            f"Est. by ans:\n{self.current_question_time.toString()}"
        )
        central_layout_column.addWidget(self.reply_auto_button)
        central_layout_column.addWidget(self.reply_button)
        central_layout_column.addWidget(self.reply_random_button)
        central_layout_column.addWidget(self.stream_timer_header_label)
        central_layout_column.addWidget(self.stream_timer_label)
        central_layout_column.addWidget(self.delete_pending_question_button)
        central_layout_column.addWidget(self.current_question_timer_header_label)
        central_layout_column.addWidget(self.current_question_timer_label)
        central_layout_column.addWidget(self.total_questions_label)
        central_layout_column.addWidget(self.wait_average_label)
        central_layout_column.addWidget(self.answer_average_label)
        central_layout_column.addWidget(self.estimated_by_answer_label)

        central_layout.addWidget(self.pending_questions_view)
        central_layout.addLayout(central_layout_column)
        central_layout.addWidget(self.replied_questions_view)
        central_layout.addWidget(self.live_chat_feed_text_box)

        # Add layout to the general one
        self.general_layout.addLayout(central_layout)

    def __alchemized_model_helper(self):
        """Return a list of tuples on which each tuple is composed of:
        (column: sqlalchemy.sql.schema.Column,
         sql_alchemy_column_name: str,
         header_display_name: str,
         flags: dict)
        """
        # TODO: have this as a constant at the top of this module
        # Basically changing a column name to be something else
        column_extra_header_display_flags = {
            "created_ts": {"display_name": "Asked@", "flags": {"editable": True}}
        }

        columns = [
            AlchemizedModelColumn(column=column, column_name=column.name, flags=dict())
            for column in Question.__table__.columns
        ]

        for column in columns:
            for column_name, extra_values in column_extra_header_display_flags.items():
                if column_name == column.column_name:
                    column.header_display_name = extra_values.get("display_name", "")
                    column.flags = extra_values.get("flags", dict())

        return AlchemicalTableModel(
            session=get_db_session(db_filename=DATABASE_NAME),
            model=Question,
            relationship=Question.user,
            columns=columns,
        )

    def _get_column_index(self, column_name: str) -> Optional[int]:
        """Helper that given a name, that has to match one of the described in the database_model, returns the index
        number of such name"""
        for index, column in enumerate(Question.__table__.columns):
            if column_name == column.name:
                return index

    def _create_bottom_layout(self) -> None:
        """
        The bottom layout `Horizontal` one contains:
        - QuestionInput (QLineEdit)
        - Display total of pending questions (QLabel)
        - Add (QPushButton) to add a row to the table (new question to the table)
        - Checkbox to close questions (or open them) (QCheckBox)
        - Display total of replied questions (QLabel)
        - Reschedule last (QPushButton) to mark the last question as not responded and added it back as current (?)
        - Remove (QPushButton) to delete an element (row) from the replied_questions table (the selected one)
        """
        # reschedule last implies marking as pending the current one and resetting the "answered timestamp" for it too
        # A comment in a youtube live chat should be no more than 200 chars
        bottom_layout = QHBoxLayout()

        # Add the text box to add questions and the button that confirms the action
        self.question_manual_input = QTextEdit(self)
        # TODO: have this calculated dynamically?
        self.question_manual_input.setMaximumSize(450, 100)

        # Grouping Pending questions counter + Add (question) button
        _add_button_pending_q_group = QVBoxLayout()

        self.no_of_pending_questions = QLabel(
            f"{QUESTIONS_COUNTER_PLACEHOLDER} Pending"
        )

        self.add_manual_question_button = QPushButton("Add")

        _add_button_pending_q_group.addWidget(self.no_of_pending_questions)
        _add_button_pending_q_group.addWidget(self.add_manual_question_button)

        self.youtube_open_questions = QCheckBox("Open Questions", self)

        self.no_of_replied_questions = QLabel(
            f"{QUESTIONS_COUNTER_PLACEHOLDER} Replied"
        )

        self.reschedule_last_button = QPushButton("Reschedule last")
        self.remove_replied_question_button = QPushButton("Remove")

        # Add Widgets to bottom layout
        bottom_layout.addWidget(self.question_manual_input)
        bottom_layout.addLayout(_add_button_pending_q_group)
        bottom_layout.addWidget(self.youtube_open_questions)
        bottom_layout.addWidget(self.no_of_replied_questions)
        bottom_layout.addWidget(self.reschedule_last_button)
        bottom_layout.addWidget(self.remove_replied_question_button)

        # Add layout to the general one
        self.general_layout.addLayout(bottom_layout)

    # Method not used by now, leaving it as a reference
    # def _create_buttons(self):
    #     FIXED_HEIGHT_START_BUTTON = 40
    #     FIXED_WIDTH_START_BUTTON = 120
    #     self.twitch_chat_button = QPushButton("Twitch Live Chat", self)
    #     self.twitch_chat_button.setFixedSize(
    #         FIXED_WIDTH_START_BUTTON, FIXED_HEIGHT_START_BUTTON
    #     )
    #     self.twitch_chat_button.setCheckable(True)

    #     self.youtube_chat_button = QPushButton("Youtube Live Chat", self)
    #     self.youtube_chat_button.setFixedSize(
    #         FIXED_WIDTH_START_BUTTON, FIXED_HEIGHT_START_BUTTON
    #     )
    #     self.youtube_chat_button.setCheckable(True)
    #     self.general_layout.addWidget(self.twitch_chat_button)
    #     self.general_layout.addWidget(self.youtube_chat_button)

    def _set_window_properties(self) -> None:
        self.setWindowTitle(f"{WINDOW_TITLE}")

    def _set_central_widget(self) -> None:
        # Setting an instance attribute here, not the best of practices...
        self._central_widget = QWidget(self)
        self.setCentralWidget(self._central_widget)
        self._central_widget.setLayout(self.general_layout)

    def __del__(self):
        sys.stdout = sys.__stdout__

    def closeEvent(self, event):
        if self.start_stream_button.isChecked():
            self.close_dialog_box.exec()
            # self.camera_reset_dialog.show()
            event.ignore()
        else:
            event.accept()
            self.__del__()
