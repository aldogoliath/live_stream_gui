from sqlalchemy import func
from sqlalchemy.orm import joinedload
from datetime import datetime, timedelta
from stream_live_chat_gui import (
    QuestionTuple,
    get_db_session,
    session_manager,
)
from typing import Optional
from stream_live_chat_gui.database_model import Question, User

# from treelib import Tree  # treelib installed only for testing
import logging

logging.basicConfig(level=logging.DEBUG)
log = logging.getLogger(__name__)


class DBInteractions:
    def __init__(self, db_filename: str = None):
        self.session = get_db_session(db_filename)

    def add_new_question(self, user_name: str, question_msg: str) -> None:
        """Add a new question to the database"""
        # Check if the question already exists (no matter the user)
        with session_manager(self.session) as session:
            question = (
                session.query(Question)
                .filter(Question.question == question_msg)
                .one_or_none()
            )

            if question is not None:
                log.debug(
                    f"DUPLICATED_QUESTION: {question_msg} was already in the table"
                )
                return

            log.debug(f"Question from user: {user_name} question: {question_msg}")

            # Create the question if needed
            question = Question(question=question_msg)

            # Check if the user making the question already exists
            user = session.query(User).filter(User.name == user_name).one_or_none()

            if user is None:
                user = User(name=user_name)
                session.add(user)

            # Initialize the question relationship
            question.user = user
            session.add(question)

    def delete_question_with_id(self, question_id: int) -> None:
        with session_manager(self.session) as session:
            question = (
                session.query(Question).filter(Question.id == question_id).first()
            )
            log.debug(f"Deleting question: {question.question}, with id: {question_id}")
            session.delete(question)

    def mark_unmark_question_as_replied(
        self, question_id: int, replied: bool = True
    ) -> None:
        """Marks the attribute 'is_replied' of a Question to be True by default when invoked.
        With this same method we can set that attribute to False if necessary.
        i.e. when revisiting a question already marked as replied to be rollbacked"""
        time_now = datetime.utcnow()
        log.debug(
            f"Mark question with id: {question_id} as replied = {replied}, now: {time_now}"
        )
        with session_manager(self.session) as session:
            question = session.query(Question).get(question_id)
            if replied:
                session.query(Question).filter(Question.id == question_id).update(
                    {
                        Question.is_replied: replied,
                        Question.waited: str(time_now - question.created_ts),
                    }
                )
            else:
                session.query(Question).filter(Question.id == question_id).update(
                    {
                        Question.replied_ts: question.created_ts,
                        Question.is_replied: replied,
                        Question.waited: "00:00",
                    }
                )

            log.debug(
                f"{question.question}'s flag is_replied updated to {question.is_replied}"
            )

    def get_all_users(self):
        # Applying here eager loading `.options(joinedload(...))`
        with session_manager(self.session) as session:
            users = (
                session.query(User)
                .options(joinedload(User.questions))
                .order_by(User.name)
                .all()
            )
            return [user.name for user in users]

    def get_next_pending_question(self) -> QuestionTuple:
        with session_manager(self.session) as session:
            next_question = (
                session.query(Question)
                .filter(Question.is_replied == 0)
                .order_by(Question.id)
                .first()
            )
            return QuestionTuple(
                next_question.id, next_question.user.name, next_question.question
            )

    def get_next_pending_question_randomly(self) -> QuestionTuple:
        log.debug("Getting random question")
        # https://stackoverflow.com/a/33583008/2706103
        # TODO: check on how to use "joinloaded" to execute eager_loading on the next query
        with session_manager(self.session) as session:
            random_question = (
                session.query(Question)
                .options(joinedload(Question.user))
                .filter(Question.is_replied == 0)
                .order_by(func.random())
                .first()
            )

            return QuestionTuple(
                random_question.id, random_question.user.name, random_question.question
            )

    def get_pending_question_with_given_id(self, id: int):
        with session_manager(self.session) as session:
            next_question = (
                session.query(Question).filter(Question.id == id).one_or_none()
            )
            log.debug(f"Found question: {next_question.question} with given id: {id}")
            return QuestionTuple(
                next_question.id, next_question.user.name, next_question.question
            )

    def count_all_pending_questions(self) -> int:
        with session_manager(self.session) as session:
            pending_questions = (
                session.query(Question)
                .filter(Question.is_replied == False)  # noqa: E712
                .count()
            )
            return pending_questions

    def count_all_replied_questions(self) -> int:
        with session_manager(self.session) as session:
            replied_questions = (
                session.query(Question)
                .filter(Question.is_replied == True)  # noqa: E712
                .count()
            )
            return replied_questions

    def count_questions_asked_by_user(self, user: str) -> int:
        with session_manager(self.session) as session:
            number_of_questions = (
                session.query(User)
                .filter(User.name.contains(user))
                .join(Question)
                .count()
            )
            return number_of_questions

    def calculate_answer_average_time(self) -> Optional[timedelta]:
        with session_manager(self.session) as session:
            replied_questions_by_replied_ts = (
                session.query(Question)
                .filter(Question.is_replied == True)  # noqa: E712
                .order_by(Question.replied_ts.desc())
                .all()
            )
            number_of_replied_questions = len(replied_questions_by_replied_ts)

            if number_of_replied_questions < 2:
                return

            replied_questions_replied_ts: list[datetime] = [
                question.replied_ts for question in replied_questions_by_replied_ts
            ]

            latest_answered = replied_questions_replied_ts[0]
            total_answer_time = timedelta(0)
            for question_replied_ts in replied_questions_replied_ts[1:]:
                total_answer_time += latest_answered - question_replied_ts
                # TODO: delete this log statement after debugging is done
                log.debug(f"latest_answered: {latest_answered}")
                log.debug(f"question_replied_ts: {question_replied_ts}")
                latest_answered = question_replied_ts

            answer_average_time = total_answer_time / number_of_replied_questions
            log.debug(
                f"Calculated answer_average_time: {answer_average_time}, "
                f"with number_of_replied_questions: {number_of_replied_questions}"
            )
            return answer_average_time

    def calculate_wait_average_time(self) -> Optional[timedelta]:
        with session_manager(self.session) as session:
            replied_questions = (
                session.query(Question)
                .filter(Question.is_replied == True)  # noqa: E712
                .all()
            )
            number_of_replied_questions = len(replied_questions)

            if number_of_replied_questions < 1:
                return

            total_waited_time = timedelta(0)
            for question in replied_questions:
                waited_in_dt = datetime.strptime(
                    question.waited.split(".")[0], "%H:%M:%S"
                )
                total_waited_time += timedelta(
                    hours=waited_in_dt.hour,
                    minutes=waited_in_dt.minute,
                    seconds=waited_in_dt.second,
                )
            waited_average_time = total_waited_time / number_of_replied_questions
            log.debug(
                f"Calculated waited_average_time: {waited_average_time}, "
                f"with number_of_replied_questions: {number_of_replied_questions}"
            )
            return waited_average_time

    def get_last_n_replied(
        self, number_of_questions_to_return: int
    ) -> list[QuestionTuple]:
        with session_manager(self.session) as session:
            replied_questions = (
                session.query(Question)
                .filter(Question.is_replied == True)  # noqa: E712
                .order_by(Question.replied_ts.desc())
                .limit(number_of_questions_to_return)
            )
            r_questions = [
                QuestionTuple(question.id, question.user.name, question.question)
                for question in replied_questions
            ]
            return r_questions


if __name__ == "__main__":
    from stream_live_chat_gui import DATABASE_NAME

    # Section only used for local testing
    db_interactions = DBInteractions(DATABASE_NAME)

    next_question = db_interactions.get_next_pending_question()
    print(f"{next_question.id}: {next_question.user}: {next_question.question}")

    random_question = db_interactions.get_next_pending_question_randomly()
    print(f"{random_question.id}: {random_question.user}: {random_question.question}")

    pending_questions = db_interactions.count_all_pending_questions()
    print(
        f"pending questions number: {pending_questions}, type: {type(pending_questions)}"
    )

    # db_interactions.calculate_answer_average()
    USER = "Artemio"
    print(
        f"Questions asked by {USER}: {db_interactions.count_questions_asked_by_user(user=USER)}"
    )
