from yt_dlp import YoutubeDL
from yt_dlp.utils import format_bytes
from PyQt5.Qt import *
from PyQt5.QtGui import *
from PyQt5.QtCore import *
from PyQt5.QtWidgets import *
from PyQt5.QtWebEngineWidgets import QWebEnginePage, QWebEngineSettings
from PyQt5.uic import loadUi as _loadUi


import pickle
import os
import sys
from urllib.parse import urlparse

from google_auth_oauthlib.flow import Flow, InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload, MediaIoBaseDownload
from google.auth.transport.requests import Request


# ---------------------------------------------------------------------------
# Adaptive UI scaling + forced light theme.
#
# The .ui files were authored on Windows with 9/10 pt Arial and hard-coded
# pixel geometry. Elsewhere - especially macOS, where Qt uses 72 logical DPI
# instead of 96 - that renders ~25-40 % too small, and the hard-coded black
# item colours vanish against a dark system theme. These helpers rescale every
# widget's font (and fixed-size dialogs' geometry) to the running screen, and
# pin a light Fusion palette so the colours are always right.
# ---------------------------------------------------------------------------

_UI_SCALE = None
_UI_FONT_FAMILIES = {'arial'}          # families that came from the .ui files
_REF_HEIGHT = 912.0                    # usable screen height the .ui was tuned for
_QWIDGETSIZE_MAX = 16777215


def ui_scale():
    """A factor >= 1.0 for the primary screen: DPI parity (96 vs 72) times a
    gentle resolution term. Computed once, then cached. Override with the
    YTH_UI_SCALE environment variable (e.g. YTH_UI_SCALE=1.6)."""
    global _UI_SCALE
    if _UI_SCALE is None:
        override = os.environ.get('YTH_UI_SCALE', '').strip()
        if override:
            try:
                _UI_SCALE = max(0.5, min(float(override), 3.0))
                return _UI_SCALE
            except ValueError:
                pass
        screen = QApplication.primaryScreen()
        if screen is None:
            return 1.0
        dpi_factor = 96.0 / max(screen.logicalDotsPerInch(), 48.0)
        res_factor = screen.availableGeometry().height() / _REF_HEIGHT
        _UI_SCALE = round(min(max(dpi_factor * res_factor, 1.0), 2.0), 3)
    return _UI_SCALE


def _sc(px):
    return int(round(px * ui_scale()))


def light_palette():
    p = QPalette()
    p.setColor(QPalette.Window, QColor(0xF2, 0xF2, 0xF2))
    p.setColor(QPalette.WindowText, QColor(0x1A, 0x1A, 0x1A))
    p.setColor(QPalette.Base, QColor(0xFF, 0xFF, 0xFF))
    p.setColor(QPalette.AlternateBase, QColor(0xEA, 0xEA, 0xEA))
    p.setColor(QPalette.ToolTipBase, QColor(0xFF, 0xFF, 0xE1))
    p.setColor(QPalette.ToolTipText, QColor(0x1A, 0x1A, 0x1A))
    p.setColor(QPalette.Text, QColor(0x1A, 0x1A, 0x1A))
    p.setColor(QPalette.Button, QColor(0xF2, 0xF2, 0xF2))
    p.setColor(QPalette.ButtonText, QColor(0x1A, 0x1A, 0x1A))
    p.setColor(QPalette.BrightText, QColor(0xC4, 0x00, 0x00))
    p.setColor(QPalette.Link, QColor(0x24, 0x5E, 0xDC))
    p.setColor(QPalette.Highlight, QColor(0x30, 0x8C, 0xC6))
    p.setColor(QPalette.HighlightedText, QColor(0xFF, 0xFF, 0xFF))
    for role in (QPalette.WindowText, QPalette.Text, QPalette.ButtonText):
        p.setColor(QPalette.Disabled, role, QColor(0x9A, 0x9A, 0x9A))
    return p


def apply_theme(app):
    """Force a light Fusion look (independent of the OS dark/light setting) and
    set a resolution-scaled base font for everything not styled by the .ui."""
    app.setStyle('Fusion')
    app.setPalette(light_palette())

    base = QFont(app.font())
    base.setPointSizeF(round(9.5 * ui_scale(), 1))
    app.setFont(base)

    app.setStyleSheet(
        'QToolTip{color:#1a1a1a;background:#ffffe1;border:1px solid #b0b0b0;}'
        'QTreeView,QListView,QTreeWidget,QTextBrowser{background:#ffffff;color:#1a1a1a;}'
    )


