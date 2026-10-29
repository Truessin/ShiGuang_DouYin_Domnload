import os

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import time

from PyQt6 import QtWidgets

import app
from core import Asset, Post

qt = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


def wait_done(window):
    deadline = time.monotonic() + 4
    while window.worker and time.monotonic() < deadline:
        qt.processEvents()
        time.sleep(.01)
    assert window.worker is None


def test_empty_input_does_not_start_thread():
    w = app.Window()
    w.start_work()
    assert w.worker is None
    assert '没有找到' in w.status.text()
    w.close()


def test_lifecycle_and_second_download(monkeypatch, tmp_path):
    class FakeEngine:
        def __init__(self, *a):
            self.session = type('Session', (), {'close': lambda s: None})()
        def resolve(self, *a):
            return Post('1234567890123456789','test','author','图集', [Asset(1,'image',['unused'],100,200,'图片 001')])
        def download(self, post, indices, destination, progress, event):
            event(1,'downloading','')
            progress(1,1,5,10)
            event(1,'done',str(tmp_path/'001.webp'))
            return tmp_path,[{'bytes':10}]
    monkeypatch.setattr(app,'Engine',FakeEngine)
    w = app.Window()
    w.text.setPlainText('https://www.douyin.com/note/1234567890123456789')
    for _ in range(2):
        w.start_work()
        wait_done(w)
        assert w.start.isEnabled() and not w.stop.isEnabled()
        assert w.table.rowCount() == 1
        assert w.table.item(0,4).text() == '已完成'
        assert w.progress.value() == 1000
    w.close()


def test_failed_items_not_marked_success():
    w = app.Window()
    p = Post('1','a','b','图集',[Asset(1,'image',['unused']), Asset(2,'image',['unused'])])
    w.on_message({'kind':'post','key':0,'post':p})
    w.on_message({'kind':'unfinished','key':0,'indices':[1,2],'state':'未完成'})
    assert [w.table.item(i,4).text() for i in range(2)] == ['未完成','未完成']
    w.close()
