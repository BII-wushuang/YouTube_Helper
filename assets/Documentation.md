# YouTube Helper

A GUI wrapper for [YouTube-dl](https://github.com/ytdl-org/youtube-dl).

### Functionalities:
- Perform YouTube searches
- Drag and Drop or Paste (Ctrl+V) into the GUI to import links
- Supported site links follow that of [YouTube-dl](https://ytdl-org.github.io/youtube-dl/supportedsites.html)
- Select streams for downloading
- Import videos into playlists / create playlists (requires [Google OAuth 2.0](#google-oauth))

### Python Prerequisites

Install Python prerequisites via the following command:

```pip install -r requirements.txt```

### FFMPEG Post Processing

For postprocessing such as merging of DASH audios and videos or converting to other formats,

the [ffmpeg](https://ffmpeg.org/) libraries will be required.

- For Windows, download from the following link:

[Download FFmpeg](https://www.ffmpeg.org/download.html#build-windows)

and either extract ffmpeg.exe to this folder or add to path

- For MacOS, install via brew:

```brew install ffmpeg```

- For Ubuntu, install via apt-get:

```sudo apt install ffmpeg```

### Quick Start
Run the program via
```python main.py```

If you prefer to compile the python script into an executable,

```pyinstaller --clean --onefile pyinstaller.spec```

### YouTube API Key

In order to perform YouTube searches, please obtain an API Key for the YouTube Data API as follows:

1. Go to https://console.developers.google.com/ and create a project under your Google account.
2. Click on the ```+ Enable API and Servies``` link.
3. Select the ```YouTube Data API v3``` and enable this API.
4. Click on ```Create credentials``` and create an API Key.
5. Save your API Key into ```api_key.txt``` in this folder.

### Google OAuth

To operate on your playlists, please activate the Google OAuth 2.0 Services:

1. Go to https://console.developers.google.com/ and create a project under your Google account.
2. Click on the ```+ Enable API and Servies``` link.
3. Select the ```YouTube Data API v3``` and enable this API.
4. Click on ```Create credentials``` and create an OAuth 2.0 Client ID.
5. Save your OAuth 2.0 client as ```client.json``` in this folder.
