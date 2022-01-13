from youtube_dl import YoutubeDL
from youtube_dl.utils import format_bytes
from PyQt5.Qt import *
from PyQt5.QtGui import *
from PyQt5.QtCore import *
from PyQt5.QtWidgets import *
from PyQt5.QtWebEngineWidgets import QWebEnginePage, QWebEngineSettings
from PyQt5.uic import loadUi


import pickle
import os
import sys
from urllib.parse import urlparse

from google_auth_oauthlib.flow import Flow, InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload, MediaIoBaseDownload
from google.auth.transport.requests import Request


class YDL(YoutubeDL):
    def list_formats(self, info_dict):
        formats = info_dict.get('formats', [info_dict])
        videos = []
        audios = []
        for f in formats:
            if f.get('vcodec') == 'none':
                audios.append([f['format_id'], self.format_resolution(f), self.file_size(f), f['ext'], self._format_note(f)])
            else:
                videos.append([f['format_id'], self.format_resolution(f), self.file_size(f), f['ext'], self._format_note(f)])
        return videos, audios

    def _format_note(self, fdict):
        res = ''
        if fdict.get('ext') in ['f4f', 'f4m']:
            res += '(unsupported) '
        if fdict.get('format_note') is not None:
            res += fdict['format_note'] + ' '
        if fdict.get('tbr') is not None:
            res += '%4dk ' % fdict['tbr']
        if (fdict.get('vcodec') is not None
                and fdict.get('vcodec') != 'none'):
            if res:
                res += ', '
            res += fdict['vcodec']
            if fdict.get('vbr') is not None:
                res += '@'
        elif fdict.get('vbr') is not None and fdict.get('abr') is not None:
            res += 'video@'
        if fdict.get('vbr') is not None:
            res += '%4dk' % fdict['vbr']
        if fdict.get('fps') is not None:
            if res:
                res += ', '
            res += '%sfps' % fdict['fps']
        if fdict.get('acodec') is not None:
            if res:
                res += ', '
            if fdict['acodec'] == 'none':
                res += 'video only'
            else:
                res += '%-5s' % fdict['acodec']
        elif fdict.get('abr') is not None:
            if res:
                res += ', '
            res += 'audio'
        if fdict.get('abr') is not None:
            res += '@%3dk' % fdict['abr']
        if fdict.get('asr') is not None:
            res += ' (%5dHz)' % fdict['asr']
        return res

    def file_size(self, fdict):
        res = ''
        if fdict.get('filesize') is not None:
            res += format_bytes(fdict['filesize'])
        elif fdict.get('filesize_approx') is not None:
            res += '~' + format_bytes(fdict['filesize_approx'])
        return res

    @staticmethod
    def format_resolution(format):
        if format.get('vcodec') == 'none':
            return 'audio only'
        if format.get('height') is not None:
            return '%s' % format['height']
        elif format.get('resolution') is not None:
            return format['resolution']
        else:
            return 'unknown'


class MyLogger(object):
    def __init__(self, main_window):
        self.main_window = main_window

    def debug(self, msg):
        if 'Downloading' in msg and 'webpage' in msg:
            self.main_window.import_tab.textBrowser.append(msg)
            QApplication.instance().processEvents()

    def warning(self, msg):
        pass

    def error(self, msg):
        self.main_window.sig_error.emit(msg)


