from utils import *

class PreferencesDialog(QDialog):
    default_settings = """[General]
proxy=
proxyChecked=0
searchAppend=1
saveSearchSettings=0
maxResults=5
order=Relevance
directory=./
output=%(title)s.%(ext)s
overwrite=0
writesubtitles=0
writeautomaticsub=0
subtitleslangs=en,zh,fr
preferredVideos=mp4
preferredAudios=mp3
keepFiles=0
convertFormats=2
"""

    def __init__(self, parent):
        super().__init__(parent)
        if hasattr(sys, "_MEIPASS"):
            datadir = os.path.join(sys._MEIPASS, 'dialogs/Preferences.ui')
        else:
            datadir = 'dialogs/Preferences.ui'
        loadUi(datadir, self)
        self.init_settings()
        self.directoryBtn.clicked.connect(self.change_directory)
        self.saveSettingsBtn.clicked.connect(self.saveSettings)
        self.resetSettingsBtn.clicked.connect(self.resetSettings)
        self.exitBtn.clicked.connect(self.close)

    def show_dialog(self):
        self.show()
        self.exec_()

    def init_settings(self, resetSettings=False):
        if not os.path.isfile('settings.ini') or resetSettings:
            with open('settings.ini', 'w') as f:
                f.write(self.default_settings.strip().replace(" ", ""))

        self.parent().settings = QSettings('settings.ini', QSettings.IniFormat)

        for k in self.parent().settings.allKeys():
            val = self.parent().settings.value(k)
            if k == 'maxResults' or k == 'order':
                continue
            elif eval('self.' + k + '.__class__') == QCheckBox:
                val = int(val)
                eval('self.' + k + '.setCheckState(val)')
            elif eval('self.' + k + '.__class__') == QComboBox:
                eval('self.' + k + '.setCurrentText(val)')
            elif eval('self.' + k + '.__class__') == QPlainTextEdit:
                if type(val) == list:
                    val = ', '.join(val)
                eval('self.' + k + '.setPlainText(val)')
            elif eval('self.' + k + '.__class__') == QSpinBox:
                val = int(val)
                eval('self.' + k + '.setValue(val)')

    def change_directory(self):
        folder = QFileDialog.getExistingDirectory(parent=None, caption='Choose Default Download Directory', directory='./')
        self.parent().settings.setValue('directory', folder)
        self.directory.setPlainText(folder)

    def saveSettings(self):
        for k in self.parent().settings.allKeys():
            val = None
            if k == 'maxResults' or k == 'order':
                continue
            elif eval('self.' + k + '.__class__') == QCheckBox:
                val = eval('self.' + k + '.checkState()')
            elif eval('self.' + k + '.__class__') == QComboBox:
                val = eval('self.' + k + '.currentText()')
            elif eval('self.' + k + '.__class__') == QPlainTextEdit:
                val = eval('self.' + k + '.toPlainText()')
            elif eval('self.' + k + '.__class__') == QSpinBox:
                val = eval('self.' + k + '.value()')
            self.parent().settings.setValue(k, val)

        self.parent().init_API()

        if self.parent().settings.value('saveSearchSettings') == 2:
            self.parent().settings.setValue('maxResults', self.parent().maxResults.value())
            self.parent().settings.setValue('order', self.parent().order.currentText())

        self.parent().settings.sync()
        self.close()

    def resetSettings(self):
        self.init_settings(True)


class DocumentationDialog(QDialog):
    def __init__(self):
        super().__init__()
        if hasattr(sys, "_MEIPASS"):
            datadir = os.path.join(sys._MEIPASS, 'dialogs/Documentation.ui')
        else:
            datadir = 'dialogs/Documentation.ui'
        loadUi(datadir, self)
        self.webEngineView.setPage(WebEnginePage(self.webEngineView))
        self.webEngineView.setUrl(QUrl('file:///../assets/Documentation.html'))

    def show_dialog(self):
        self.show()
        self.exec_()


class AboutDialog(QDialog):
    def __init__(self):
        super().__init__()
        if hasattr(sys, "_MEIPASS"):
            datadir = os.path.join(sys._MEIPASS, 'dialogs/About.ui')
        else:
            datadir = 'dialogs/About.ui'
        loadUi(datadir, self)
    def show_dialog(self):
        self.show()
        self.exec_()


class ErrorDialog(QDialog):
    def __init__(self, error_msg):
        super().__init__()
        if hasattr(sys, "_MEIPASS"):
            datadir = os.path.join(sys._MEIPASS, 'dialogs/Error.ui')
        else:
            datadir = 'dialogs/Error.ui'
        loadUi(datadir, self)
        self.error_box.setText(error_msg)
