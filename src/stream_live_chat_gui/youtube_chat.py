from stream_live_chat_gui import (
    get_client_creds,
    get_token,
    StreamerThreadControl,
    YOUTUBE_CHANNEL_ID,
    DATABASE_NAME,
    CREDS_AUTH_PORT,
    CHAT_FILTER_WORD,
    LIMITED_USERS,
    PRIVATE_TESTING,
    LIVE_VIDEO_ID,
    QUESTIONS_LIMIT,
)
from stream_live_chat_gui.db_interactions import DBInteractions
from queue import Queue
from datetime import datetime
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery_cache.base import Cache
from typing import Optional, Any
import requests
import os
import re
import pickle
import logging
import time


LOG_FORMAT = "%(asctime)s %(message)s"
logging.basicConfig(format=LOG_FORMAT, datefmt="%Y-%m-%d %H:%M:%S", level=logging.DEBUG)

log = logging.getLogger(__name__)

SCOPES = ["https://www.googleapis.com/auth/youtube.readonly"]
API_SERVICE_NAME, API_VERSION = "youtube", "v3"
LIVE_STREAM_TARGET_URL = f"https://www.youtube.com/channel/{YOUTUBE_CHANNEL_ID}/live"
PATTERN_TO_FIND_VIDEO_ID_USING_REQUESTS = r'"videoId":"(?P<video_id>.*)","broadcastId"'
LIVE_BROADCASTS_LIST_MAX_RESULTS = 50


class UnableToGetVideoId(Exception):
    pass


class UnableToGetLiveChatId(Exception):
    pass


# Workaround https://bit.ly/3pu44bx
class MemoryCache(Cache):
    _CACHE = {}

    def get(self, url):
        return MemoryCache._CACHE.get(url)

    def set(self, url, content):
        MemoryCache._CACHE[url] = content


