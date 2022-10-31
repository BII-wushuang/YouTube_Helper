from utils import *
from youtube_dl.postprocessor.common import PostProcessor
from youtube_dl.utils import encodeArgument, PostProcessingError
import subprocess
import os
from shutil import move


class AudioPP(PostProcessor):
    def run(self, information):
        directory, filename = os.path.split(information['filepath'])
        if directory == '':
            directory = os.getcwd()
        outfile = os.path.join(directory, filename)
        print(outfile)
        tempfile = os.path.join(os.getcwd(), 'temp.mp3')
        command = f'ffmpeg -i "{outfile}" -acodec copy {tempfile} -y'
        retCode = subprocess.call(encodeArgument(command), shell=True)
        if retCode != 0:
            raise PostProcessingError(
                'Command returned error code %d' % retCode)
        move(tempfile, outfile)
        return [], information


class MyLogger(object):
    def __init__(self, download_manager):
        self.download_manager = download_manager

    def debug(self, msg):
        if '[ffmpeg]' in msg:
            if 'Destination' in msg:
                idx = msg.find('Destination')
                msg = msg[:idx] + '\n' + msg[idx:]
            if 'Merging formats into' in msg:
                msg = msg[:30] + '\n' + msg[30:]
            self.download_manager.sig_msg.emit(msg)
        elif 'Deleting' in msg:
            self.download_manager.sig_msg.emit('Deleting Originals')
        else:
            pass

    def warning(self, msg):
        pass

    def error(self, msg):
        if msg == 'ERROR: requested format not available':
            pass
        elif 'ERROR: unable to download video data' in msg:
            pass
        else:
            self.download_manager.sig_error.emit(msg)


