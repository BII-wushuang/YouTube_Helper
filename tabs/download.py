from utils import *
from yt_dlp.postprocessor.common import PostProcessor
from yt_dlp.utils import encodeArgument, PostProcessingError, DownloadCancelled
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
    # yt-dlp logger interface: it funnels to_screen() through debug(),
    # report_warning() through warning(), report_error() through error().
    # Post-processor lines look like "[Merger] Merging formats into ...",
    # "[ExtractAudio] Destination: ...", "[VideoConvertor] ...".
    PP_TAGS = ('[Merger]', '[ExtractAudio]', '[VideoConvertor]', '[Fixup')

    def __init__(self, download_manager):
        self.download_manager = download_manager

    def debug(self, msg):
        if any(tag in msg for tag in self.PP_TAGS):
            for marker in ('Destination', 'Merging formats into', 'Converting'):
                idx = msg.find(marker)
                if idx > 0:
                    msg = msg[:idx] + '\n' + msg[idx:]
                    break
            self.download_manager.sig_msg.emit(msg)
        elif 'Deleting original file' in msg:
            self.download_manager.sig_msg.emit('Deleting Originals')

    def info(self, msg):
        self.debug(msg)

    def warning(self, msg):
        pass

    def error(self, msg):
        low = msg.lower()
        if 'requested format' in low and 'not available' in low:
            return
        if 'unable to download video data' in low:
            return
        self.download_manager.sig_error.emit(msg)