class API(object):
    order_dict = {'Relevance': 'relevance', 'View Counts': 'viewCount', 'Date': 'date', 'Rating': 'rating'}
    
    def __init__(self, main_window):
        self.main_window = main_window
        self.logger = MyLogger(main_window)
        ydl_opts = {
            'ignoreerrors': True,
            'default_search': 'auto',
            'logger': self.logger,
        }
        if int(self.main_window.settings.value('proxyChecked')) == 2:
            ydl_opts['proxy'] = self.main_window.settings.value('proxy')
        self.ydl = YDL(ydl_opts)

        self.Create_Service()

    def Create_Service(self):
        CLIENT_SECRET_FILE = 'client.json'
        API_SERVICE_NAME = 'youtube'
        API_VERSION = 'v3'
        SCOPES = ['https://www.googleapis.com/auth/youtube']

        cred = None

        pickle_file = f'token_{API_SERVICE_NAME}_{API_VERSION}.pickle'

        if os.path.exists(pickle_file):
            with open(pickle_file, 'rb') as token:
                cred = pickle.load(token)

        try:
            if not cred or not cred.valid:
                if cred and cred.expired and cred.refresh_token:
                    cred.refresh(Request())
                else:
                    flow = InstalledAppFlow.from_client_secrets_file(CLIENT_SECRET_FILE, SCOPES)
                    cred = flow.run_local_server()

            with open(pickle_file, 'wb') as token:
                pickle.dump(cred, token)
            self.youtube = build(API_SERVICE_NAME, API_VERSION, credentials=cred)
            self.API_type = 'OAuth'

        except Exception as e:
            try:
                f = open('api_key.txt', 'r')
                api_key = f.readline()
                f.close()
                # Create an API object with the API key
                self.youtube = build(API_SERVICE_NAME, API_VERSION, developerKey=api_key)
                self.API_type = 'APIkey'

            except:
                self.API_type = 'None'
                return

    def importlink(self, link):
        html = ''
        if 'www.youtube.com/c' in link or 'www.youtube.com/user/' in link:
            html = self.channelLists(link)
        elif 'www.youtube.com/' in link and 'list=' in link:
            html = self.playLists(link)
        elif link not in self.main_window.downloadVideos.videos:
            info = self.ydl.extract_info(link, download=False)
            if not info:
                return
            html = self.renderResults([info], info.get('title'), 3)
        self.main_window.search_tab.show_html(html)

    def searchResults(self, query, maxResults=5, order='relevance'):
        """
        Args:
        - query: search keywords.
        - maxResults (optional): maxResults to be included, defaults to 5.
        - order (optional): default is 'relevance', other options include 'viewCounts', 'date', 'rating', 'title'.
        """

        maxResults = self.main_window.maxResults.value()
        order = self.order_dict[self.main_window.order.currentText()]
        if self.API_type != 'None':
            search_results = self.youtube.search().list(q=query, part='id', maxResults=maxResults, order=order, type='video').execute()['items']

            entries = []
            for result in search_results:
                id = result['id']['videoId']
                entries.append(self.prepareAPIentry(id))
        else:
            entries = self.ydl.extract_info(query, download=False)['entries']
        html = self.renderResults(entries, query, 0)

        return html

    def channelLists(self, channelId):
        """
        Args:
        - channelId: the id of the channel
        """
        if channelId.find('https://www.youtube.com/channel/') == -1:
            channelId = 'https://www.youtube.com/channel/' + channelId
        channel_info = self.ydl.extract_info(channelId, download=False)
        entries = channel_info['entries']
        html = self.renderResults(entries, channel_info['title'], 1)

        return html

    def playLists(self, playlistId):
        """
        Args:
        - playlistId: the id of the playlist
        """
        if playlistId.find('list=')>0:
            playlistId = playlistId[playlistId.find('list=')+5:]

        if self.API_type != 'None':
            response = self.youtube.playlists().list(part='snippet', id=playlistId).execute()
            title = response['items'][0]['snippet']['title']

            entries = []
            response = self.youtube.playlistItems().list(
                part='contentDetails',
                playlistId=playlistId,
                maxResults=50
            ).execute()
            for item in response['items']:
                id = item['contentDetails']['videoId']
                entries.append(self.prepareAPIentry(id))

            nextPageToken = response.get('nextPageToken')
            while nextPageToken:
                response = self.youtube.playlistItems().list(
                    part='contentDetails',
                    playlistId=playlistId,
                    maxResults=50,
                    pageToken=nextPageToken
                ).execute()

                for item in response['items']:
                    id = item['contentDetails']['videoId']
                    entries.append(self.prepareAPIentry(id))

                nextPageToken = response.get('nextPageToken')

        else:
            playlist_info = self.ydl.extract_info(playlistId, download=False)
            title = playlist_info['title']
            entries = playlist_info['entries']

        html = self.renderResults(entries, title, 2)

        return html

    def prepareAPIentry(self, id):
        url = 'https://www.youtube.com/watch?v=' + id
        snippet = self.youtube.videos().list(part='snippet', id=id).execute()['items'][0]['snippet']
        statistics = self.youtube.videos().list(part='statistics', id=id).execute()['items'][0]['statistics']
        entry = {'id': id,
                 'webpage_url': url,
                 'title': snippet['title'],
                 'thumbnail': snippet['thumbnails']['high']['url'],
                 'view_count': statistics['viewCount'],
                 'like_count': statistics['likeCount']}
        return entry

    def renderResults(self, entries, heading, type_id):
        """
        Args:
        - entries: the extracted info returned by youtube-dl.

        Parses the extracted information into desired format.
        """

        html = '<h1>' + str(heading) + '</h1>'

        heading_item = StandardItem(heading, set_bold=True)
        self.main_window.allVideos.model().item(type_id).appendRow(heading_item)
        idx = self.main_window.allVideos.model().item(type_id).rowCount() - 1
        node = self.main_window.allVideos.model().item(type_id).child(idx)

        for (i, info) in enumerate(entries):
            if info is None:
                continue
            link = info['webpage_url']

            entry = """<figure><a href='{}' target='_blank'><figcaption>{}</figcaption><img src='{}' title='{}'/></a><figcaption>views: {}, likes: {}</figcaption></figure>""".format(link, info.get('title'), info.get('thumbnail'), link, info.get('view_count'), info.get('like_count'))

            info['thumbnail_entry'] = entry
            if type_id > 0 or i < int(self.main_window.settings.value('searchAppend')):
                self.main_window.allVideos.importvideo(link, node, info, append=True)
            else:
                self.main_window.allVideos.importvideo(link, node, info, append=False)

            html += entry

        return html


