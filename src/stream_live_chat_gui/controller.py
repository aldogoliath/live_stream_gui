# from stream_live_chat_gui.twitch_chat import TwitchStreamThreadControl
from stream_live_chat_gui.youtube_chat import (
    YoutubeStreamThreadControl,
    UnableToGetVideoId,
    UnableToGetLiveChatId,
)
from stream_live_chat_gui.db_interactions import DBInteractions
from stream_live_chat_gui import QuestionTuple, YOUTUBER_NAME, DATABASE_NAME
from stream_live_chat_gui.record_files import FileRecording
from PyQt5.QtCore import QItemSelectionModel, QModelIndex, QTime, Qt
from PyQt5.QtWidgets import QTableView
from queue import Queue
from datetime import datetime
from enum import Enum
import logging

logging.basicConfig(level=logging.DEBUG)
log = logging.getLogger(__name__)
DEFAULT_CURRENT_QUESTION_TIMER = QTime(00, 00, 00)


class AutoReplyStatus(Enum):
    DO_NEXT_1 = 1
    DO_NEXT_2 = 2
    DO_RANDOM = 3
    MAX_STATUS = 4


class TableType(Enum):
    PENDING_QUESTIONS = 0
    REPLIED_QUESTIONS = 1


class AppController:
    def __init__(self, model, view, db_filename: str = DATABASE_NAME):
        self.model = model
        self.view = view
        self.db_filename = db_filename
        self.db = DBInteractions(db_filename=self.db_filename)
        self.answer_average = None
        self.auto_reply_value: int = 0
        self.current_timer_per_question_id = dict()
        # This avoids a message box being shown multiple times once we know the live chat api thread has failed once
        self.error_message_box_already_shown: bool = False
        # Show camera reset dialog every 25 min
        self.view.camera_reset_timer.start(1500000)

        # To account for youtube failures and the need to split the files on which the questions are saved
        self.start_stream_button_click_counter: int = 0

        # Open/Close question control (inter-thread communication)
        self.open_close_question_control_queue = Queue(maxsize=1)

        # Setting these ones for the banner display file
        self.answer_average_for_display: str = None
        self.wait_average_for_display: str = None
        self.estimated_by_answer_time_for_display: str = None
        self.number_of_pending_questions: int = None
        self.youtube_questions_open: bool = False

        # To prevent being able to use the youtube_open_questions checkbox before clicking Stream Start button
        self.view.youtube_open_questions.setEnabled(False)
        self.view.add_manual_question_button.setEnabled(False)
        self.record_file: FileRecording = None
        self.reset_pending_questions_pointers()
        self.reset_replied_questions_pointers()

    def reset_pending_questions_pointers(self):
        self.pending_question_row_index: int = -1
        self.pending_question_id: int = -1

    def reset_replied_questions_pointers(self):
        self.replied_question_row_index: int = -1
        self.replied_question_id: int = -1

    def run(self):
        """"Run the controller"""
        log.debug("Connecting signals")
        # Update question related counters (total/pending/replied)
        self.update_question_counters_and_banner()
        self.connect_signals()

    def update_question_counters_and_banner(self):
        number_of_pending_questions: int = self.db.count_all_pending_questions()
        number_of_replied_questions: int = self.db.count_all_replied_questions()
        # TODO: clean this variable, either make `number_of_replied_questions` a variable instance as well or make all
        # `number_of_pending_questions` references in this method to be `self.number_of_pending_questions`
        self.number_of_pending_questions = number_of_pending_questions
        self.view.total_questions_label.setText(
            f"Total: {number_of_pending_questions + number_of_replied_questions}"
        )
        self.view.no_of_pending_questions.setText(
            f"{number_of_pending_questions} Pending"
        )
        self.view.no_of_replied_questions.setText(
            f"{number_of_replied_questions} Replied"
        )
        if self.record_file:
            self.record_file.update_banner(
                pending_questions=self.number_of_pending_questions,
                replied_questions=number_of_replied_questions,
                answer_average=self.answer_average_for_display,
                estimated_total_wait=self.estimated_by_answer_time_for_display,
                open_questions=self.youtube_questions_open,
            )

    def connect_signals(self):
        """Connect signals and slots"""
        log.debug("Connecting slots...")
        # unused for now
        # self.view.twitch_chat_button.clicked.connect(
        #     self.twitch_chat_button_click_action
        # )
        self.view.youtube_open_questions.stateChanged.connect(
            self.youtube_chat_checkbox_click_action
        )

        self.view.stream_timer.timeout.connect(self.display_stream_timer)
        self.view.current_question_timer.timeout.connect(
            self.display_current_question_timer
        )
        self.view.table_refresh_timer.timeout.connect(
            self.refresh_while_stream_is_active
        )
        self.view.start_stream_button.clicked.connect(self.stream_timer_control)

        self.view.camera_reset_timer.timeout.connect(self.view.camera_reset_dialog.show)

        # Gives reference to the row selected when an item is clicked in the tableview
        self.view.pending_questions_view.clicked.connect(
            self.pending_table_view_clicked
        )
        self.view.replied_questions_view.clicked.connect(
            self.replied_table_view_clicked
        )

        self.view.add_manual_question_button.clicked.connect(self.add_manual_question)

        # Reply buttons slot section
        self.view.reply_auto_button.clicked.connect(self.reply_auto)
        self.view.reply_button.clicked.connect(self.reply_question)
        self.view.reply_random_button.clicked.connect(
            lambda: self.reply_question(random=True)
        )

        # Reschedule Last
        self.view.reschedule_last_button.clicked.connect(self.reschedule_last)

        # Delete buttons
        self.view.delete_pending_question_button.clicked.connect(
            lambda: self.delete_question(table=TableType.PENDING_QUESTIONS)
        )
        self.view.remove_replied_question_button.clicked.connect(
            lambda: self.delete_question(table=TableType.REPLIED_QUESTIONS)
        )

    def add_manual_question(self):
        question = self.view.question_manual_input.toPlainText()
        if not question:
            return
        self.db.add_new_question(user_name=YOUTUBER_NAME, question_msg=question)
        self.view.pending_questions_view.model().refresh()
        self.update_question_counters_and_banner()
        self.view.question_manual_input.clear()

    def reschedule_last(self):
        """
        The latest question replied is actually the current question in display, so we need to
        reset that first. And then get the one before to the latest to display it again as the current
        one. Using `current_timer_per_question_id` to restart the current_question_time
        """
        if self.db.count_all_replied_questions() < 2:
            return

        latest_replied_questions: list[QuestionTuple] = self.db.get_last_n_replied(
            number_of_questions_to_return=2
        )
        current_question_to_reset = latest_replied_questions[0]
        question_to_reschedule = latest_replied_questions[-1]

        self.db.mark_unmark_question_as_replied(
            current_question_to_reset.id, replied=False
        )
        self.view.replied_questions_view.clearSelection()
        self.view.pending_questions_view.clearSelection()
        self.view.replied_questions_view.model().refresh()
        self.view.pending_questions_view.model().refresh()
        self.view.current_question_text.setText(question_to_reschedule.question)
        # Only needed if something goes wrong
        # log.debug(
        #     f"Dict: current_timer_per_question_id: {self.current_timer_per_question_id}"
        # )
        restart_time: QTime = self.current_timer_per_question_id.get(
            question_to_reschedule.id, DEFAULT_CURRENT_QUESTION_TIMER
        )
        self.start_current_question_timer(start_timer_at=restart_time)
        self.update_question_counters_and_banner()

    def delete_question(self, table: TableType) -> None:
        if table == TableType.PENDING_QUESTIONS and self.pending_question_id != -1:
            log.debug(
                f"Deleting pending question id: {self.pending_question_id}, with row index: "
                f"{self.pending_question_row_index} of pending questions table"
            )
            self.db.delete_question_with_id(self.pending_question_id)
            self.reset_pending_questions_pointers()
            self.view.pending_questions_view.clearSelection()
            self.view.pending_questions_view.model().refresh()

        elif table == TableType.REPLIED_QUESTIONS and self.replied_question_id != -1:
            log.debug(
                f"Deleting replied question id: {self.replied_question_id}, with row index: "
                f"{self.replied_question_row_index} of pending questions table"
            )
            self.db.delete_question_with_id(self.replied_question_id)
            self.reset_replied_questions_pointers()
            self.view.replied_questions_view.clearSelection()
            self.view.replied_questions_view.model().refresh()
        self.update_question_counters_and_banner()
        return

    def reply_auto(self):
        """
        In the event of a super chat, give priority to it but keep on using reply auto normal
        functionality after 1 super chat event.
        """
        if not self.db.count_all_pending_questions():
            self.view.current_question_text.setText("")
            return

        # super chat takes priority
        number_of_pending_super_chats = self.db.count_all_pending_questions(
            is_super_chat=True
        )
        if number_of_pending_super_chats:
            log.debug(
                f"Number of pending super chat events: {number_of_pending_super_chats}"
            )
            self.reply_question(is_super_chat=True)

        self.auto_reply_value += 1
        log.debug(f"Reply auto, auto_reply_value: {self.auto_reply_value}")

        if self.auto_reply_value >= AutoReplyStatus.MAX_STATUS.value:
            log.debug("Reset auto_reply_value")
            self.auto_reply_value = AutoReplyStatus.DO_NEXT_1.value

        if (
            self.auto_reply_value == AutoReplyStatus.DO_NEXT_1.value
            or self.auto_reply_value == AutoReplyStatus.DO_NEXT_2.value
        ):
            log.debug(f"Reply auto, regular question: {self.auto_reply_value}")
            self.reply_question()
        else:
            log.debug(f"Reply auto, random question: {self.auto_reply_value}")
            self.reply_question(random=True)

    def reply_question(self, random=False, is_super_chat=False):
        if (
            not self.db.count_all_pending_questions()
            and not self.db.count_all_pending_questions(is_super_chat=True)
            or not self.view.start_stream_button.isChecked()
        ):
            self.view.current_question_text.setText("")
            # TODO: add a way to stop the current question timer display for the last question, maybe have the stop
            # stream button action deal with this
            return

        if is_super_chat:
            question: QuestionTuple = self.db.get_next_pending_question(
                is_super_chat=True
            )
        elif not random:
            if self.pending_question_row_index == -1:
                # reply top of the question
                question: QuestionTuple = self.db.get_next_pending_question()
            else:
                # reply selected question from the table
                question: QuestionTuple = self.db.get_pending_question_with_given_id(
                    self.pending_question_id
                )
        else:
            question: QuestionTuple = self.db.get_next_pending_question_randomly()

        # Add question and timestamp to record file
        # TODO: add workaround for reschedule last question scenario
        # TODO: when integration with super chat, avoid registering such messages in the output file
        if not is_super_chat:
            self.record_file.add_entry_to_record_file(
                replied_timestamp=datetime.utcnow(), question=question.question
            )
        # reset pointers
        self.reset_pending_questions_pointers()
        self.view.current_question_text.setText(question.question)
        self.db.mark_unmark_question_as_replied(question.id)

        self.display_answer_average_time()
        self.display_wait_average_time()
        self.display_estimated_by_answer_time()
        # `>2` due to the fact that the current shown question will be present in the replied_question_table
        # and we need to start counting after the 1st question has been replied (meaning, when the second
        # question becomes the current question) and all the subsequent ones.
        if self.db.count_all_replied_questions() >= 2:
            log.debug(
                f"For question.id {question.id}, assign current_time: {self.view.current_question_time}"
            )
            self.current_timer_per_question_id[
                question.id
            ] = self.view.current_question_time
        self.start_current_question_timer()
        self.view.replied_questions_view.clearSelection()
        self.view.pending_questions_view.clearSelection()
        self.view.replied_questions_view.model().refresh()
        self.view.pending_questions_view.model().refresh()
        self.update_question_counters_and_banner()

    # https://stackoverflow.com/questions/41327545/how-to-create-a-timer-in-pyqt
    def stream_timer_control(self):
        if self.view.start_stream_button.isChecked():
            log.debug("Starting stream")
            self.view.stream_timer.start(1000)
            self.view.start_stream_button.setText("Stop Stream")
            start_time = datetime.utcnow()
            self.record_file = FileRecording(
                start_time, self.start_stream_button_click_counter
            )

            self.start_stream_button_click_counter += 1
            log.debug(
                f"Start stream button counter: {self.start_stream_button_click_counter}"
            )
            self.view.youtube_open_questions.setEnabled(True)
            self.view.add_manual_question_button.setEnabled(True)
            self._start_youtube_live_chat_execution(self.record_file.live_chat_file)
            self.error_message_box_already_shown = False
        else:
            # Check if the thread is alive first, before joining
            if self.youtube_chat_streamer_thread.is_alive():
                self.youtube_chat_streamer_thread.join()
            else:
                log.warning("Unable to join thread, it stopped running, check logs!")
            log.debug("Stopping stream")
            self.view.stream_timer.stop()
            self.view.table_refresh_timer.stop()
            self.view.start_stream_button.setText("Start Stream")
            if self.youtube_questions_open:
                self.view.youtube_open_questions.setChecked(False)
                self.youtube_questions_open = False
            self.view.youtube_open_questions.setEnabled(False)
            self.view.add_manual_question_button.setEnabled(False)

    def _start_youtube_live_chat_execution(self, live_chat_record_file: str) -> None:
        # TODO: Add a popup display message displaying the error of the try/except block.
        # After that, uncheck the checkbox, reference -> `self.checkbox_confirmed.setCheckState(Qt.Unchecked)`
        # TODO: check if the queue needs to be added a value before or after creating the thread instance
        try:
            self.youtube_chat_streamer_thread = YoutubeStreamThreadControl(
                self.open_close_question_control_queue,
                live_chat_record_file,
                self.db_filename,
            )

        except (UnableToGetVideoId, UnableToGetLiveChatId) as error:
            log.debug(f"ERROR: \n{error}")
            # setCheckState -> Qt.Unchecked triggers (stateChanged), it's disabled here so it doesn't trigger the
            # button (youtube_open_questions) event
            self.view.youtube_open_questions.blockSignals(True)
            self.view.youtube_open_questions.setCheckState(Qt.Unchecked)
            self.view.youtube_open_questions.blockSignals(False)
            self.view.youtube_open_questions.setEnabled(False)

            self.view.start_stream_button.setChecked(False)
            self.view.start_stream_button.setText("Start Stream")

            self.start_stream_button_click_counter -= 1
            log.debug(
                f"Decreasing start_stream_button_click_counter to: {self.start_stream_button_click_counter}"
            )
            # RESET TIMER ?
            self.view.stream_timer.stop()
            return

        self.youtube_chat_streamer_thread.daemon = True
        self.youtube_chat_streamer_thread.start()

        # Refresh table view/counters every 2.5 seconds
        self.view.table_refresh_timer.start(2500)

    def display_stream_timer(self):
        self.view.stream_time = self.view.stream_time.addSecs(1)
        self.view.stream_timer_label.setText(self.view.stream_time.toString())

    def refresh_while_stream_is_active(self):
        self.view.pending_questions_view.model().refresh()
        self.update_question_counters_and_banner()
        # Check that the underlying worker in charge of calling the youtube live chat api is alive
        # if not, display a message.
        if (
            not self.error_message_box_already_shown
            and not self.youtube_chat_streamer_thread.is_alive()
        ):
            self.view.error_message_box.show()
            self.error_message_box_already_shown = True
            # Two possible scenarios related to the `open_questions` status:
            # 1. Thread fails when questions are open -> questions get closed immediately
            # 2. Thread fails when questions are closed
            # in either case (1 or 2) the open_questions checkbox gets disabled
            if self.youtube_questions_open:
                log.critical(
                    "Closing questions due to youtube live chat api worker thread crash"
                )
                self.view.youtube_open_questions.setCheckState(Qt.Unchecked)
                self.youtube_questions_open = False

            self.view.youtube_open_questions.setEnabled(False)

        return

    def display_answer_average_time(self):
        # TODO: Do calculation of wait average here:
        """
        0.- order by replied_ts
        1.- If no elements in replied question table (1st question), show 00:00:00
        2.- For the nth element: (nth element's replied_ts) - (n-1 element's replied_ts)
        3.- For the last element (check if the pending_questions table is empty) there is no way to calculate current,
            doing what is done in the step above, but we could use the current timer as reference for this at this
            moment the last current time is just not calculated.
        """
        answer_average = self.db.calculate_answer_average_time()
        if not answer_average:
            return

        # timedelta saved here because it will be used again for display_estimated_by_answer_time
        self.answer_average = answer_average
        # trimming out miliseconds with the str split method
        self.answer_average_for_display = str(answer_average).split(".")[0]
        self.view.answer_average_label.setText(
            f"Ans Avg:\n{self.answer_average_for_display}"
        )

    def display_wait_average_time(self):
        wait_average = self.db.calculate_wait_average_time()
        if not wait_average:
            return
        self.wait_average_for_display = str(wait_average).split(".")[0]
        self.view.wait_average_label.setText(
            f"Wait Avg:\n{self.wait_average_for_display}"
        )

    def display_estimated_by_answer_time(self):
        number_of_pending_questions = self.db.count_all_pending_questions()
        if not number_of_pending_questions or self.answer_average is None:
            return
        self.estimated_by_answer_time_for_display = str(
            number_of_pending_questions * self.answer_average
        ).split(".")[0]
        self.view.estimated_by_answer_label.setText(
            f"Est. by ans:\n{self.estimated_by_answer_time_for_display}"
        )

    def start_current_question_timer(
        self, start_timer_at: QTime = DEFAULT_CURRENT_QUESTION_TIMER, restart=True
    ):
        # restart the current question timer
        self.view.current_question_time = start_timer_at
        if restart:
            self.view.current_question_timer.start(1000)

    def display_current_question_timer(self):
        self.view.current_question_time = self.view.current_question_time.addSecs(1)
        self.view.current_question_timer_label.setText(
            self.view.current_question_time.toString()
        )

    def pending_table_view_clicked(self, clickedIndex: QModelIndex):
        # TODO: Deduplicate this method and replied_table_view_clicked, maybe reimplementing the
        #       signal clicked for the table view
        if self.pending_question_row_index == clickedIndex.row():
            selection_model = self.view.pending_questions_view.selectionModel()
            selection_model.select(clickedIndex, QItemSelectionModel.Clear)
            # Reset the pointers
            self.reset_pending_questions_pointers()
            return

        self._set_row_index_and_id(
            clickedIndex=clickedIndex, tableView=self.view.pending_questions_view
        )

    def replied_table_view_clicked(self, clickedIndex: QModelIndex):
        if self.replied_question_row_index == clickedIndex.row():
            selection_model = self.view.replied_questions_view.selectionModel()
            selection_model.select(clickedIndex, QItemSelectionModel.Clear)
            # Reset the pointers
            self.reset_replied_questions_pointers()
            return

        self._set_row_index_and_id(
            clickedIndex=clickedIndex, tableView=self.view.replied_questions_view
        )

    def _set_row_index_and_id(self, clickedIndex: QModelIndex, tableView: QTableView):
        model = clickedIndex.model()
        row = clickedIndex.row()
        for index, question_table_column in enumerate(model.fields):
            if question_table_column.column_name == "id":
                selected_row_question_id = clickedIndex.siblingAtColumn(index).data()
                log.debug(f"selected_row_question_id: {selected_row_question_id}")
                if tableView is self.view.pending_questions_view:
                    self.pending_question_row_index = row
                    self.pending_question_id = selected_row_question_id
                # Assuming that there are only 2 tables and the 2nd one is `self.view.replied_questions_view`
                else:
                    self.replied_question_row_index = row
                    self.replied_question_id = selected_row_question_id

    def youtube_chat_checkbox_click_action(self, state):
        log.debug(
            f"Checking for {AppController.youtube_chat_checkbox_click_action.__name__}"
        )
        if state == Qt.Checked:
            log.debug("Youtube stream, opening questions")
            self.open_close_question_control_queue.put(True)
            self.view.youtube_open_questions.setText("Close questions")
            self.youtube_questions_open = True

        else:
            log.debug("Youtube stream, closing questions")
            self.view.youtube_open_questions.setText("Open questions")
            if self.youtube_chat_streamer_thread.is_alive():
                self.open_close_question_control_queue.put(False)
            self.youtube_questions_open = False

    # Unused for now, leaving it as reference
    # def twitch_chat_button_click_action(self):
    #     log.debug(
    #         f"Checking for {AppController.twitch_chat_button_click_action.__name__}"
    #     )
    #     if self.view.twitch_chat_button.isChecked():
    #         # The creation of a new thread is placed here and not in __init__ since this means that we'll be
    #         # opening a new thread each time the Start button is Pressed
    #         self.chat_streamer_thread = TwitchStreamThreadControl()
    #         self.chat_streamer_thread.start()
    #         log.debug("Twitch Start Button has been clicked")
    #         self.view.twitch_chat_button.setText("Stop")
    #     else:
    #         self.view.twitch_chat_button.setText("Twitch Live Chat")
    #         self.chat_streamer_thread.join()
    #         log.debug("Twitch Stop Button has been clicked")