class DownloadManager(QObject):
    """
    The Download Manager will be initiated as a new QThread worker consisting of the YouTube-dl objects.
    The signals emitted will be relayed back to the main GUI.
    """
    sig_msg = pyqtSignal(str)
    sig_item = pyqtSignal(QStandardItem)
    sig_tProgress = pyqtSignal(int)
    sig_dProgress = pyqtSignal(int)
    sig_error = pyqtSignal(str)
    sig_done = pyqtSignal(int)

    def __init__(self, download_tab):
        super().__init__()
        self.__abort = False
        self.download_tab = download_tab
        self.main_window = self.download_tab.main_window

        self.logger = MyLogger(self)

        # Settings to format the downloader options
        self.proxy = self.main_window.settings.value('proxy') if int(self.main_window.settings.value('proxyChecked')) == 2 else None
        self.outtmpl = os.path.join(self.main_window.settings.value('directory'), self.main_window.settings.value('output'))
        self.nooverwrites = False if int(self.main_window.settings.value('overwrite')) == 2 else True
        self.writesubtitles = True if int(self.main_window.settings.value('writesubtitles')) == 2 else False
        self.writeautomaticsub = True if int(self.main_window.settings.value('writeautomaticsub')) == 2 else False
        self.subtitleslangs = self.main_window.settings.value('subtitleslangs')
        if type(self.subtitleslangs) == str:
            self.subtitleslangs = self.subtitleslangs.split(', ')
        if 'zh' in self.subtitleslangs:
            self.subtitleslangs.append('zh-Hans')
            self.subtitleslangs.append('zh-Hant')
        self.keepvideo = True if int(self.main_window.settings.value('keepFiles')) == 2 else False
        self.video_postprocessor = [{'key': 'FFmpegVideoConvertor', 'preferedformat': self.main_window.settings.value('preferredVideos')}] if int(self.main_window.settings.value('convertFormats')) == 2 else None
        self.audio_postprocessor = [{'key': 'FFmpegExtractAudio', 'preferredcodec': self.main_window.settings.value('preferredAudios')}] if int(self.main_window.settings.value('convertFormats')) == 2 else None

        self.default_opts = """{
            'proxy': self.proxy,
            'outtmpl': self.outtmpl,
            'format': 'best',
            'postprocessors': self.video_postprocessor,
            'keepvideo': self.keepvideo,
            'writesubtitles': self.writesubtitles,
            'writeautomaticsub': self.writeautomaticsub,
            'subtitleslangs': self.subtitleslangs,
            'logger': self.logger,
            'progress_hooks': [self.progress_hook],
            'nooverwrites': self.nooverwrites,
        }"""
        self.default_downloader = YDL(eval(self.default_opts))

        video_opts = eval(self.default_opts)
        video_opts['format'] = 'bestvideo+bestaudio'
        video_opts['postprocessors'] = [{'key': 'FFmpegMerger'}]
        video_opts['merge_output_format'] = self.main_window.settings.value('preferredVideos')
        self.ydl_video = YDL(video_opts)

        audio_opts = eval(self.default_opts)
        audio_opts['format'] = 'bestaudio/best'
        audio_opts['postprocessors'] = self.audio_postprocessor
        self.ydl_audio = YDL(audio_opts)

        self.ydl = []
        selection = self.main_window.Stream.currentText()

        if selection == 'Best Quality (Merge)':
            self.ydl.append(self.ydl_video)

        if selection == 'Best Quality (Separate)':
            self.ydl.append(self.ydl_video)
            self.ydl.append(self.ydl_audio)

        if selection[-1] == 'p':
            ydl_opts = eval(self.default_opts)
            ydl_opts['format'] = 'best[height<={}]'.format(selection[-4:-1])
            downloader = YDL(ydl_opts)
            self.ydl.append(downloader)

        if selection == 'Audio Only':
            self.ydl_audio.add_post_processor(AudioPP(None))
            self.ydl.append(self.ydl_audio)

    def download(self, downloader, link):
        incomplete = True
        while incomplete:
            try:
                downloader.download([link])
                incomplete = False
            except Exception as e:
                if 'ERROR: unable to download video data' in str(e):
                    pass
                else:
                    raise e

    def start_downloader(self):
        for (i, idx) in enumerate(self.main_window.downloadVideos.selectedIndexes()):
            self.sig_tProgress.emit(i)
            item = idx.model().itemFromIndex(idx)
            self.sig_item.emit(item)

            outtmpl = self.outtmpl
            if '%(format_id)s' not in outtmpl:
                idx = outtmpl.find('.%(ext)s')
                outtmpl = outtmpl[:idx] + ' - %(format_id)s.%(ext)s'

            if len(item.video_streams) > 0:
                format = ''
                for stream in item.video_streams:
                    format += stream + ','
                format = format[:-1]

                video_opts = eval(self.default_opts)
                video_opts['format'] = format
                video_opts['outtmpl'] = outtmpl
                video_ydl = YDL(video_opts)
                self.download(video_ydl, item.text())

            if len(item.audio_streams) > 0:
                format = ''
                for stream in item.audio_streams:
                    format += stream + ','
                format = format[:-1]

                audio_opts = eval(self.default_opts)
                audio_opts['format'] = format
                audio_opts['outtmpl'] = outtmpl
                audio_opts['postprocessors'] = self.audio_postprocessor
                audio_ydl = YDL(audio_opts)
                self.download(audio_ydl, item.text())

            if len(item.video_streams) > 0 or len(item.audio_streams) > 0:
                break

            try:
                for downloader in self.ydl:
                    self.download(downloader, item.text())
            except Exception as e:
                if str(e) == 'ERROR: requested format not available':
                    self.download(self.default_downloader, item.text())

        self.sig_dProgress.emit(0)
        self.sig_tProgress.emit(len(self.main_window.downloadVideos.selectedIndexes()))
        self.sig_done.emit(0)

    def progress_hook(self, d):
        if d['status'] == 'finished':
            file_tuple = os.path.split(os.path.abspath(d['filename']))
            self.sig_msg.emit('Finished downloading {}'.format(file_tuple[1]))
        if d['status'] == 'downloading':
            p = d['_percent_str']
            p = p.replace('%', '')
            self.sig_dProgress.emit(float(p))
            self.sig_msg.emit('Downloading {} \n Speed: {}, ETA: {}'.format(d['filename'], d['_speed_str'], d['_eta_str']))

    def abort(self):
        if self.__abort:
            return
        self.sig_msg.emit('Aborting Downloads')
        self.__abort = True