class WebEnginePage(QWebEnginePage):
    """This is to open new tabs in default browser"""

    def createWindow(self, _type):
        page = WebEnginePage(self)
        page.urlChanged.connect(self.open_browser)
        return page

    def open_browser(self, url):
        page = self.sender()
        QDesktopServices.openUrl(url)
        page.deleteLater()


class StandardItemModel(QStandardItemModel):
    """This emits a signal when a checkbox status is changed"""
    itemDataChanged = pyqtSignal(object, object)

    def setData(self, index, value, role=Qt.CheckStateRole):
        oldvalue = index.data(role)
        result = super(StandardItemModel, self).setData(index, value, role)
        if result and value != oldvalue:
            self.itemDataChanged.emit(self.itemFromIndex(index), role)
        return result


class StandardItem(QStandardItem):
    """Define the standard items entry for the QTreeView and QListView in our program"""

    def __init__(self, txt='', info=None, font_size=9, set_bold=False, color=QColor(0, 0, 0)):
        super().__init__()

        font = QFont('Arial', font_size)
        font.setBold(set_bold)

        self.setEditable(False)
        self.setForeground(color)
        self.setFont(font)
        self.setText(txt)
        self.info = info
        if info is not None:
            self.setToolTip(info.get('title'))
        self.video_streams = {}
        self.video_streams = set()
        self.audio_streams = {}
        self.audio_streams = set()


class rootWidgetItem(QTreeWidgetItem):
    def __lt__(self, other):
        return False


class TreeWidgetItem(QTreeWidgetItem):
    def __lt__(self, other):
        column = self.treeWidget().sortColumn()
        if column <= 1:
            if self.text(column) == 'unknown' or self.text(column) == 'audio only':
                return True
            return int(self.text(column)) < int(other.text(column))
        else:
            return self.text(column) < other.text(column)
    

def resize(widget):
    width = widget.parent().geometry().width() - 20
    height = widget.parent().geometry().height() - 40
    widget.setGeometry(QRect(10, 20, width, height))


