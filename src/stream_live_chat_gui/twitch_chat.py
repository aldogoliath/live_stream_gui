from socket import socket, AF_INET, SOCK_STREAM
import logging
import os
import re
from dotenv import load_dotenv

from stream_live_chat_gui.db_interactions import DBInteractions
from stream_live_chat_gui import StreamerThreadControl

# TODO: All environmental variables should be passed through __init__
load_dotenv()
FORMAT = "%(asctime)s %(message)s"
logging.basicConfig(format=FORMAT, datefmt="%Y-%m-%d %H:%M:%S", level=logging.DEBUG)
log = logging.getLogger(__name__)

SERVER = os.getenv("SERVER")
PORT = int(os.getenv("PORT"))
NICKNAME = os.getenv("NICKNAME")
# Set at .env file in the root folder
TOKEN = os.getenv("TOKEN")
CHANNEL = os.getenv("CHANNEL")
MSGBUFFSIZE = int(os.getenv("MSGBUFFSIZE"))
MESSAGEREGEX = r"^:(?P<user>\w+)!.*\#(?P<channel>\w+)?\s:(?P<message>.*)"


def log_in(socket_: socket) -> None:
    starting_strings = [f"PASS {TOKEN}\n", f"NICK {NICKNAME}\n", f"JOIN {CHANNEL}\n"]
    for string_ in starting_strings:
        socket_.send(string_.encode("utf-8"))
    log.debug("INITIALIZING THE CONNECTION TO TWITCH IRC")
    return


class TwitchStreamThreadControl(StreamerThreadControl):
    """Setting initial variabels"""

    def __init__(self):
        super().__init__(name="TwitchStreamThread")
        self.set_twitch_thread_control_variables()

    def set_twitch_thread_control_variables(self):
        self.socket = socket(AF_INET, SOCK_STREAM)
        self.socket.connect((SERVER, PORT))
        self.socket.setblocking(0)  # non-blocking mode
        self.db = DBInteractions()

    def run(self):
        """Main control loop"""
        log_in(self.socket)
        log.debug(f"{self.getName} starts")
        response = ""
        while not self._stopevent.is_set():
            try:
                response = self.socket.recv(MSGBUFFSIZE).decode("utf-8")
            except BlockingIOError:
                continue
            log.debug("END OF socket RECV operation")

            if response.startswith("PING"):
                self.socket.send("PONG\n".encode("utf-8"))
            elif (
                "PRIVMSG" in response
            ):  # IRC msgs have the string PRIVMSG in it, the rest are server side gibberish
                response = response.rstrip()
                log.debug(f"{response}")
                matches = re.search(MESSAGEREGEX, response)
                if matches:
                    user = matches.group("user")
                    message = matches.group("message")
                    log.debug(f"{user} {message}")
                    self.db.add_new_question(user_name=user, question_msg=message)
                else:
                    log.debug(f"NOT_VALID_MSG: {response}")
            else:
                pass  # ignore the response

            # Make the thread sleep so the main thread (controller) gets to run as well.
            self._stopevent.wait(self._sleepperiod)


# This function is for pure local testing
def chat_streamer() -> None:
    sock: socket = socket()
    sock.connect((SERVER, PORT))
    log_in(sock)
    response = ""
    while True:
        response = sock.recv(MSGBUFFSIZE).decode("utf-8")
        if response.startswith("PING"):
            sock.send("PONG\n".encode("utf-8"))
        else:
            log.debug(f"{response.rstrip()}")

    sock.close()


if __name__ == "__main__":
    chat_streamer()
