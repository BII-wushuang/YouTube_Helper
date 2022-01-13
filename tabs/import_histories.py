from utils import *


class ImportTab(QWidget):
    display_name = 'Import Histories'
    
    def __init__(self, main_window):
        super().__init__(main_window)
        QThread.currentThread().setObjectName('import_tab')
        self.main_window = main_window
        self.main_window.import_tab = self
        self.init_ui()
        self.show()

    def init_ui(self):
        if hasattr(sys, "_MEIPASS"):
            datadir = os.path.join(sys._MEIPASS, 'tabs//import_histories.ui')
        else:
            datadir = 'tabs//import_histories.ui'
        loadUi(datadir, self)