class AllVideos(QTreeView):
    """The all videos view box is based on the QTreeView class"""

    def __init__(self, main_window, parent=None):
        super().__init__(parent)
        self.main_window = main_window
        resize(self)
        self.setFrameShape(QFrame.NoFrame)
        self.setHeaderHidden(True)
        treeModel = StandardItemModel()
        rootNode = treeModel.invisibleRootItem()
        search = StandardItem('General Search', font_size=10, set_bold=True)
        channel = StandardItem('Channel Playlists', font_size=10, set_bold=True)
        playlist = StandardItem('Playlists', font_size=10, set_bold=True)
        others = StandardItem('Imported Links', font_size=10, set_bold=True)
        rootNode.appendRow(search)
        rootNode.appendRow(channel)
        rootNode.appendRow(playlist)
        rootNode.appendRow(others)
        self.setModel(treeModel)
        treeModel.itemDataChanged.connect(self.tickbox)
        self.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.setDragEnabled(True)
        self.doubleClicked.connect(self.main_window.download_tab.showVideo)
        self.videos = []

    def tickbox(self, item, role):
        self.setCurrentIndex(item.index())
        downloads = self.main_window.downloadVideos
        if role == Qt.CheckStateRole:
            if item.checkState() == 0:
                item.setForeground(QColor(128, 128, 128))
                for i in range(downloads.model().rowCount()):
                    if downloads.model().item(i).text() == item.text():
                        downloads.model().removeRow(i)
                        downloads.videos.remove(item.text())
                        return
            else:
                item.setForeground(QColor(0, 0, 0))
                downloads.model().appendRow([StandardItem(item.text(), info=item.info)])
                downloads.videos.add(item.text())

    def importvideo(self, link, node, info, append=True):
        for video in self.videos:
            if video.data(2) == link:
                video.model().setData(video, 2, Qt.CheckStateRole)
                return
        s = StandardItem(link, info=info)
        s.setCheckable(True)
        if append:
            self.main_window.downloadVideos.model().appendRow([StandardItem(link, info=info)])
            self.main_window.downloadVideos.videos.add(link)
            s.setCheckState(2)
        else:
            s.setForeground(QColor(128, 128, 128))
            s.setCheckState(0)

        node.appendRow([s])
        idx = node.rowCount() - 1
        self.videos.append(node.child(idx).index())
        self.expandAll()

    def contextMenuEvent(self, event):
        contextMenu = QMenu(self)
        checkSelected  = contextMenu.addAction("Check Selected")
        uncheckSelected = contextMenu.addAction("UnCheck Selected")
        checkAll = contextMenu.addAction("Check All Children")
        uncheckAll = contextMenu.addAction("UnCheck All Children")
        action = contextMenu.exec_(self.mapToGlobal(event.pos()))

        if action == checkSelected:
            selection = self.selectedIndexes()
            for entry in selection:
                if entry.data(Qt.CheckStateRole) is not None:
                    entry.model().setData(entry, 2, Qt.CheckStateRole)
            self.clearSelection()
            for entry in selection:
                self.selectionModel().select(entry, QItemSelectionModel.Select)

        if action == uncheckSelected:
            selection = self.selectedIndexes()
            for entry in selection:
                if entry.data(Qt.CheckStateRole) is not None:
                    entry.model().setData(entry, 0, Qt.CheckStateRole)
            self.clearSelection()
            for entry in selection:
                self.selectionModel().select(entry, QItemSelectionModel.Select)

        if action == checkAll:
            selection = self.selectedIndexes()
            for entry in selection:
                children = []
                self.getChildren(children, entry)
                for child in children:
                    if child.data(Qt.CheckStateRole) is not None:
                        child.model().setData(child, 2, Qt.CheckStateRole)
            self.clearSelection()
            for entry in selection:
                self.selectionModel().select(entry, QItemSelectionModel.Select)

        if action == uncheckAll:
            selection = self.selectedIndexes()
            for entry in selection:
                children = []
                self.getChildren(children, entry)
                for child in children:
                    if child.data(Qt.CheckStateRole) is not None:
                        child.model().setData(child, 0, Qt.CheckStateRole)
            self.clearSelection()
            for entry in selection:
                self.selectionModel().select(entry, QItemSelectionModel.Select)

    def getChildren(self, children, entry):
        childCount = entry.model().rowCount(entry)
        for i in range(childCount):
            children.append(entry.child(i, 0))
            self.getChildren(children, entry.child(i, 0))

    


