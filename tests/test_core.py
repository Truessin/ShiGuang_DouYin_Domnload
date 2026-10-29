import json
import threading
from urllib.parse import quote

import pytest

import core
from core import Cancelled, Engine, UserError, parse_item

ID = '7690457558616945051'
PIC = 'https://p3-sign.douyinpic.com/example'
VIDEO = 'https://v3.douyinvod.com/example.mp4'


def album():
    return {'aweme_id': ID, 'desc': '测试/图集', 'author': {'nickname': '测试作者'}, 'images': [
        {'url_list': [PIC + '/clean'], 'download_url_list': [PIC + '/tplv-dy-water-v2:foo.webp', PIC + '/watermark/backup'], 'width': 3000, 'height': 4000},
        {'display_image': {'url_list': [PIC + '/second']}, 'width': 2000, 'height': 3000}]}


def test_share_text_and_host_validation():
    assert core.extract_links('文案 https://v.douyin.com/Abc/。 https://www.douyin.com/note/'+ID) == [
        'https://v.douyin.com/Abc/', 'https://www.douyin.com/note/'+ID]
    assert not core.allowed_url('https://douyin.com.evil.example/x')
    assert not core.allowed_url('https://evil@www.douyin.com/x')
    assert not core.allowed_url('http://127.0.0.1/x')
    assert not core.allowed_url('https://www.douyin.com:9999/x')


def test_album_order_original_and_no_cover():
    item = album()
    item['video'] = {'cover': {'url_list': [PIC + '/cover']}}
    post = parse_item(item, ID)
    assert post.kind == '图集' and len(post.assets) == 2
    assert [a.index for a in post.assets] == [1, 2]
    assert post.assets[0].candidates[0].endswith('/clean')


def test_nested_album_and_missing_photo_is_error():
    item = album()
    item['image_post_info'] = {'images': item.pop('images')}
    assert len(parse_item(item, ID).assets) == 2
    item['image_post_info']['images'].append({})
    with pytest.raises(UserError):
        parse_item(item, ID)


def test_select_highest_resolution_before_bitrate():
    item = {'aweme_id': ID, 'video': {'bit_rate': [
        {'bit_rate': 9000000, 'play_addr': {'width': 720, 'height': 1280, 'url_list': [VIDEO+'?low']}},
        {'bit_rate': 8000000, 'play_addr': {'width': 1080, 'height': 1920, 'url_list': [VIDEO+'?high']}}]}}
    post = parse_item(item, ID)
    assert post.assets[0].width == 1080
    assert post.assets[0].candidates == [VIDEO+'?high']


def test_never_accept_different_post():
    item = album()
    assert core.find_item({'feed': [item]}, ID) is item
    assert core.find_item({'feed': [item]}, '1234567890123456789') is None
    with pytest.raises(UserError):
        parse_item(item, '1234567890123456789')


def test_json_states_without_eval():
    item = album()
    raw = json.dumps({'loaderData': {'item': item}})
    for page in ['<script>window._ROUTER_DATA = '+raw+';</script>',
                 '<script id="RENDER_DATA">'+quote(raw)+'</script>']:
        assert any(core.find_item(x, ID) for x in core.state_objects(page))
    assert list(core.state_objects('<script>window._ROUTER_DATA = do_bad_thing();</script>')) == []


def test_id_variants():
    for u in [f'https://www.douyin.com/note/{ID}', f'https://www.iesdouyin.com/share/video/{ID}/',
              f'https://www.douyin.com/?modal_id={ID}']:
        assert core.post_id(u) == ID


@pytest.mark.parametrize('name', ['CON', 'AUX.txt', 'NUL', 'test:/a*?b', '..'])
def test_windows_safe_filenames(name):
    safe = core.safe_name(name)
    assert safe and not any(c in safe for c in '<>:"/\\|?*') and safe != '..'
    assert safe.split('.')[0].upper() not in ('CON', 'AUX', 'NUL')


