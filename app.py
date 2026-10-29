"""拾光：本地抖音视频与图集下载界面。"""
import json
import sys
import threading
from pathlib import Path

from PyQt6 import QtCore, QtGui, QtWidgets

from core import Cancelled, Engine, UserError, check_cancel, extract_links
from version import __version__

ROOT = Path(sys.executable).parent if getattr(sys, 'frozen', False) else Path(__file__).resolve().parent


def human(n):
    for unit in ('B', 'KB', 'MB', 'GB'):
        if n < 1024:
            return f'{n:.1f} {unit}'
        n /= 1024
    return f'{n:.1f} TB'


class Worker(QtCore.QThread):
    message = QtCore.pyqtSignal(object)

    def __init__(self, links, destination, visible, state_dir, login_only=False):
        super().__init__()
        self.links, self.destination, self.visible = links, destination, visible
        self.state_dir, self.login_only = state_dir, login_only
        self.cancel = threading.Event()

    def send(self, kind, **data):
        self.message.emit({'kind': kind, **data})

    def run(self):
        engine = Engine(self.state_dir, self.cancel, lambda s: self.send('log', text=s))
        completed, failed, files = 0, 0, 0
        try:
            if self.login_only:
                from browser import login
                login(engine)
                self.send('log', text='登录窗口已关闭。可以粘贴链接后开始下载。')
                return
            for post_index, link in enumerate(self.links):
                check_cancel(self.cancel)
                self.send('parsing', current=post_index + 1, total=len(self.links))
                pending = set()
                try:
                    post = engine.resolve(link, self.visible)
                    self.send('post', key=post_index, post=post)
                    pending = {a.index for a in post.assets}

                    def event(index, state, path):
                        nonlocal files
                        if state == 'done':
                            files += 1
                            pending.discard(index)
                        self.send('file', key=post_index, index=index, state=state, path=path, files=files)

                    def progress(nth, count, received, total):
                        fraction = min(received / total, .9999) if total else 0
                        self.send('progress', key=post_index, index=post.assets[nth - 1].index,
                            received=received, total=total,
                            overall=int(1000 * (post_index + (nth - 1 + fraction) / count) / len(self.links)))

                    folder, results = engine.download(post, pending, self.destination, progress, event)
                    completed += 1
                    self.send('log', text=f'作品完成：{len(results)} 个文件，保存至 {folder.name}')
                except Cancelled:
                    self.send('unfinished', key=post_index, indices=list(pending), state='已停止')
                    raise
                except Exception as exc:
                    failed += 1
                    message = str(exc) if isinstance(exc, UserError) else f'连接或文件操作失败（{type(exc).__name__}），请检查网络、保存目录或正常登录后重试。'
                    self.send('unfinished', key=post_index, indices=list(pending), state='未完成')
                    self.send('log', text=f'第 {post_index + 1} 个作品未完成：{message}')
                self.send('post_finished', overall=int(1000 * (post_index + 1) / len(self.links)))
            self.send('summary', text=f'处理结束：{completed} 个作品完成，{failed} 个作品未完成；成功保存 {files} 个文件。', failed=failed)
        except Cancelled:
            self.send('summary', text=f'已停止，已保存 {files} 个完整文件。可以重新粘贴链接开始。', failed=0)
        except Exception as exc:
            message = str(exc) if isinstance(exc, UserError) else f'启动失败（{type(exc).__name__}），请确认 Edge / Chrome 可用。'
            self.send('summary', text=message, failed=1)
        finally:
            engine.session.close()


