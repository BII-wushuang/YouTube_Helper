from utils import *


class MyChannelTab(QWidget):
    display_name = 'My Channel'
    
    def __init__(self, main_window):
        super().__init__(main_window)
        QThread.currentThread().setObjectName('mychannel_tab')
        self.main_window = main_window
        self.main_window.mychannel_tab = self
        self.init_ui()
        self.show()

    def init_ui(self):
        if hasattr(sys, "_MEIPASS"):
            datadir = os.path.join(sys._MEIPASS, 'tabs//mychannel.ui')
        else:
            datadir = 'tabs//mychannel.ui'
        loadUi(datadir, self)

        if self.main_window.API.API_type == 'OAuth':
            self.importVideosBtn.clicked.connect(self.importVideos)
            self.newPlaylistBtn.clicked.connect(self.newPlaylist)

            mychannel = self.main_window.API.youtube.channels().list(part='snippet', mine=True).execute()['items'][0]
            title = mychannel['snippet']['title']
            link = 'https://www.youtube.com/channel/' + mychannel['id'] + '/playlists'
            self.label.setText("""<html><head/><body><p><a href={}><span style=" text-decoration: underline; color:#0000ff;"> {}'s Playlists</span></a></p></body></html>""".format(link, title))
            playlists = self.main_window.API.youtube.playlists().list(part='snippet,contentDetails', mine=True).execute()['items']
            for playlist in playlists:
                self.addEntry(playlist)
        else:
            self.setEnabled(False)
    
    def addEntry(self, playlist):
        link = 'https://www.youtube.com/playlist?list=' + playlist['id']
        videocount = playlist['contentDetails']['itemCount']
        html = """<html><head/><body><p><a href='{}'><span style=" text-decoration: underline; color:#0000ff;">{}, Video Count: {}</span></a></p></body></html>""".format(link, playlist['snippet']['title'], videocount)
        entry = QLabel(html)
        entry.setOpenExternalLinks(True)
        info = {'id': playlist['id'], 'title': playlist['snippet']['title'], 'entry': entry}
        item = QListWidgetItem()
        item.setData(0, info)
        self.listWidget.addItem(item)
        self.listWidget.setItemWidget(item, entry)

    def importVideos(self):
        for item in self.listWidget.selectedItems():
            playlistId_Target = item.data(0).get('id')
            for video in self.main_window.downloadVideos.videos:
                request_body = {
                    'snippet': {
                        'playlistId': playlistId_Target,
                        'resourceId': {
                            'kind': 'youtube#video',
                            'videoId': video[video.find('watch?v=')+8:]
                        }
                    }
                }

                self.main_window.API.youtube.playlistItems().insert(
                    part='snippet',
                    body=request_body
                ).execute()

            entry = item.data(0).get('entry')
            left = entry.text().find('Video Count: ') + 13
            right = entry.text().find('</span></a></p></body></html>')
            videocount = int(entry.text()[left:right]) + len(self.main_window.downloadVideos.videos)
            updated_text = entry.text()[:left] + str(videocount) + entry.text()[right:]
            entry.setText(updated_text)

    def newPlaylist(self):
            title = self.lineEdit.text()
            playlist = self.main_window.API.youtube.playlists().insert(part='snippet,contentDetails', body={'snippet': {'title': title}}).execute()
            self.addEntry(playlist)