def scale_fonts(root):
    """Multiply the point size of every descendant widget that carries a font
    from the .ui files (family Arial) by the UI scale factor."""
    factor = ui_scale()
    if factor <= 1.001 or root is None:
        return
    for w in [root] + root.findChildren(QWidget):
        f = w.font()
        if f.family().lower() in _UI_FONT_FAMILIES and f.pointSizeF() > 0:
            g = QFont(f)
            g.setPointSizeF(f.pointSizeF() * factor)
            w.setFont(g)


def scale_geometry(win):
    """Grow a fixed-size, absolutely-positioned dialog (and its non-layout
    children) by the UI scale factor so the bigger fonts still fit."""
    factor = ui_scale()
    if factor <= 1.001 or win is None:
        return
    for w in [win] + win.findChildren(QWidget):
        mn = w.minimumSize()
        if mn.width() or mn.height():
            w.setMinimumSize(_sc(mn.width()) if mn.width() else 0,
                             _sc(mn.height()) if mn.height() else 0)
        mx = w.maximumSize()
        if mx.width() < _QWIDGETSIZE_MAX or mx.height() < _QWIDGETSIZE_MAX:
            w.setMaximumSize(
                _sc(mx.width()) if mx.width() < _QWIDGETSIZE_MAX else _QWIDGETSIZE_MAX,
                _sc(mx.height()) if mx.height() < _QWIDGETSIZE_MAX else _QWIDGETSIZE_MAX)
        if w is win:
            continue
        parent = w.parentWidget()
        if parent is not None and parent.layout() is not None:
            continue                      # position is managed by a layout
        r = w.geometry()
        w.setGeometry(QRect(_sc(r.x()), _sc(r.y()), _sc(r.width()), _sc(r.height())))
    win.resize(_sc(win.width()), _sc(win.height()))


def loadUi(uifile, baseinstance=None, package=''):
    """loadUi + automatic font/geometry rescaling for the running screen."""
    widget = _loadUi(uifile, baseinstance, package)
    target = baseinstance if baseinstance is not None else widget
    scale_fonts(target)
    if isinstance(target, QDialog):
        scale_geometry(target)
    return target


