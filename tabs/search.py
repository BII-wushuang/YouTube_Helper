from utils import *


class SearchTab(QWidget):
    display_name = 'Search'

    def __init__(self, main_window):
        super().__init__(main_window)
        QThread.currentThread().setObjectName('search_tab')
        self.main_window = main_window
        self.main_window.search_tab = self
        self.init_ui()
        # self.webEngineView.page().setBackgroundColor(Qt.transparent)
        self.show()

    def init_ui(self):
        if hasattr(sys, "_MEIPASS"):
            datadir = os.path.join(sys._MEIPASS, 'tabs/search.ui')
        else:
            datadir = 'tabs/search.ui'
        loadUi(datadir, self)
        self.webEngineView.setPage(WebEnginePage(self.webEngineView))
        self.query.returnPressed.connect(self.search)
        self.searchBtn.clicked.connect(self.search)
        self.loadListBtn.clicked.connect(self.load_list)

    def search(self):
        query = self.query.text()
        self.main_window.tab_manager.setCurrentIndex(2)
        type_id = self.main_window.search_types.checkedId()

        if type_id == 0:
            html = self.main_window.API.searchResults(query=query)

        elif type_id == 1:
            html = self.main_window.API.channelLists(channelId=query)

        elif type_id == 2:
            html = self.main_window.API.playLists(playlistId=query)

        self.show_html(html)
        self.main_window.tab_manager.setCurrentIndex(0)

    def load_list(self):
        fname = QFileDialog.getOpenFileName(parent=None, caption='Open file', directory='./', filter='*.txt')
        if fname[0] == '':
            return

        with open(fname[0], 'r', encoding='utf-8') as f:
            queries = f.read().splitlines()

        html = ''
        self.main_window.tab_manager.setCurrentIndex(2)
        for query in queries:
            html += self.main_window.API.searchResults(query=query)

        self.show_html(html)
        self.main_window.tab_manager.setCurrentIndex(0)

    def show_html(self, html):
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
                width: 280px;
            }
            figcaption {
                text-align: center;
            }
            img {
                width: 240px; 
                margin: 10px; 
                float: left; 
                border: 10px solid black;
            }
            </style>
            </head>

            <body>
            """

        footer = """
            </body>
            </html>
            """

        final_html = header + html + footer
        self.webEngineView.setHtml(final_html)