class Window(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        self.worker = None
        self.closing = False
        self.rows, self.paths = {}, {}
        self.state = ROOT / 'data'
        self.destination = ROOT / 'downloads'
        try:
            saved = json.loads((self.state / 'settings.json').read_text(encoding='utf-8'))
            self.destination = Path(saved.get('destination') or self.destination)
        except (OSError, ValueError):
            pass
        self.setWindowTitle(f'拾光 v{__version__} · 抖音视频与无水印图集')
        self.resize(1020, 820)
        self.setMinimumSize(840, 710)
        central = QtWidgets.QWidget()
        self.setCentralWidget(central)
        layout = QtWidgets.QVBoxLayout(central)
        layout.setContentsMargins(28, 23, 28, 18)
        layout.setSpacing(12)
        header = QtWidgets.QHBoxLayout()
        title = QtWidgets.QLabel('拾光  /  作品收藏')
        title.setObjectName('hero')
        header.addWidget(title)
        header.addStretch()
        self.login = QtWidgets.QPushButton('登录 / 验证')
        self.login.clicked.connect(self.open_login)
        header.addWidget(self.login)
        layout.addLayout(header)
        description = QtWidgets.QLabel('粘贴抖音分享内容，保存视频或整组无平台水印图片。')
        description.setObjectName('muted')
        layout.addWidget(description)
        self.text = QtWidgets.QPlainTextEdit()
        self.text.setPlaceholderText('把抖音“复制链接”得到的整段文字粘贴到这里…\n支持视频、多图图集 / 单张图片，也可以一次粘贴多个作品链接。')
        self.text.setFixedHeight(105)
        layout.addWidget(self.text)
        actions = QtWidgets.QHBoxLayout()
        paste = QtWidgets.QPushButton('粘贴链接')
        paste.clicked.connect(lambda: self.text.setPlainText(QtWidgets.QApplication.clipboard().text()))
        actions.addWidget(paste)
        self.visible = QtWidgets.QCheckBox('解析时显示浏览器')
        self.visible.setToolTip('遇到需要验证的作品时勾选，在专用浏览器中正常完成验证。不会自动绕过验证。')
        actions.addWidget(self.visible)
        actions.addStretch()
        self.stop = QtWidgets.QPushButton('停止')
        self.stop.setEnabled(False)
        self.stop.clicked.connect(self.stop_work)
        actions.addWidget(self.stop)
        self.start = QtWidgets.QPushButton('开始下载')
        self.start.setObjectName('primary')
        self.start.setMinimumWidth(145)
        self.start.clicked.connect(self.start_work)
        actions.addWidget(self.start)
        layout.addLayout(actions)
        location = QtWidgets.QHBoxLayout()
        location.addWidget(QtWidgets.QLabel('统一保存至'))
        self.folder = QtWidgets.QLineEdit(str(self.destination))
        self.folder.setReadOnly(True)
        location.addWidget(self.folder, 1)
        self.choose = QtWidgets.QPushButton('选择文件夹')
        self.choose.clicked.connect(self.choose_folder)
        location.addWidget(self.choose)
        open_folder = QtWidgets.QPushButton('打开文件夹')
        open_folder.clicked.connect(self.open_folder)
        location.addWidget(open_folder)
        layout.addLayout(location)
        self.status = QtWidgets.QLabel('准备就绪')
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self.progress = QtWidgets.QProgressBar()
        self.progress.setRange(0, 1000)
        self.progress.setValue(0)
        self.progress.setTextVisible(False)
        self.progress.setFixedHeight(7)
        layout.addWidget(self.progress)
        self.table = QtWidgets.QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(['文件 / 作品', '类型', '可获取尺寸', '下载进度', '状态'])
        self.table.verticalHeader().hide()
        self.table.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.horizontalHeader().setSectionResizeMode(0, QtWidgets.QHeaderView.ResizeMode.Stretch)
        self.table.setColumnWidth(1, 62)
        self.table.setColumnWidth(2, 110)
        self.table.setColumnWidth(3, 185)
        self.table.setColumnWidth(4, 85)
        self.table.cellDoubleClicked.connect(self.open_file)
        layout.addWidget(self.table, 1)
        self.log = QtWidgets.QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumBlockCount(300)
        self.log.setFixedHeight(90)
        self.log.setPlaceholderText('运行记录：解析、下载、完成或失败原因会显示在这里。双击已完成文件可以打开。')
        layout.addWidget(self.log)
        foot = QtWidgets.QLabel('图片仅使用未标记平台水印的源地址；不涂抹、不裁切。作者原图中的文字或署名可能仍存在。')
        foot.setWordWrap(True)
        foot.setObjectName('muted')
        layout.addWidget(foot)
        self.setStyleSheet('''
QMainWindow,QWidget{background:#f3f6f9;color:#26364a;font-family:Microsoft YaHei;font-size:12px;}
QLabel#hero{font-size:25px;font-weight:650;color:#18364b;} QLabel#muted{color:#748396;font-size:11px;}
QPlainTextEdit,QLineEdit,QTableWidget{background:#fff;border:1px solid #dae3ec;border-radius:8px;padding:9px;selection-background-color:#d9edf2;}
QPushButton{background:#fff;border:1px solid #d5dfe8;border-radius:7px;padding:8px 15px;} QPushButton:hover{background:#e7f0f5;border-color:#abc4d2;}
QPushButton#primary{background:#206e79;color:white;border:0;font-weight:600;} QPushButton#primary:hover{background:#185c65;}
QPushButton:disabled{background:#edf0f3;color:#a0acb8;border-color:#e0e5ea;} QHeaderView::section{background:#edf3f7;border:0;padding:9px;color:#687c8f;}
QTableWidget{gridline-color:#edf1f4;padding:0;} QProgressBar{border:0;background:#e3eaf0;border-radius:3px;} QProgressBar::chunk{background:#369899;border-radius:3px;}
QCheckBox{spacing:7px;color:#758496;}
''')

    def choose_folder(self):
        dest = QtWidgets.QFileDialog.getExistingDirectory(self, '选择统一下载目录', str(self.destination))
        if dest:
            self.destination = Path(dest)
            self.folder.setText(dest)
            try:
                self.state.mkdir(parents=True, exist_ok=True)
                (self.state / 'settings.json').write_text(json.dumps({'destination': dest}, ensure_ascii=False), encoding='utf-8')
            except OSError:
                self.status.setText('目录本次已生效，但无法保存设置。')

    def open_folder(self):
        try:
            self.destination.mkdir(parents=True, exist_ok=True)
            QtGui.QDesktopServices.openUrl(QtCore.QUrl.fromLocalFile(str(self.destination)))
        except OSError:
            self.status.setText('无法打开文件夹，请选择可写目录。')

    def open_file(self, row, _):
        if row in self.paths:
            QtGui.QDesktopServices.openUrl(QtCore.QUrl.fromLocalFile(self.paths[row]))

    def set_busy(self, busy):
        self.start.setEnabled(not busy)
        self.login.setEnabled(not busy)
        self.choose.setEnabled(not busy)
        self.text.setReadOnly(busy)
        self.stop.setEnabled(busy)

    def start_work(self):
        if self.worker:
            return
        try:
            links = extract_links(self.text.toPlainText())
        except UserError as exc:
            self.status.setText(str(exc))
            return
        self.table.setRowCount(0)
        self.rows.clear()
        self.paths.clear()
        self.log.clear()
        self.begin(Worker(links, self.destination, self.visible.isChecked(), self.state))

    def open_login(self):
        if not self.worker:
            self.status.setText('将打开专用抖音窗口，登录或验证完成后关闭窗口返回。登录状态仅保存在本机 data 文件夹。')
            self.begin(Worker([], self.destination, True, self.state, login_only=True))

    def begin(self, worker):
        self.worker = worker
        self.set_busy(True)
        self.worker.message.connect(self.on_message)
        self.worker.finished.connect(self.work_finished)
        self.worker.start()

    def stop_work(self):
        if self.worker:
            self.worker.cancel.set()
            self.stop.setEnabled(False)
            self.status.setText('正在停止，等待当前连接返回并关闭专用浏览器…')

    def work_finished(self):
        self.worker.deleteLater()
        self.worker = None
        self.set_busy(False)
        if self.progress.maximum() == 0:
            self.progress.setRange(0, 1000)
            self.progress.setValue(0)
        if self.closing:
            self.close()

    def on_message(self, event):
        kind = event['kind']
        if kind == 'log':
            self.log.appendPlainText(event['text'])
        elif kind == 'parsing':
            self.status.setText(f'正在解析作品 {event["current"]}/{event["total"]}…')
            self.progress.setRange(0, 0)
        elif kind == 'post':
            post = event['post']
            self.progress.setRange(0, 1000)
            self.status.setText(f'{post.kind} · {len(post.assets)} 个文件 · {post.title[:55]}')
            for asset in post.assets:
                row = self.table.rowCount()
                self.table.insertRow(row)
                self.table.setRowHeight(row, 40)
                self.rows[(event['key'], asset.index)] = row
                label = f'{asset.index:03d} · {post.title[:45]}'
                size = f'{asset.width} × {asset.height}' if asset.width and asset.height else '页面未标注'
                for col, text in enumerate([label, '图片' if asset.kind == 'image' else '视频', size, '', '等待下载']):
                    self.table.setItem(row, col, QtWidgets.QTableWidgetItem(text))
                bar = QtWidgets.QProgressBar()
                bar.setRange(0, 100)
                bar.setValue(0)
                bar.setFormat('等待')
                bar.setFixedHeight(21)
                self.table.setCellWidget(row, 3, bar)
        elif kind == 'progress':
            row = self.rows[(event['key'], event['index'])]
            bar = self.table.cellWidget(row, 3)
            total = event['total']
            bar.setRange(0, 100 if total else 0)
            if total:
                bar.setValue(min(99, int(100 * event['received'] / total)))
                bar.setFormat(f'{human(event["received"])} / {human(total)}')
            else:
                self.table.item(row, 4).setText(human(event['received']))
            self.progress.setRange(0, 1000)
            self.progress.setValue(event['overall'])
        elif kind == 'file':
            row = self.rows[(event['key'], event['index'])]
            self.table.item(row, 4).setText({'downloading': '下载中', 'done': '已完成', 'failed': '失败'}[event['state']])
            if event['state'] == 'done':
                self.paths[row] = event['path']
                self.table.item(row, 0).setText(Path(event['path']).name)
                self.table.item(row, 0).setToolTip(event['path'])
                bar = self.table.cellWidget(row, 3)
                bar.setRange(0, 100)
                bar.setValue(100)
                bar.setFormat('已完成')
        elif kind == 'unfinished':
            for index in event['indices']:
                row = self.rows.get((event['key'], index))
                if row is not None:
                    self.table.item(row, 4).setText(event['state'])
                    bar = self.table.cellWidget(row, 3)
                    bar.setRange(0, 100)
                    bar.setFormat(event['state'])
        elif kind == 'post_finished':
            self.progress.setRange(0, 1000)
            self.progress.setValue(event['overall'])
        elif kind == 'summary':
            self.status.setText(event['text'])
            self.log.appendPlainText(event['text'])

    def closeEvent(self, event):
        if self.worker:
            self.closing = True
            self.stop_work()
            event.ignore()
        else:
            event.accept()


def main():
    if '--verify-link' in sys.argv:
        try:
            link = sys.argv[sys.argv.index('--verify-link') + 1]
            engine = Engine(ROOT / 'data')
            post = engine.resolve(extract_links(link)[0])
            result = {'ok': True, 'id': post.id, 'type': post.kind, 'file_count': len(post.assets)}
        except Exception as exc:
            result = {'ok': False, 'error_type': type(exc).__name__}
        (ROOT / 'engine-verification.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
        return 0 if result['ok'] else 1
    app = QtWidgets.QApplication(sys.argv)
    app.setStyle('Fusion')
    window = Window()
    window.show()
    if '--smoke-test' in sys.argv:
        def finish():
            window.grab().save(str(ROOT / 'smoke.png'))
            (ROOT / 'smoke.json').write_text(json.dumps({'window': window.windowTitle(), 'start_enabled': window.start.isEnabled(), 'network_used': False}), encoding='utf-8')
            app.quit()
        QtCore.QTimer.singleShot(650, finish)
    return app.exec()


if __name__ == '__main__':
    raise SystemExit(main())
