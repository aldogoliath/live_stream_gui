from stream_live_chat_gui import (
    get_client_creds,
    get_token,
    StreamerThreadControl,
    YOUTUBE_CHANNEL_ID,
    DATABASE_NAME,
    CREDS_AUTH_PORT,
    CHAT_FILTER_WORD,
    LIMITED_USERS,
)
from stream_live_chat_gui.db_interactions import DBInteractions
from queue import Queue
from datetime import datetime
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery_cache.base import Cache
from typing import Optional, Any
import os
import pickle
import logging


LOG_FORMAT = "%(asctime)s %(message)s"
logging.basicConfig(format=LOG_FORMAT, datefmt="%Y-%m-%d %H:%M:%S", level=logging.DEBUG)

log = logging.getLogger(__name__)

SCOPES = ["https://www.googleapis.com/auth/youtube.readonly"]
API_SERVICE_NAME, API_VERSION = "youtube", "v3"


class UnableToGetVideoId(Exception):
    pass


# Workaround https://bit.ly/3pu44bx
class MemoryCache(Cache):
    _CACHE = {}

    def get(self, url):
        return MemoryCache._CACHE.get(url)

    def set(self, url, content):
        MemoryCache._CACHE[url] = content


class YoutubeStreamThreadControl(StreamerThreadControl):
    def __init__(self, questions_control_queue: Queue, db_filename=None):
        super().__init__(name="YoutubeStreamThread")
        # Controls the periodicity of the call to get the live chat
        # comments/questions
        self._sleepperiod = 5.0
        self.set_youtube_thread_control_variables(questions_control_queue, db_filename)

    def set_youtube_thread_control_variables(
        self, questions_control_queue, db_filename
    ):
        self.youtube_service = YoutubeLiveChat(
            channel_id=YOUTUBE_CHANNEL_ID, db_filename=db_filename
        )
        self.questions_control_queue = questions_control_queue
        # Initializing
        self.open_questions_start_time = None

    def run(self):
        """Main control loop"""
        while not self._stopevent.is_set():
            if self.questions_control_queue.empty():
                log.debug("No value in queue")
            else:
                self.open_questions = self.questions_control_queue.get()
                if self.open_questions:
                    self.open_questions_start_time = datetime.utcnow()
                    log.debug(
                        f"Setting open_questions_start_time to: {self.open_questions_start_time}"
                    )
                else:
                    self.open_questions_start_time = None

                log.debug(f"Open questions queue value: {self.open_questions}")
            self.youtube_service.get_live_chat_messages_threaded(
                self.open_questions_start_time
            )
            # Make the thread sleep so the main thread (gui `controller`) gets to run as well.
            self._stopevent.wait(self._sleepperiod)


