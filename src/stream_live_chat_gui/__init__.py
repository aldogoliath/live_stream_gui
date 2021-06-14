from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, scoped_session, Session as SQLSession
from sqlalchemy.engine.base import Engine  # added only for type hinting
from sqlalchemy.sql.schema import Column  # added only for type hinting
from stream_live_chat_gui.database_model import Base
from dataclasses import dataclass
from contextlib import contextmanager
from dotenv import load_dotenv
from threading import Thread, Event
from datetime import datetime, timezone, timedelta
import os
import json
import logging
from typing import NamedTuple, Optional

log = logging.getLogger(__name__)

SAVE_FILES_DATETIME_FORMAT = "%m%d%Y"

load_dotenv(".env")
BANNER_FILENAME = os.getenv("BANNER_FILENAME")
LIVE_CHAT_RECORD_FILENAME = os.getenv("LIVE_CHAT_RECORD_FILENAME")
ACTUAL_START_TIMESTAMP_ADJUSTED_QUESTIONS_TIMESTAMP_FILENAME = os.getenv(
    "ACTUAL_START_TIMESTAMP_ADJUSTED_QUESTIONS_TIMESTAMP_FILENAME"
)
CLIENT_SECRETS_FILE = os.getenv("CLIENT_SECRETS_FILE")
YOUTUBER_NAME = os.getenv("YOUTUBER_NAME")
TOKEN_FILE = os.getenv("TOKEN_FILE")
YOUTUBE_CHANNEL_ID = os.getenv("YOUTUBE_CHANNEL_ID")
CREDS_AUTH_PORT = os.getenv("CREDS_AUTH_PORT")
YOUTUBE_COMMENT_MAX_LENGTH = os.getenv("YOUTUBE_COMMENT_MAX_LENGTH")
QUESTION_LOOKUP_WEBPAGE = os.getenv("QUESTION_LOOKUP_WEBPAGE")
CHAT_FILTER_WORD = os.getenv("CHAT_FILTER_WORD")
YOUTUBE_DATETIME_FORMAT = os.getenv("YOUTUBE_DATETIME_FORMAT")
PRIVATE_TESTING = os.getenv("PRIVATE_TESTING")
LIVE_VIDEO_ID = os.getenv("LIVE_VIDEO_ID")
QUESTIONS_LIMIT = os.getenv("QUESTIONS_LIMIT")
QUESTIONS_LIMIT = int(QUESTIONS_LIMIT) if QUESTIONS_LIMIT else 4
# Checking that PRIVATE_TESTING envvar is set correctly
if not PRIVATE_TESTING or not any(
    PRIVATE_TESTING.lower() == valid_option for valid_option in ["yes", "no"]
):
    raise ValueError(
        f"PRIVATE_TESTING value is incorrect: {PRIVATE_TESTING}, it needs to be either 'yes' or 'no'"
    )
# Can be deleted
TEST_DB_FILENAME = os.getenv("TEST_DB_FILENAME")
LIMITED_USERS = [user.strip().lower() for user in os.getenv("LIMITED_USERS").split(",")]
TOP_MESSAGE_OF_TIMESTAMP_FILE = (
    "00:00:00 " + (os.getenv("TOP_MESSAGE_OF_TIMESTAMP_FILE") or "Start") + "\n"
)


def search_files_in_resources_directory_given_extension(extension: str) -> list[str]:
    files_found = [
        file_
        for file_ in os.listdir(os.path.join(os.getcwd(), "resources"))
        if file_.endswith("." + extension)
    ]
    files_found.sort()
    log.debug(f"Found files: {files_found}")
    return files_found


# https://bit.ly/3aAI1f5
def utc_to_local_time_formatted(utc_timestamp: datetime) -> str:
    local_timestamp: datetime = utc_timestamp.replace(tzinfo=timezone.utc).astimezone(
        tz=None
    )
    log.debug(
        f"Given utc datetime: {utc_timestamp}, converted it to local time: {local_timestamp}"
    )
    return local_timestamp.strftime(SAVE_FILES_DATETIME_FORMAT)


def previous_file_reference(
    datetime_prefix: str,
    file_name_suffix: str,
    file_extension: str,
) -> Optional[str]:
    """Looks for latest file found under the ./resources directory given a prefix/suffix and file extension"""
    log.debug(
        f"Given inputs: datetime_prefix: {datetime_prefix}, file_name_suffix: {file_name_suffix}, "
        f"file_extension: {file_extension}"
    )
    existing_files = search_files_in_resources_directory_given_extension(file_extension)
    filter_by = datetime_prefix + "_" + file_name_suffix
    log.debug(f"Existing files: {existing_files}, filter by: {filter_by}")
    filtered_by_name_suffix_files = [
        file_ for file_ in existing_files if filter_by in file_
    ]
    log.debug(f"Found filtered_by_name_suffix_files: {filtered_by_name_suffix_files}")

    if filtered_by_name_suffix_files:
        return filtered_by_name_suffix_files[-1]
    return