class YDL(YoutubeDL):
    # NOTE: do not name these to shadow YoutubeDL's own methods (list_formats,
    # format_resolution, _format_note). yt-dlp calls those internally with
    # signatures of its own (e.g. format_resolution(fmt, default=None)).
    def split_formats(self, info_dict):
        formats = info_dict.get('formats', [info_dict])
        videos = []
        audios = []
        for f in formats:
            if f.get('vcodec') == 'none':
                audios.append([f['format_id'], self._resolution(f), self._file_size(f), f['ext'], self._note(f)])
            else:
                videos.append([f['format_id'], self._resolution(f), self._file_size(f), f['ext'], self._note(f)])
        return videos, audios

    def _note(self, fdict):
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

    def _file_size(self, fdict):
        res = ''
        if fdict.get('filesize') is not None:
            res += format_bytes(fdict['filesize'])
        elif fdict.get('filesize_approx') is not None:
            res += '~' + format_bytes(fdict['filesize_approx'])
        return res

    @staticmethod
    def _resolution(format):
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
            'noprogress': True,
            'quiet': True,
        }
        if int(self.main_window.settings.value('proxyChecked')) == 2:
            ydl_opts['proxy'] = self.main_window.settings.value('proxy')

        # Optional: authenticate scraping with a local browser's YouTube cookies.
        # Set 'cookiesBrowser' in settings.ini to chrome/edge/firefox/
        # brave/chromium/vivaldi/opera to force one; otherwise it is auto-tried
        # only when a search returns nothing.
        self.cookies_browser = (self.main_window.settings.value('cookiesBrowser') or '').strip().lower() or None
        if self.cookies_browser:
            ydl_opts['cookiesfrombrowser'] = (self.cookies_browser,)

        self.ydl = YDL(ydl_opts)
        # Flat variant for enumerating channels / playlists: lists video URLs
        # and titles WITHOUT extracting every video (which is minutes-slow and
        # looks like an empty/hung result for a big channel).
        self.ydl_flat = YDL({**ydl_opts, 'extract_flat': 'in_playlist',
                             'playlistend': 200})

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
        link = link.strip()
        html = ''
        if 'list=' in link and 'watch?v=' not in link:
            html = self.playLists(link)
        elif any(s in link for s in ('/channel/', '/c/', '/user/', '/@')):
            html = self.channelLists(link)
        elif link and link not in self.main_window.downloadVideos.videos:
            info = self.ydl.extract_info(link, download=False)
            if not info:
                self.main_window.sig_error.emit('Could not read: {}'.format(link))
                return
            if info.get('entries') is not None:            # playlist/channel-like
                html = self.renderResults(info.get('entries') or [], info.get('title'), 3)
            else:
                html = self.renderResults([info], info.get('title'), 3)
        self.main_window.search_tab.show_html(html or '<h1>Nothing to import</h1>')

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
            try:
                results = self.youtube.search().list(
                    q=query, part='snippet', maxResults=maxResults,
                    order=order, type='video').execute().get('items', [])
            except HttpError as e:
                self.main_window.sig_error.emit(
                    'YouTube search failed ({}). The Data API daily quota may be '
                    'exhausted - try again later, or delete api_key.txt / the OAuth '
                    'token to fall back to yt-dlp scraping.'.format(e))
                return self.renderResults([], query, 0)

            ids = [r['id']['videoId'] for r in results if r.get('id', {}).get('videoId')]
            stats = {}
            if ids:
                try:
                    for v in self.youtube.videos().list(
                            part='statistics', id=','.join(ids)).execute().get('items', []):
                        stats[v['id']] = v.get('statistics', {})
                except HttpError:
                    pass

            entries = []
            for r in results:
                vid = r.get('id', {}).get('videoId')
                if not vid:
                    continue
                sn = r.get('snippet', {})
                st = stats.get(vid, {})
                thumbs = sn.get('thumbnails', {})
                thumb = (thumbs.get('high') or thumbs.get('medium')
                         or thumbs.get('default') or {}).get('url', '')
                entries.append({
                    'id': vid,
                    'webpage_url': 'https://www.youtube.com/watch?v=' + vid,
                    'title': sn.get('title', vid),
                    'thumbnail': thumb,
                    'view_count': st.get('viewCount', 'N/A'),
                    'like_count': st.get('likeCount', 'N/A'),
                })
        else:
            info = self.ydl.extract_info(query, download=False)
            entries = (info or {}).get('entries') or []

        # The Data API (and unauthenticated scraping) filter results that
        # youtube.com shows to a signed-in account with SafeSearch off. If we
        # got nothing, retry the search authenticated with the browser's cookies.
        if not any(entries):
            cookie_entries = self.cookieSearch(query, maxResults)
            if cookie_entries:
                entries = cookie_entries

        return self.renderResults(entries, query, 0)

    def cookieSearch(self, query, n):
        """yt-dlp search authenticated with a local browser's YouTube cookies,
        so results match what that signed-in browser shows (SafeSearch honours
        the account setting). Returns [] if no usable browser cookies are found.
        """
        browsers = [self.cookies_browser] if self.cookies_browser else \
            ['edge', 'chrome', 'firefox', 'chromium', 'safari', 'opera', 'brave', 'vivaldi']
        for br in browsers:
            if not br:
                continue
            try:
                opts = {'quiet': True, 'noprogress': True, 'ignoreerrors': True,
                        'extract_flat': 'in_playlist', 'cookiesfrombrowser': (br,)}
                with YoutubeDL(opts) as y:
                    info = y.extract_info('ytsearch%d:%s' % (n, query), download=False) or {}
                entries = [e for e in (info.get('entries') or []) if e]
                if entries:
                    self.cookies_browser = br    # remember what worked this session
                    return entries
            except Exception as e:
                print('cookieSearch({}): {}'.format(br, e), file=sys.stderr)
        return []

    def channelLists(self, channelId):
        """
        Args:
        - channelId: a channel URL, an @handle, a UC... id, or a channel name.
        """
        channelId = channelId.strip()
        if channelId.startswith('http'):
            url = channelId
        elif channelId.startswith('@'):
            url = 'https://www.youtube.com/' + channelId
        elif channelId.startswith('UC') and len(channelId) == 24:
            url = 'https://www.youtube.com/channel/' + channelId
        else:
            # treat it as a name/handle - let YouTube resolve it
            url = 'https://www.youtube.com/@' + channelId.lstrip('@')

        channel_info = self.ydl_flat.extract_info(url, download=False) or {}
        entries = channel_info.get('entries') or []
        # a channel page can nest tabs (Videos / Shorts / Live) as sub-playlists
        if entries and isinstance(entries[0], dict) and entries[0].get('entries') is not None:
            flat = []
            for tab in entries:
                flat.extend((tab or {}).get('entries') or [])
            entries = flat
        return self.renderResults(entries, channel_info.get('title', channelId), 1)

    def playLists(self, playlistId):
        """
        Args:
        - playlistId: the id of the playlist
        """
        playlistId = playlistId.strip()
        if 'list=' in playlistId:
            playlistId = playlistId.split('list=', 1)[1].split('&', 1)[0]

        if self.API_type != 'None':
            try:
                meta = self.youtube.playlists().list(
                    part='snippet', id=playlistId).execute().get('items', [])
                title = meta[0]['snippet']['title'] if meta else playlistId

                entries = []
                pageToken = None
                while True:
                    response = self.youtube.playlistItems().list(
                        part='snippet', playlistId=playlistId,
                        maxResults=50, pageToken=pageToken).execute()
                    for item in response.get('items', []):
                        sn = item.get('snippet', {})
                        vid = sn.get('resourceId', {}).get('videoId')
                        if not vid:
                            continue
                        thumbs = sn.get('thumbnails', {})
                        thumb = (thumbs.get('high') or thumbs.get('medium')
                                 or thumbs.get('default') or {}).get('url', '')
                        entries.append({
                            'id': vid,
                            'webpage_url': 'https://www.youtube.com/watch?v=' + vid,
                            'title': sn.get('title', vid),
                            'thumbnail': thumb,
                            'view_count': 'N/A', 'like_count': 'N/A',
                        })
                    pageToken = response.get('nextPageToken')
                    if not pageToken:
                        break
            except HttpError as e:
                self.main_window.sig_error.emit('Playlist lookup failed: {}'.format(e))
                return self.renderResults([], playlistId, 2)
        else:
            if not playlistId.startswith('http'):
                playlistId = 'https://www.youtube.com/playlist?list=' + playlistId
            playlist_info = self.ydl_flat.extract_info(playlistId, download=False) or {}
            title = playlist_info.get('title', playlistId)
            entries = playlist_info.get('entries') or []

        html = self.renderResults(entries, title, 2)

        return html

    def prepareAPIentry(self, id):
        try:
            item = self.youtube.videos().list(
                part='snippet,statistics', id=id).execute()['items'][0]
        except (HttpError, IndexError, KeyError):
            return None
        snippet = item.get('snippet', {})
        statistics = item.get('statistics', {})
        thumbs = snippet.get('thumbnails', {})
        thumb = (thumbs.get('high') or thumbs.get('medium')
                 or thumbs.get('default') or {}).get('url', '')
        return {'id': id,
                'webpage_url': 'https://www.youtube.com/watch?v=' + id,
                'title': snippet.get('title', id),
                'thumbnail': thumb,
                'view_count': statistics.get('viewCount', 'N/A'),
                'like_count': statistics.get('likeCount', 'N/A')}

    def renderResults(self, entries, heading, type_id):
        """
        Args:
        - entries: the extracted info returned by yt-dlp.

        Parses the extracted information into desired format.
        """

        html = '<h1>' + str(heading) + '</h1>'

        entries = list(entries or [])
        if not any(entries):
            return html + ("<p>No results found. YouTube itself returns nothing "
                           "for this exact query - try adding another word, or a "
                           "romanised / kana spelling.</p>")

        parent = self.main_window.allVideos.model().item(type_id)
        heading_item = StandardItem(heading, set_bold=True)
        parent.appendRow(heading_item)
        node = parent.child(parent.rowCount() - 1)

        try:
            searchAppend = int(self.main_window.settings.value('searchAppend'))
        except (TypeError, ValueError):
            searchAppend = 1

        for (i, info) in enumerate(entries or []):
            if not info:
                continue
            link = info.get('webpage_url') or info.get('url')
            if not link:
                continue

            entry = """<figure><a href='{}' target='_blank'><figcaption>{}</figcaption><img src='{}' title='{}'/></a><figcaption>views: {}, likes: {}</figcaption></figure>""".format(
                link, info.get('title', ''), info.get('thumbnail', ''), link,
                info.get('view_count', 'N/A'), info.get('like_count', 'N/A'))

            info['thumbnail_entry'] = entry
            try:
                append = type_id > 0 or i < searchAppend
                self.main_window.allVideos.importvideo(link, node, info, append=append)
            except Exception as e:
                print('renderResults: importvideo failed for {}: {}'.format(link, e), file=sys.stderr)

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

    def __init__(self, txt='', info=None, font_size=9, set_bold=False, color=None):
        super().__init__()

        font = QFont('Arial')
        font.setPointSizeF(font_size * ui_scale())
        font.setBold(set_bold)

        self.setEditable(False)
        if color is not None:
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