class Response:
    def __init__(self, chunks, total=None):
        self.chunks = chunks
        self.headers = {'Content-Type': 'image/jpeg', 'Content-Length': str(total if total is not None else sum(map(len,chunks)))}
    def iter_content(self, _):
        yield from self.chunks
    def close(self):
        pass


def test_download_actual_extension_order_manifest_and_no_overwrite(tmp_path, monkeypatch):
    payload = b'RIFF\x1a\0\0\0WEBPactual_image_bytes'
    monkeypatch.setattr(core, 'get_checked', lambda *a, **kw: Response([payload]))
    engine = Engine(tmp_path/'state')
    post = parse_item(album(), ID, f'https://www.douyin.com/note/{ID}')
    folder, results = engine.download(post, [1, 2], tmp_path, lambda *a: None)
    assert [r['file'] for r in results] == ['001.webp', '002.webp']
    assert (folder/'001.webp').read_bytes() == payload
    manifest = (folder/'作品信息.json').read_text(encoding='utf-8')
    assert PIC not in manifest
    engine.download(post, [1], tmp_path, lambda *a: None)
    assert (folder/'001_2.webp').exists()


def test_bad_media_not_marked_complete(tmp_path, monkeypatch):
    monkeypatch.setattr(core, 'get_checked', lambda *a, **kw: Response([b'<html>login</html>']))
    engine = Engine(tmp_path/'state')
    with pytest.raises(UserError):
        engine.download(parse_item(album(), ID), [1], tmp_path, lambda *a: None)
    assert not list(tmp_path.rglob('*.part'))
    assert not list(tmp_path.rglob('*.jpg'))


def test_truncated_download_not_success(tmp_path, monkeypatch):
    monkeypatch.setattr(core, 'get_checked', lambda *a, **kw: Response([b'\xff\xd8\xfftiny'], total=100))
    engine = Engine(tmp_path/'state')
    with pytest.raises(UserError):
        engine.download(parse_item(album(), ID), [1], tmp_path, lambda *a: None)
    assert not list(tmp_path.rglob('*.part'))


def test_stop_cleans_partial_file(tmp_path, monkeypatch):
    cancel = threading.Event()
    class Interrupted(Response):
        def iter_content(self, _):
            yield b'\xff\xd8\xfffirst'
            cancel.set()
            yield b'second'
    monkeypatch.setattr(core, 'get_checked', lambda *a, **kw: Interrupted([], total=15))
    with pytest.raises(Cancelled):
        Engine(tmp_path/'state', cancel).download(parse_item(album(), ID), [1], tmp_path, lambda *a: None)
    assert not list(tmp_path.rglob('*.part'))


def test_redirect_rejects_external_host():
    class Redirect:
        status_code = 302
        headers = {'Location': 'http://127.0.0.1/private'}
        def close(self): pass
    class Session:
        def get(self, *a, **kw): return Redirect()
    with pytest.raises(UserError):
        core.get_checked(Session(), 'https://v.douyin.com/test/', threading.Event())


def test_video_extension():
    assert core.extension(b'\0\0\0\x18ftypisom' + b'\0'*20, 'video/mp4', 'video') == '.mp4'


def test_only_platform_watermarked_images_are_rejected():
    item = album()
    item['images'][0]['url_list'] = []
    with pytest.raises(UserError, match='无平台水印'):
        parse_item(item, ID)


def test_clean_candidates_never_fall_back_to_watermarked_downloads():
    post = parse_item(album(), ID)
    assert post.assets[0].candidates == [PIC + '/clean']
    assert not any(core.has_platform_watermark(u) for a in post.assets for u in a.candidates)


def test_watermark_detection_and_clean_query():
    assert core.has_platform_watermark(PIC + '~tplv-dy-water-v2:signature.webp')
    assert core.has_platform_watermark(PIC + '?watermark=1')
    assert not core.has_platform_watermark(PIC + '?watermark=0')
    assert not core.has_platform_watermark(PIC + '~tplv-dy-aweme-images:q75.webp')
