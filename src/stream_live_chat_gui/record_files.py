import logging
from datetime import datetime, timedelta
from stream_live_chat_gui import (
    get_resource,
    get_time_adjusted_filename,
    YOUTUBE_COMMENT_MAX_LENGTH,
    QUESTION_LOOKUP_WEBPAGE,
    BANNER_FILENAME,
    LIVE_CHAT_RECORD_FILENAME,
    ACTUAL_START_TIMESTAMP_ADJUSTED_QUESTIONS_TIMESTAMP_FILENAME,
)


logging.basicConfig(level=logging.DEBUG)
log = logging.getLogger(__name__)
TIMESTAMP_PLACEHOLDER = "--:--:--"
SPACERS = "=" * 20


class FileRecording:
    def __init__(self):
        self.record_file_name: str = None
        self.file_number_of_lines = 0
        self.banner_file: str = None
        # This attribute is set after this class is instantiated
        self.start_time_in_utc = None
        self.create_banner_file()
        self.create_live_chat_file()
        self.create_actual_timestamps_replied_questions_file()
        self.questions_open: bool = False

    def set_start_time(self, start_time_in_utc: datetime):
        log.debug(f"For FileRecording given start time: {start_time_in_utc}")
        self.start_time_in_utc = start_time_in_utc

    def create_banner_file(self):
        self.banner_file = get_resource(BANNER_FILENAME)
        log.debug("Creating banner file")
        with open(self.banner_file, "w", encoding="utf-8") as banner:
            banner.writelines(
                [
                    f"Buscador de preguntas previas: {QUESTION_LOOKUP_WEBPAGE}",
                    "\nPor favor pregunta una sola vez usando #pregunta",
                ]
            )

    def create_actual_timestamps_replied_questions_file(self):
        self.replied_questions_w_timestamp_file = get_time_adjusted_filename(
            ACTUAL_START_TIMESTAMP_ADJUSTED_QUESTIONS_TIMESTAMP_FILENAME, "txt"
        )
        # To make the file be under resources directory
        self.replied_questions_w_timestamp_file = get_resource(
            self.replied_questions_w_timestamp_file
        )

        # Creating the file
        with open(self.replied_questions_w_timestamp_file, "a", encoding="utf-8"):
            pass

    def create_live_chat_file(self):
        log.debug("Searching for live chat record file")
        self.live_chat_file = get_time_adjusted_filename(
            LIVE_CHAT_RECORD_FILENAME, "txt"
        )
        # To make the file be under resources directory
        self.live_chat_file = get_resource(self.live_chat_file)

        # Creating the file
        with open(self.live_chat_file, "a", encoding="utf-8"):
            pass

    def generate_file_w_timestamp_synchronized_replied_questions(
        self, replied_questions_w_timestamp: list[tuple[str, datetime]]
    ):
        with open(
            self.replied_questions_w_timestamp_file, "w", encoding="utf-8"
        ) as question_record_file:
            for replied_question_tuple in replied_questions_w_timestamp:
                # Where index 0 is the question text and the -1 is the replied_timestamp datetime value
                question = replied_question_tuple[0]
                replied_timestamp = replied_question_tuple[-1]
                adjusted_timestamp: timedelta = (
                    replied_timestamp - self.start_time_in_utc
                )

                # Taking out mseconds, if any
                record_to_store = str(adjusted_timestamp).split(".")[0] + " " + question

                if self.file_number_of_lines >= int(YOUTUBE_COMMENT_MAX_LENGTH):
                    question_record_file.write(
                        f"\n{SPACERS} {self.file_number_of_lines} {SPACERS}\n\n"
                    )
                    self.file_number_of_lines = 0

                question_record_file.write(record_to_store + "\n")

                self.file_number_of_lines += 1

    def update_banner(
        self,
        pending_questions: int = 0,
        replied_questions: int = 0,
        answer_average: str = None,
        estimated_total_wait: str = None,
        open_questions: bool = False,
    ) -> None:
        answer_average = answer_average or TIMESTAMP_PLACEHOLDER
        estimated_total_wait = estimated_total_wait or TIMESTAMP_PLACEHOLDER
        question_status_msg = "ABIERTAS." if open_questions else "CERRADAS."

        with open(self.banner_file, "w", encoding="utf-8") as banner:
            banner.writelines(
                [
                    f"Preguntas pendientes {pending_questions}",
                    f"\nTiempo promedio por respuesta: {answer_average}",
                    f"\nEspera estimada: {estimated_total_wait}",
                    f"\nPreguntas respondidas hoy: {replied_questions}",
                    f"\nPreguntas {question_status_msg}",
                ]
            )


if __name__ == "__main__":
    test = FileRecording()
    pass