class DownloadManager(QObject):
    """
    The Download Manager will be initiated as a new QThread worker consisting of the YouTube-dl objects.
    The signals emitted will be relayed back to the main GUI.
    """
    sig_msg = pyqtSignal(str)
    # pyqtSignal(QStandardItem) cannot be delivered across threads (queued
    # connection) without registering the metatype; use object instead.
    sig_item = pyqtSignal(object)
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

        # Settings -> plain values used to build yt-dlp option dicts.
        s = self.main_window.settings
        self.proxy = s.value('proxy') if int(s.value('proxyChecked')) == 2 else None
        self.outtmpl = os.path.join(s.value('directory'), s.value('output'))
        self.nooverwrites = int(s.value('overwrite')) != 2
        self.writesubtitles = int(s.value('writesubtitles')) == 2
        self.writeautomaticsub = int(s.value('writeautomaticsub')) == 2

        langs = s.value('subtitleslangs')
        if isinstance(langs, str):
            langs = langs.split(',')
        langs = [l.strip() for l in langs if l.strip()]
        if 'zh' in langs:
            langs = langs + ['zh-Hans', 'zh-Hant']
        self.subtitleslangs = langs

        self.keepvideo = int(s.value('keepFiles')) == 2
        convert = int(s.value('convertFormats')) == 2
        self.preferred_video = s.value('preferredVideos')
        self.preferred_audio = s.value('preferredAudios')
        self.video_postprocessor = (
            [{'key': 'FFmpegVideoConvertor', 'preferedformat': self.preferred_video}]
            if convert else [])
        self.audio_postprocessor = (
            [{'key': 'FFmpegExtractAudio', 'preferredcodec': self.preferred_audio}]
            if convert else [])

        # Fallback used when a specifically requested format is unavailable.
        self.default_downloader = YDL(self.base_opts(
            fmt='best/bestvideo+bestaudio',
            postprocessors=self.video_postprocessor))

        # One downloader per "Default Stream" choice.
        self.ydl = []
        selection = self.main_window.Stream.currentText()

        if selection == 'Best Quality (Merge)':
            self.ydl.append(self.build_video_ydl())

        elif selection == 'Best Quality (Separate)':
            self.ydl.append(self.build_video_ydl())
            self.ydl.append(self.build_audio_ydl())

        elif selection.endswith('p') and selection[:-1].isdigit():
            h = selection[:-1]
            self.ydl.append(YDL(self.base_opts(
                fmt='bestvideo[height<=%s]+bestaudio/best[height<=%s]/best' % (h, h),
                postprocessors=self.video_postprocessor,
                merge_output_format=self.preferred_video)))

        elif selection == 'Audio Only':
            audio_ydl = self.build_audio_ydl()
            audio_ydl.add_post_processor(AudioPP(None))
            self.ydl.append(audio_ydl)

    def base_opts(self, fmt='best', postprocessors=None, **extra):
        """A fresh yt-dlp options dict; **extra overrides individual keys."""
        opts = {
            'proxy': self.proxy,
            'outtmpl': self.outtmpl,
            'format': fmt,
            'postprocessors': list(postprocessors or []),
            'keepvideo': self.keepvideo,
            'writesubtitles': self.writesubtitles,
            'writeautomaticsub': self.writeautomaticsub,
            'subtitleslangs': self.subtitleslangs,
            'logger': self.logger,
            'progress_hooks': [self.progress_hook],
            'nooverwrites': self.nooverwrites,
            'noprogress': True,
            'ignoreerrors': False,
        }
        opts.update(extra)
        return opts

    def build_video_ydl(self):
        # yt-dlp merges bestvideo+bestaudio automatically; just name the container.
        return YDL(self.base_opts(
            fmt='bestvideo+bestaudio/best',
            postprocessors=self.video_postprocessor,
            merge_output_format=self.preferred_video))

    def build_audio_ydl(self):
        return YDL(self.base_opts(
            fmt='bestaudio/best',
            postprocessors=self.audio_postprocessor))

    def download(self, downloader, link):
        for _ in range(3):
            if self.__abort:
                return
            try:
                downloader.download([link])
                return
            except DownloadCancelled:
                return
            except Exception as e:
                if 'unable to download video data' in str(e).lower():
                    continue
                raise

    def start_downloader(self):
        for (i, index) in enumerate(self.main_window.downloadVideos.selectedIndexes()):
            if self.__abort:
                break
            self.sig_tProgress.emit(i)
            item = index.model().itemFromIndex(index)
            self.sig_item.emit(item)

            # When specific streams are picked, tag the filename with the format
            # id so multiple picks for one video don't overwrite each other.
            outtmpl = self.outtmpl
            if '%(format_id)s' not in outtmpl:
                pos = outtmpl.find('.%(ext)s')
                if pos > 0:
                    outtmpl = outtmpl[:pos] + ' - %(format_id)s.%(ext)s'

            if len(item.video_streams) > 0:
                fmt = ','.join(item.video_streams)
                video_ydl = YDL(self.base_opts(
                    fmt=fmt, outtmpl=outtmpl,
                    postprocessors=self.video_postprocessor))
                self.download(video_ydl, item.text())

            if len(item.audio_streams) > 0:
                fmt = ','.join(item.audio_streams)
                audio_ydl = YDL(self.base_opts(
                    fmt=fmt, outtmpl=outtmpl,
                    postprocessors=self.audio_postprocessor))
                self.download(audio_ydl, item.text())

            if len(item.video_streams) > 0 or len(item.audio_streams) > 0:
                continue

            try:
                for downloader in self.ydl:
                    self.download(downloader, item.text())
            except Exception as e:
                if 'requested format not available' in str(e):
                    try:
                        self.download(self.default_downloader, item.text())
                    except Exception as e2:
                        self.sig_error.emit(str(e2))
                else:
                    self.sig_error.emit(str(e))

        self.sig_dProgress.emit(0)
        self.sig_tProgress.emit(len(self.main_window.downloadVideos.selectedIndexes()))
        self.sig_done.emit(0)

    def progress_hook(self, d):
        # This runs inside yt-dlp's download loop; yt-dlp does NOT guard against
        # exceptions raised here, so anything that throws aborts the download and
        # leaves a .part file behind. Compute everything from the raw numeric
        # fields (the '_*_str' fields are yt-dlp internals and carry terminal
        # formatting) and never let an error escape.
        if self.__abort:
            # yt-dlp documents this as the way to stop from a progress hook.
            raise DownloadCancelled('Aborted by user')
        try:
            status = d.get('status')
            if status == 'finished':
                name = os.path.basename(d.get('filename') or '')
                self.sig_msg.emit('Finished downloading {}'.format(name))
            elif status == 'downloading':
                total = d.get('total_bytes') or d.get('total_bytes_estimate')
                downloaded = d.get('downloaded_bytes') or 0
                percent = int(downloaded * 100 / total) if total else 0
                self.sig_dProgress.emit(max(0, min(100, percent)))

                speed = d.get('speed')
                speed_str = format_bytes(speed) + '/s' if speed else 'Unknown'
                eta = d.get('eta')
                eta_str = '{:d}:{:02d}'.format(int(eta) // 60, int(eta) % 60) if eta is not None else 'Unknown'
                self.sig_msg.emit('Downloading {} \n Speed: {}, ETA: {}'.format(
                    os.path.basename(d.get('filename') or ''), speed_str, eta_str))
        except Exception:
            pass

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
        videos, audios = self.main_window.API.ydl.split_formats(info)
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