def get_time_adjusted_filename(filename_reference: str, file_extension: str) -> str:
    log.debug(
        f"With filename reference: {filename_reference} and file extension: {file_extension}"
    )
    # First look for a file being created "one day" before
    local_datetime: str = utc_to_local_time_formatted(
        datetime.utcnow() - timedelta(hours=23)
    )
    previous_file = previous_file_reference(
        datetime_prefix=local_datetime,
        file_name_suffix=filename_reference,
        file_extension=file_extension,
    )

    if previous_file:
        log.debug(f"Previous file existed: {previous_file}")
        return previous_file

    # If the file didn't exist with one day before datime, set to now
    local_datetime: str = utc_to_local_time_formatted(datetime.utcnow())
    filename_to_be_created = f"{local_datetime}_{filename_reference}"
    log.debug(f"Filename to be created = {filename_to_be_created}")
    return filename_to_be_created


db_name = os.getenv("DATABASE_NAME")
DATABASE_NAME = get_time_adjusted_filename(db_name, "db")


# TODO: Learn how to use joinedload in the query of questions to avoid this NamedTuple
class QuestionTuple(NamedTuple):
    id: int
    user: str
    question: str


@dataclass
class AlchemizedModelColumn:
    column: Column
    column_name: str
    header_display_name: str = None
    flags: dict = None


# From -> https://learning.oreilly.com/library/view/python-cookbook/0596001673/ch06s03.html
class StreamerThreadControl(Thread):
    """Setting initial variabels"""

    def __init__(self, name="StreamerThreadControl"):
        super().__init__(name=name)
        self._stopevent = Event()
        self._sleepperiod = 1.0

    def run(self):
        # Placeholder, it should be overwritten inside the child class
        pass

    def join(self, timeout=None):
        """Stops the thread"""
        self._stopevent.set()
        Thread.join(self, timeout)


# https://youtu.be/36yw8VC3KU8?t=792
@contextmanager
def session_manager(session: SQLSession) -> None:
    """Provide a transactional scope around a series of operations"""
    session_ = session()
    try:
        yield session_
        session_.commit()
    except:  # noqa: E722
        session_.rollback()
        raise
    finally:
        session_.close()


def print_to_json(response: dict) -> None:
    print(json.dumps(response, indent=2))


def get_resource(resource_name: str) -> str:
    log.debug(f"Current Directory: {os.getcwd()}")
    return os.path.join(os.getcwd(), "resources", resource_name)


def get_token() -> str:
    return get_resource(TOKEN_FILE)


def get_client_creds() -> str:
    return get_resource(CLIENT_SECRETS_FILE)


def create_db():
    get_engine(db_filename=DATABASE_NAME)


def get_log_file_name() -> str:
    log_name = os.getenv("LOG_FILE")
    adjusted_log_name = get_time_adjusted_filename(log_name, "log")
    log_name_in_resources_path = get_resource(adjusted_log_name)
    log.debug(f"Log filename adjusted: {log_name_in_resources_path}")
    return log_name_in_resources_path


# https://stackoverflow.com/questions/12223335/sqlalchemy-creating-vs-reusing-a-session
# https://docs.sqlalchemy.org/en/13/orm/contextual.html#unitofwork-contextual
def get_db_session(db_filename: str = None):
    engine = get_engine(db_filename)
    session_factory = sessionmaker(bind=engine)
    Session = scoped_session(session_factory)
    return Session


def get_engine(db_filename: str = DATABASE_NAME) -> Engine:
    """
    Returns an Engine object that will be used to bind it to an sqlalchemy Session.
    If the database file is not created, it creates it on the fly.
    It does so by taking into account the passed db_filename if any, if nothing is passed, then
    the database_filename will be the one set by the environmental variable.
    """
    if db_filename:
        db_name = db_filename

    log.debug(f"Database filename: {db_name}")
    sqlite_filepath = get_resource(db_name)
    log.debug(f"DB Filepath: {sqlite_filepath}")

    engine = create_engine(f"sqlite:///{sqlite_filepath}", echo=False)

    # Check if the Database file already exists
    if not os.path.exists(sqlite_filepath):
        # Create the database and tables
        log.debug("Creating database and tables")
        Base.metadata.create_all(bind=engine)

    return engine
