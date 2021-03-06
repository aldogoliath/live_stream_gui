import logging
from datetime import datetime, timedelta
from stream_live_chat_gui import (
    get_resource,
    YOUTUBE_COMMENT_MAX_LENGTH,
    QUESTION_LOOKUP_WEBPAGE,
    BANNER_FILENAME,
    previous_file_reference,
    utc_to_local_time_formatted,
)


logging.basicConfig(level=logging.DEBUG)
log = logging.getLogger(__name__)
TIMESTAMP_PER_QUESTION_FILE_SUFFIX = "Replied_"
TIMESTAMP_PLACEHOLDER = "--:--:--"


class FileRecording:
    def __init__(self, start_time_in_utc: datetime, split_count: int):
        self.record_file_name: str = None
        self.start_time_in_utc = start_time_in_utc
        self.file_number_of_lines = 0
        self.banner_file: str = None
        self.create_banner_file()
        self.start_recording_timestamp_per_question_file(split_count)
        self.questions_open: bool = False

    def create_banner_file(self):
        self.banner_file = get_resource(BANNER_FILENAME)
        log.debug("Creating banner file")
        with open(self.banner_file, "w") as banner:
            banner.writelines(
                [
                    f"Buscador de preguntas previas: {QUESTION_LOOKUP_WEBPAGE}",
                    "\nPor favor pregunta una sola vez usando #pregunta",
                ]
            )

    def start_recording_timestamp_per_question_file(self, split_count: int) -> None:
        """
        Only need to confirm if a file has been created already for this session/day,
        so no new one is created since the show covers 2 datetimes.
        What changes here in the filename, besides the possible different split_count is mainly the
        file_datetime. It can point to yesterday or today.
        """
        # First look for a file being created one day before
        file_datetime: str = utc_to_local_time_formatted(
            self.start_time_in_utc - timedelta(days=1)
        )

        previous_file = previous_file_reference(
            file_datetime, TIMESTAMP_PER_QUESTION_FILE_SUFFIX, "txt"
        )

        if previous_file:
            log.debug(f"A reference file existed for datetime: {previous_file}")
            self.record_file_name = f"{file_datetime}_Replied_{split_count}.txt"
            log.debug(f"Record file name: {self.record_file_name}")
            return

        log.debug(f"No active record_file was found for datetime: {file_datetime}")

        file_datetime = utc_to_local_time_formatted(self.start_time_in_utc)

        # split_count should be `0` in this case
        self.record_file_name = f"{file_datetime}_Replied_{split_count}.txt"
        log.debug(
            f"A new file will be created as: {self.record_file_name}, for today's date"
        )
        # Creating the file
        with open(get_resource(self.record_file_name), "a"):
            pass

    def add_entry_to_record_file(self, replied_timestamp, question):
        adjusted_timestamp: timedelta = replied_timestamp - self.start_time_in_utc
        # Taking out mseconds
        record_to_store = str(adjusted_timestamp).split(".")[0] + " " + question
        with open(get_resource(self.record_file_name), "a") as record_file:

            if self.file_number_of_lines >= int(YOUTUBE_COMMENT_MAX_LENGTH):
                record_file.write(
                    f"\n==================== {self.file_number_of_lines} ==================\n\n"
                )
                self.file_number_of_lines = 0

            record_file.write(record_to_store + "\n")
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

        with open(self.banner_file, "w") as banner:
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
    pass
