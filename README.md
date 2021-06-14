# live_stream_gui
Stores the contents of different sources of live chat messages (mainly youtube, twitch integration is unfinished) in a 
local sqlite db. The application is useful for a live stream video that is interactive with the audience, where the 
audience asks questions and the host(s) respond to those. It basically scraps text out of a youtube live chat session 
with keyword that the host of the live stream decides.
The audience would then need to put messages in the chat using such keyword so those messages get stored locally and 
the hosts can see them.
This application is used so far in this youtube channel live stream format https://bit.ly/3gynnhh


## How to "compile"
Install pyinstaller (https://www.pyinstaller.org)
Execute the command -> `pyinstaller.exe <file_name>.spec`
(in my case my .spec filename is gui.spec so the command I use is: `pyinstaller.exe gui.spec`)

The application uses `google-api-python-client` which is not copied by default to the library folder that gets created 
once the pyinstaller command is used (pyinstaller copies in general all the dependencies present in your interpreter).
In my case, I used this answer to make it work https://stackoverflow.com/a/61385725
gui.spec contains a section which explicitly asks to copy this library to the "compiled" folder.
More on why this library is not copied by default -> https://bit.ly/3ydB7WT

Below are shown the contents of my `gui.spec` file.
```
# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import copy_metadata
block_cipher = None

extra_files = [( 'resources\\*.json', 'resources' ),
               ( '.env', '.')]
extra_files += copy_metadata('google-api-python-client')

a = Analysis(['src\\stream_live_chat_gui\\main.py'],
             pathex=['D:\\code_projects\\python\\stream_live_chat_gui'],
             binaries=[],
             datas=extra_files,
             hiddenimports=[],
             hookspath=[],
             runtime_hooks=[],
             excludes=[],
             win_no_prefer_redirects=False,
             win_private_assemblies=False,
             cipher=block_cipher,
             noarchive=False)
```

## How to use

### How the application works
The application stores messages, polled using the google youtube api for a live chat transmission, in an sqlite dabase 
locally using sqlalchemy. It uses a keyword ( in the .env file) to filter for the messages that are target of being 
stored in the local database.
It also creates the next files:
- BANNER_FILENAME = "banner_control.txt"
- LIVE_CHAT_RECORD_FILENAME = "live_chat_record.txt"
- ACTUAL_START_TIMESTAMP_ADJUSTED_QUESTIONS_TIMESTAMP_FILENAME = "actual_timestamp_replied_questions.txt"
- LOG_FILE = "stream_live_chat.log"

#### Banner control file
If you want to show your audience any message during your stream.
Needs setup in OBS to send the information through a video stream.

#### Live chat record
Stores all messages exchanged in the chat window of a live video session.

#### Actual timestamp replied questions
Stores messages that were grabbed from the live chat session and stored in the database. It marks them with the 
timestamp on which the message was grabbed from the database and read by the host (of the livestream) to interact with 
it i.e. the timestamp of when the host had interaction (read it for the audience) with a message.

#### Log File
Logs all events related to the application.

### How to Authenticate the application
General knowledge on the authentication types for the client:
https://developers.google.com/youtube/registering_an_application

This application uses oauth 2.0 for authentication, follow this guide to get creds.
https://developers.google.com/youtube/v3/guides/auth/server-side-web-apps
After following the guides above, you will get a json file that contains the credentials to be used for authenticating 
the client to the youtube API.

The only advantage of using OAuth over regular API keys is the fact that you can test the application using unlisted
videos (basically, private videos). This is how it's build for this case. But it can totally work with only API keys


### App control (using .env file)
The application uses an .env file to control different aspects, such as the .db filename that gets created everytime 
the application runs or the control word which is used to filter out which messages out of the youtube livechat are the 
ones that are stored in the database.

```
### Database related variables
DATABASE_NAME = "youtube_questions.db"
# The next variable determines which messages from the live chat are stored in the database, use lower case
CHAT_FILTER_WORD = "#pregunta"

### Text files control variables
BANNER_FILENAME = "banner_control.txt"
YOUTUBE_COMMENT_MAX_LENGTH = "5000"
QUESTION_LOOKUP_WEBPAGE = "https://somelink.com"
LIVE_CHAT_RECORD_FILENAME = "live_chat_record.txt"
ACTUAL_START_TIMESTAMP_ADJUSTED_QUESTIONS_TIMESTAMP_FILENAME = "actual_timestamp_replied_questions.txt"

# Youtube Channel related variables
# used when adding questions manually through the gui
YOUTUBER_NAME = "SOME NAME"
YOUTUBE_CHANNEL_ID = "<SOME_YOUTUBE_CHANNEL_ID>"
# Set this variable to either yes or no, if another value is set it will error out.
# Set to "no" when using unlisted videos (youtube) and "yes" when going to a public live video
PRIVATE_TESTING="no"
# NOT STRICTLY necessary, used in case of testing with unlisted videos in case the api can't grab the video id by itself
LIVE_VIDEO_ID="<SOME_LIVE_VIDEO_ID>"
# The upper limit (questions number) a user can submit per stream
QUESTIONS_LIMIT="4"
# Message that shows up together with the start of the video timestamp (00:00:00)
TOP_MESSAGE_OF_TIMESTAMP_FILE="Start of stream"


### Youtube API creds related config:
# The cred files (*.json) should be inside the `resources` directory
CLIENT_SECRETS_FILE = "client_secret.json"
TOKEN_FILE = "token.pickle"
CREDS_AUTH_PORT = "8080"

### Log
LOG_FILE = "stream_live_chat.log"
```