class DownloadTab(QWidget):
    display_name = 'Download'
    threads = []

    def __init__(self, main_window):
        super().__init__(main_window)
        QThread.currentThread().setObjectName('download_tab')
        self.main_window = main_window
        self.main_window.download_tab = self
        self.init_ui()
        # self.webEngineView.page().setBackgroundColor(Qt.transparent)
        self.show()

    def init_ui(self):
        if hasattr(sys, "_MEIPASS"):
            datadir = os.path.join(sys._MEIPASS, 'tabs/download.ui')
        else:
            datadir = 'tabs/download.ui'
        loadUi(datadir, self)
        self.webEngineView.setPage(WebEnginePage(self.webEngineView))
        self.webEngineView.settings().setAttribute(QWebEngineSettings.FullScreenSupportEnabled, True)
        self.page = self.webEngineView.page()
        self.page.fullScreenRequested.connect(self.toggleFullScreen)
        self.webEngineView.exitFullScreen = QShortcut(QKeySequence(Qt.Key_Escape), self.webEngineView)
        self.webEngineView.exitFullScreen.activated.connect(self.exitFullScreen)
        self.Streams.sortByColumn(1, Qt.DescendingOrder)
        self.Streams.itemChanged.connect(self.tickbox)

    def toggleFullScreen(self, request):
        if request.toggleOn():
            request.accept()
            self.webViewLayout.removeWidget(self.webEngineView)
            self.webEngineView.setParent(None)
            self.webEngineView.showFullScreen()
        else:
            request.accept()
            self.webEngineView.setGeometry(QRect(int((self.geometry().width()-800)/2), 0, 784, 434))
            self.webViewLayout.addWidget(self.webEngineView)
            QApplication.setActiveWindow(self.main_window)
            self.webEngineView.setFocus()
            widget = QApplication.focusObject()
            print(widget)

    def exitFullScreen(self):
        self.webEngineView.triggerPageAction(self.page.ExitFullScreen)

    def start_worker(self):
        worker = DownloadManager(self)
        worker.sig_msg.connect(self.textDisplay.setText)
        worker.sig_item.connect(self.showStreams)
        worker.sig_item.connect(self.showThumbnail)
        worker.sig_tProgress.connect(self.update_total)
        worker.sig_dProgress.connect(self.downloadProgress.setValue)
        worker.sig_error.connect(self.main_window.show_error)
        worker.sig_done.connect(self.on_worker_done)

        thread = QThread()
        self.threads.append((thread, worker))
        worker.moveToThread(thread)

        self.main_window.downloadBtn.setEnabled(False)
        self.main_window.downloadAllBtn.setEnabled(False)

        thread.started.connect(worker.start_downloader)
        thread.start()

    def download(self):
        self.main_window.tab_manager.setCurrentIndex(1)
        self.totalProgress.setMaximum(len(self.main_window.downloadVideos.selectedIndexes()))
        QApplication.instance().processEvents()
        self.start_worker()

    def downloadAll(self):
        self.main_window.downloadVideos.selectAll()
        self.download()

    def update_total(self, i):
        self.totalProgress.setFormat('{}/{}'.format(i, self.totalProgress.maximum()))

    def abort_workers(self):
        for thread, worker in self.threads:
            worker.abort()
            thread.quit()
            thread.wait()

    @pyqtSlot()
    def on_worker_done(self):
        self.textDisplay.setText('All downloads complete.')

        self.main_window.downloadBtn.setEnabled(True)
        self.main_window.downloadAllBtn.setEnabled(True)

    def showVideo(self, idx):
        item = idx.model().itemFromIndex(idx)
        info = item.info
        if info is None:
            return
        videoId = info.get('id')
        netloc = urlparse(info.get('webpage_url')).netloc
        myhtml = """<iframe width="784" height="434" src="https://{}/embed/{}" frameborder="0" allowfullscreen></iframe>""".format(netloc, videoId)

        self.webEngineView.setHtml(myhtml, QUrl("local"))
        self.main_window.tab_manager.setCurrentIndex(1)
        self.webEngineView.setFocus()

        if self.sender() == self.main_window.downloadVideos:
            self.showStreams(item)

    def showStreams(self, item):
        if self.Streams.topLevelItemCount() == 2:
            if self.video_streams.itemparent is item:
                return
            else:
                self.Streams.clear()

        self.video_streams = rootWidgetItem(self.Streams, ['Video'])
        self.audio_streams = rootWidgetItem(self.Streams, ['Audio'])
        self.video_streams.itemparent = item
        self.audio_streams.itemparent = item

        info = item.info
        if info.get('formats') is None:
            info = self.main_window.API.ydl.extract_info(info['webpage_url'], download=False)
        videos, audios = self.main_window.API.ydl.list_formats(info)
        for entry in videos:
            t = TreeWidgetItem(entry)
            if entry[0] in item.video_streams:
                t.setCheckState(0, 2)
            else:
                t.setCheckState(0, 0)
            self.video_streams.addChild(t)
        for entry in audios:
            t = TreeWidgetItem(entry)
            if entry[0] in item.audio_streams:
                t.setCheckState(0, 2)
            else:
                t.setCheckState(0, 0)
            t.setCheckState(0, 0)
            self.audio_streams.addChild(t)
        self.Streams.expandAll()

    def tickbox(self, item):
        if item.checkState(0) == 2:
            if item.text(1) == 'audio only':
                item.parent().itemparent.audio_streams.add(item.text(0))
            else:
                item.parent().itemparent.video_streams.add(item.text(0))
        else:
            if item.text(1) == 'audio only':
                item.parent().itemparent.audio_streams.remove(item.text(0))
            else:
                item.parent().itemparent.video_streams.remove(item.text(0))

    def showThumbnail(self, item):
        thumbnail = item.info['thumbnail_entry']
        header = """
        <!DOCTYPE html>
        <html>
        <head>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <meta name="description" content="">
        <meta name="author" content="">
        <style>
        h1 {
            text-align: center;
        }
        figure {
            display: inline-block;
            border: thin silver solid;
            width: 600px;
            height: 400px;
        }
        figcaption {
            text-align: center;
        }
        img {
            width: 600px; 
            float: left; 
        }
        </style>
        </head>

        <body>
        """

        footer = """
        </body>
        </html>
        """

        myhtml = header + thumbnail + footer
        self.webEngineView.setHtml(myhtml)