class YoutubeLiveChat:
    def __init__(
        self,
        channel_id: str = None,
        is_own_channel: bool = False,
        db_filename: str = None,
    ):
        if channel_id is None and not is_own_channel:
            raise ValueError(
                "channel_id nor own_channel where set.." "set one at least"
            )
        db_file = db_filename if db_filename else DATABASE_NAME
        self.start_time = datetime.utcnow()
        self.service = self.get_authenticated_service()
        self.channel_id = channel_id
        self.live_chat_id = (
            self.get_own_channel_live_chat_id()
            if is_own_channel
            else self.get_active_live_chat_id_via_channel_id()
        )
        self.live_messages_page_token: str = None
        self.db = DBInteractions(db_filename=db_file)

    # TODO: move this method to a different class or make it a module's method
    # (no need to be inside YoutubeLiveChat)
    def get_credentials(self) -> Optional[Any]:
        credentials = None
        creds_path = get_token()
        if os.path.exists(creds_path):
            log.debug(f"Loading credentials from file: {creds_path}")
            with open(creds_path, "rb") as token:
                credentials = pickle.load(token)
        return credentials

    # TODO: move this method to a different class or make it a module's method
    # (no need to be inside YoutubeLiveChat)
    def save_credentials(self, creds) -> None:
        """Save credentials for next run"""
        with open(get_token(), "wb") as f:
            log.debug("Saving credentials for future use.")
            pickle.dump(creds, f)

    # TODO: move this method to a different class or make it a module's method
    # (no need to be inside YoutubeLiveChat)
    def get_authenticated_service(self):
        credentials = self.get_credentials()
        if not credentials or not credentials.valid:
            if credentials and credentials.expired and credentials.refresh_token:
                log.debug("Refreshing access token...")
                credentials.refresh(Request())
            else:
                log.debug("Fetching New Tokens...")
                flow = InstalledAppFlow.from_client_secrets_file(
                    get_client_creds(), SCOPES
                )
                # port arg below is the one set when the oath client id creds
                # are created as URI
                flow.run_local_server(
                    port=int(CREDS_AUTH_PORT),
                    prompt="consent",
                    authorization_prompt_message="",
                )
                credentials = flow.credentials
                self.save_credentials(credentials)

        return build(
            API_SERVICE_NAME, API_VERSION, credentials=credentials, cache=MemoryCache()
        )

    def get_video_id(self, channel_id: str) -> str:
        log.debug(f"Searching for video_id given channel_id: {self.channel_id}")
        search_for_video_id = self.service.search().list(
            part="snippet", channelId=channel_id, eventType="live", type="video"
        )
        response = search_for_video_id.execute()

        if response["items"]:
            video_id = response["items"][0]["id"]["videoId"]
        else:
            raise UnableToGetVideoId(
                f"For channel ID: {self.channel_id} no live video_id was detected for api call "
                f"{response['kind']}: {response}. MAKE SURE YOU ARE:"
                "\n1.- Live streaming already\n2.- The live stream video is SET to PUBLIC."
            )
        return video_id

    def get_active_live_chat_id_via_channel_id(self) -> str:
        """Since live chat """
        video_id = self.get_video_id(self.channel_id)
        log.debug(f"video_id: {video_id}")
        search_for_active_live_chat_id = self.service.videos().list(
            part="snippet, liveStreamingDetails", id=video_id
        )
        response = search_for_active_live_chat_id.execute()
        log.debug(f"Search for active live chat id response: {response}")

        live_chat_id = response["items"][0]["liveStreamingDetails"]["activeLiveChatId"]
        log.debug(f"live chat id: {live_chat_id}")
        return live_chat_id

    def get_own_channel_live_chat_id(self) -> str:
        request = self.service.liveBroadcasts().list(part="snippet", mine=True)
        response = request.execute()
        log.debug(f"Response was: \n{response}")
        return response["items"][0]["snippet"]["liveChatId"]

    def get_live_chat_messages_threaded(
        self, open_questions_start_time: Optional[datetime]
    ) -> None:
        # https://developers.google.com/youtube/v3/live/docs/liveChatMessages/list
        request = self.service.liveChatMessages().list(
            liveChatId=self.live_chat_id,
            part="snippet, authorDetails",
            pageToken=self.live_messages_page_token,
        )
        response = request.execute()
        if not response["items"]:
            log.debug("No messages where found in this query")
            return

        self.live_messages_page_token = response["nextPageToken"]
        # each item = https://developers.google.com/youtube/v3/live/docs/liveChatMessages#resource
        for message in response["items"]:
            msg: str = message["snippet"]["displayMessage"]
            user: str = message["authorDetails"]["displayName"]
            published_at: str = message["snippet"]["publishedAt"]
            log.debug(f"Original msg published_at: {published_at}")

            # To avoid datetime formatting problems, miliseconds and beyond (+xx:yy | Z) characters get dropped
            published_at_satinized = published_at.split(".")[0]
            log.debug(f"Sanitized published_at: {published_at_satinized}")

            try:
                published_at_datetime: datetime = datetime.fromisoformat(
                    published_at_satinized
                )
            except ValueError:
                log.debug(
                    f"Couldn't read correctly the message: {msg}, with the next datetime: {published_at}. "
                    f"Sanitized version looks like: {published_at_satinized}"
                )
                return

            log.debug(f"Message: {msg}, published_at: {published_at_datetime}")
            if not published_at_datetime > self.start_time:
                log.debug(f"stale message: {msg}, published_at: {published_at}")
                return

            # TODO: Test the next inside db_interactions.py
            if any(limited_user in user.lower() for limited_user in LIMITED_USERS):
                questions_already_asked_by_user: int = (
                    self.db.count_questions_asked_by_user(user=user)
                )
                if questions_already_asked_by_user > 4:
                    log.debug(
                        f"The user: {user}, has already asked {questions_already_asked_by_user}, questions"
                    )
                    return

            # Normalize (lower-case) the message to filter out the CHAT_FILTER_WORD
            msg = msg.lower()

            if open_questions_start_time is None:
                log.debug("Questions are not open...")
                return

            if (
                CHAT_FILTER_WORD in msg
                and published_at_datetime > open_questions_start_time
            ):
                log.debug(f" User: {user}, sent a question: {msg}, at {published_at}")
                # Gets rid of the CHAT_FILTER_WORD in the captured msg and cleans up
                # double spaces or leading/trailing spaces
                cleaned_msg = " ".join(msg.replace(CHAT_FILTER_WORD, "").split())
                # If after cleaning it, the msg is not an empty string, then register it
                if cleaned_msg:
                    self.db.add_new_question(user_name=user, question_msg=cleaned_msg)
        return


if __name__ == "__main__":
    from stream_live_chat_gui import TEST_DB_FILENAME

    os.environ["OAUTHLIB_INSECURE_TRANSPORT"] = "1"
    youtube = YoutubeLiveChat(
        channel_id=YOUTUBE_CHANNEL_ID, db_filename=TEST_DB_FILENAME
    )