class YoutubeStreamThreadControl(StreamerThreadControl):
    def __init__(
        self,
        questions_control_queue: Queue,
        live_chat_record_file: str,
        db_filename=None,
    ):
        super().__init__(name="YoutubeStreamThread")
        # Controls the periodicity of the call to get the live chat comments/questions
        self._sleepperiod = 7.0
        self.set_youtube_thread_control_variables(
            questions_control_queue, live_chat_record_file, db_filename
        )

    def set_youtube_thread_control_variables(
        self, questions_control_queue, live_chat_record_file, db_filename
    ):
        self.youtube_service = YoutubeLiveChat(
            live_chat_record_file=live_chat_record_file,
            channel_id=YOUTUBE_CHANNEL_ID,
            db_filename=db_filename,
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
        live_chat_record_file: str,
        channel_id: str = None,
        db_filename: str = None,
    ):
        log.debug(f"PRIVATE_TESTING envvar is set to {PRIVATE_TESTING}")
        is_own_channel = True if PRIVATE_TESTING == "yes" else False

        if channel_id is None and not is_own_channel:
            raise ValueError(
                "channel_id nor own_channel where set.." "set one at least"
            )
        log.debug(f"Passed live_chat_record_file: {live_chat_record_file}")
        self.live_stream_actual_start_time: datetime = None
        db_file = db_filename if db_filename else DATABASE_NAME
        self.service = self.get_authenticated_service_using_oath()
        self.channel_id = channel_id
        self.live_chat_id = (
            self.get_own_channel_live_chat_id()
            if is_own_channel
            else self.get_active_live_chat_id_via_channel_id()
        )
        self.start_time = datetime.utcnow()
        log.debug(f"YoutubeLiveChat start time: {self.start_time}")
        self.live_chat_record_file = live_chat_record_file
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
    def get_authenticated_service_using_oath(self):
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

    def get_video_id(self) -> str:
        log.debug(f"Searching for video_id given channel_id: {self.channel_id}")
        search_for_video_id = self.service.search().list(
            part="snippet", channelId=self.channel_id, eventType="live", type="video"
        )
        response = search_for_video_id.execute()

        if response["items"]:
            video_id = response["items"][0]["id"]["videoId"]
        else:
            raise UnableToGetVideoId(
                f"For channel ID: {self.channel_id} no live video_id was detected for api call "
                f"{response['kind']}: {response}.\nMAKE SURE YOU ARE:"
                "\n1.- Live streaming already\n2.- The live stream video is SET to PUBLIC."
            )
        return video_id

    def get_video_id_no_api(self) -> str:
        log.debug("Getting video_id NOT using youtube api")
        youtube_live_stream_reply = requests.get(LIVE_STREAM_TARGET_URL)
        match = re.search(
            PATTERN_TO_FIND_VIDEO_ID_USING_REQUESTS, youtube_live_stream_reply.text
        )
        if match:
            video_id = match.group("video_id")
        else:
            raise UnableToGetVideoId(
                f"For channel ID: {self.channel_id} no live video_id was detected using the NO api method"
                "\nMAKE SURE YOU ARE:\n1.- Live streaming already\n2.- The live stream video is SET to PUBLIC."
            )
        return video_id

    def get_active_live_chat_id_via_channel_id(self, video_id: str = None) -> str:
        """Since live chat """
        # This works for unlisted videos too
        if not video_id:
            # TODO: decide whether to deprecate this method in favor of the one using requests library after testing
            # video_id = self.get_video_id()
            video_id = self.get_video_id_no_api()

        log.debug(f"video_id: {video_id}")
        search_for_active_live_chat_id = self.service.videos().list(
            part="snippet, liveStreamingDetails", id=video_id
        )
        response = search_for_active_live_chat_id.execute()
        log.debug(f"Search for active live chat id response: {response}")

        item_of_interest = response["items"][0]
        log.debug(f"Item of interest: {item_of_interest}")

        live_chat_id = item_of_interest["liveStreamingDetails"]["activeLiveChatId"]
        log.debug(f"live chat id: {live_chat_id}")
        actual_start_time = item_of_interest["liveStreamingDetails"]["actualStartTime"]
        self._set_actual_start_time(actual_start_time)

        return live_chat_id

    def get_own_channel_live_chat_id(self) -> str:
        # https://developers.google.com/youtube/v3/live/docs/liveBroadcasts#resource
        live_broadcast_next_token = None
        number_of_executions = 1
        log.debug("Getting own channel live chat id for private testing")

        if LIVE_VIDEO_ID:
            try:
                log.warning(
                    f"Trying to find chat id using the manually given live video id: {LIVE_VIDEO_ID}"
                )
                return self.get_active_live_chat_id_via_channel_id(
                    video_id=LIVE_VIDEO_ID
                )
            except Exception:
                log.exception(
                    f"Not live_chat_id was found with the ENV VAR given live_video_id: {LIVE_VIDEO_ID}"
                )

        while True:
            request = self.service.liveBroadcasts().list(
                part="snippet, status",
                mine=True,
                broadcastType="all",
                maxResults=LIVE_BROADCASTS_LIST_MAX_RESULTS,
                pageToken=live_broadcast_next_token,
            )
            response = request.execute()
            total_results_pagination = int(response["pageInfo"]["totalResults"])
            log.debug(f"Response was: \n{response}")

            if not response["items"] or not response["nextPageToken"]:
                break

            live_broadcast_next_token = response["nextPageToken"]
            log.debug(f"Next token: {live_broadcast_next_token}")
            if response["items"] and any(
                item["status"]["lifeCycleStatus"] == "live"
                for item in response["items"]
            ):
                log.debug(
                    "Item with lifeCycleStatus `live` inside liveBroadcasts list found!}"
                )
                for item in response["items"]:
                    if item["status"]["lifeCycleStatus"] == "live":
                        live_chat_id = item["snippet"]["liveChatId"]
                        self._set_actual_start_time(item["snippet"]["actualStartTime"])
                        return live_chat_id

            if (
                LIVE_BROADCASTS_LIST_MAX_RESULTS * number_of_executions
                >= total_results_pagination
            ):
                break
            number_of_executions += 1
            time.sleep(0.3)

        raise UnableToGetLiveChatId(
            f"No live_chat_id was detected for api call {response['kind']}."
            "\nMAKE SURE YOU ARE: \n1.- Live streaming already\n2.- The live stream video is SET to PUBLIC."
        )

    def _set_actual_start_time(self, actual_start_time: str) -> None:
        log.debug(f"Given actual_start_time: {actual_start_time}")
        actual_start_time = actual_start_time.strip("Z").split(".")[0]
        self.live_stream_actual_start_time = datetime.fromisoformat(actual_start_time)
        log.debug(
            f"live_stream_actual_start_time (sanitized): {self.live_stream_actual_start_time}"
        )

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
            msg_type: str = message["snippet"]["type"]
            published_at: str = message["snippet"]["publishedAt"]

            # To avoid datetime formatting problems, miliseconds and beyond (+xx:yy | Z) characters get dropped
            published_at_sanitized = published_at.split(".")[0]

            try:
                published_at_datetime: datetime = datetime.fromisoformat(
                    published_at_sanitized
                )
            except ValueError:
                log.debug(
                    f"Couldn't read correctly the message: {msg}, with the next datetime: {published_at}. "
                    f"Sanitized version looks like: {published_at_sanitized}"
                )
                continue

            log.debug(f"Message: {msg}, published_at: {published_at_datetime}")
            # If the next is True it means that the published message from the live chat is older than the datetime
            # on which the Start Stream button was clicked
            if self.start_time > published_at_datetime:
                log.debug(f"stale message: {msg}, published_at: {published_at}")
                continue

            # Normalize (lower-case) the message to filter out the CHAT_FILTER_WORD
            msg = msg.lower()

            if "superchat" in msg_type.lower():
                # Temporarily catching all exceptions here to test super chat implementation without breaking the thread
                try:
                    self.register_superchat(user, message)
                except Exception as e:
                    log.exception(f"Register super chat function failed with: {e}")
                continue

            if CHAT_FILTER_WORD not in msg:
                live_chat_comment = f"{user}: {msg}"
                # std.out is redirected to a widget in the GUI (live_chat_feed_text_box)
                print(live_chat_comment)
                with open(
                    self.live_chat_record_file, "a", encoding="utf-8"
                ) as live_chat_file:
                    live_chat_file.write(f"{live_chat_comment}\n")

            if open_questions_start_time is None:
                log.debug("Questions are not open...")
                continue

            if (
                CHAT_FILTER_WORD in msg
                and published_at_datetime > open_questions_start_time
            ):
                log.debug(f" User: {user}, sent a question: {msg}, at {published_at}")
                # TODO: Add superchat event handling here (register the question, since it's priority)

                if self.has_limited_user_exceeded_question_count(user):
                    continue

                # Gets rid of the CHAT_FILTER_WORD in the captured msg and cleans up
                # double spaces or leading/trailing spaces
                cleaned_msg = " ".join(msg.replace(CHAT_FILTER_WORD, "").split())
                # If after cleaning it, the msg is not an empty string, then register it
                if cleaned_msg:
                    self.db.add_new_question(user_name=user, question_msg=cleaned_msg)

        return

    def register_superchat(self, user: str, message: str) -> None:
        # TODO: ADD SUPER CHAT exception handling
        log.warning("Pending Super Chat implementation testing")
        log.debug(f"Super chat message contents: {message}")
        log.debug(f"Super chat message type: {type(message)}")
        super_chat_msg: str = message["snippet"]["superChatDetails"]["userComment"]
        currency: str = message["snippet"]["superChatDetails"]["currency"]
        amount: str = message["snippet"]["superChatDetails"]["amountDisplayString"]

        # Gets rid of the CHAT_FILTER_WORD in the captured msg and cleans up
        # double spaces or leading/trailing spaces
        if CHAT_FILTER_WORD in super_chat_msg:
            super_chat_msg = " ".join(
                super_chat_msg.replace(CHAT_FILTER_WORD, "").split()
            )

        if not super_chat_msg:
            log.debug(f"For super chat event, user: {user}, left No Comment")
            super_chat_msg = "NO COMMENT"
        super_chat_msg = f"[SUPER CHAT] {user}: {super_chat_msg}"
        # For super chat, we append the user name to the message for now and print it as well
        print(
            f"[SUPER CHAT], currency: {currency}, amount: {amount}. Message: {super_chat_msg}"
        )
        self.db.add_new_question(
            user_name=user, question_msg=super_chat_msg, is_super_chat=True
        )

    def has_limited_user_exceeded_question_count(self, user: str) -> bool:
        if any(limited_user in user.lower() for limited_user in LIMITED_USERS):
            questions_already_asked_by_user: int = (
                self.db.count_questions_asked_by_user(user=user)
            )
            if questions_already_asked_by_user >= QUESTIONS_LIMIT:
                log.debug(
                    f"The user: {user}, has already asked {questions_already_asked_by_user}, questions"
                )
                return True
        return False


if __name__ == "__main__":
    from stream_live_chat_gui import TEST_DB_FILENAME

    os.environ["OAUTHLIB_INSECURE_TRANSPORT"] = "1"
    youtube = YoutubeLiveChat(
        channel_id=YOUTUBE_CHANNEL_ID, db_filename=TEST_DB_FILENAME
    )