class DownloadVideos(QListView):
    """The download videos view box is based on the QListView class"""

    def __init__(self, main_window, parent=None):
        super().__init__(parent)
        self.main_window = main_window
        resize(self)
        self.setFrameShape(QFrame.NoFrame)
        model = QStandardItemModel()
        self.setModel(model)
        self.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.setAcceptDrops(True)
        self.setProperty("showDropIndicator", True)
        self.setDefaultDropAction(Qt.MoveAction)
        # self.setDragEnabled(True)
        self.doubleClicked.connect(self.main_window.download_tab.showVideo)
        self.videos = {}
        self.videos = set()

    def dragEnterEvent(self, event):
        event.accept()

    def dragMoveEvent(self, event):
        event.accept()

    def dropEvent(self, event):
        event.accept()
        if event.source() == self.main_window.search_tab.webEngineView:
            # drag from search tab
            link = event.mimeData().html()
            idx = link.find('https://www.youtube.com/watch?v=')
            link = link[idx:-2]
            if link not in self.videos:
                for entry in self.main_window.allVideos.videos:
                    if link == entry.data():
                        entry.model().setData(entry, 2, Qt.CheckStateRole)
        elif event.mimeData().hasText():
            # drag from an external browser or texts
            idx = self.main_window.tab_manager.currentIndex()
            self.main_window.tab_manager.setCurrentIndex(2)
            for link in event.mimeData().text().splitlines():
                self.main_window.API.importlink(link)
            self.main_window.tab_manager.setCurrentIndex(idx)
        else:
            # drag from allVideos Tree View
            for entry in event.source().selectedIndexes():
                if entry.data(Qt.CheckStateRole) is not None:
                    entry.model().setData(entry, 2, Qt.CheckStateRole)

    def delete(self):
        entries = [entry.data() for entry in self.selectedIndexes()]
        for entry in entries:
            for video in self.main_window.allVideos.videos:
                if entry == video.data(2):
                    video.model().setData(video, 0, Qt.CheckStateRole)

    def contextMenuEvent(self, event):
        contextMenu = QMenu(self)
        paste = contextMenu.addAction("Paste Link")
        delete = contextMenu.addAction("Delete Selected")
        deleteAll = contextMenu.addAction("Delete All")
        download = contextMenu.addAction("Download Selected")
        downloadAll = contextMenu.addAction("Download All")
        stopDownload = contextMenu.addAction("Stop Downloads")
        action = contextMenu.exec_(self.mapToGlobal(event.pos()))
        if action == paste:
            self.main_window.paste()
        if action == delete:
            self.delete()
        if action == deleteAll:
            self.selectAll()
            self.delete()
        if action == download:
            self.main_window.download_tab.download()
        if action == downloadAll:
            self.main_window.download_tab.downloadAll()
        if action == stopDownload:
            self.main_window.download_tab.abort_workers()
            

# def ffmpeg_operations(output, audio, video=None):
#     output = '"' + output + '"'
#     audio = '"' + audio + '"'
#     if not video:
#         os.system('ffmpeg -y -i ' + audio + ' -vn -sn -c:a mp3 -ab 128k ' + output)
#         os.remove(audio[1:-1])
#     else:
#         video = '"' + video + '"'
#         os.system('ffmpeg -y -i ' + video + ' -i ' + audio + ' -c:v copy -c:a aac ' + output)
#         os.remove(audio[1:-1])
#         os.remove(video[1:-1])
