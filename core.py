"""Public page parsing and byte-preserving downloads. No private API signing."""
import hashlib
import html
import json
import os
import re
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

import requests

MOBILE_UA = ('Mozilla/5.0 (Linux; Android 13; Pixel 7) AppleWebKit/537.36 '
             '(KHTML, like Gecko) Chrome/120.0 Mobile Safari/537.36')
SHARE_DOMAINS = ('douyin.com', 'iesdouyin.com')
MEDIA_DOMAINS = SHARE_DOMAINS + ('douyinvod.com', 'douyincdn.com', 'byteimg.com',
    'douyinpic.com', 'ibytedtos.com', 'snssdk.com', 'pstatp.com', 'bytecdn.cn',
    'douyinstatic.com', 'toutiaoimg.com', 'ixiguavideo.com', 'bytegoofy.com', 'bytefcdn.com')


class UserError(Exception):
    pass


class Cancelled(UserError):
    pass


def check_cancel(event):
    if event.is_set():
        raise Cancelled('已停止。未完成的文件不会标记为下载成功。')


def allowed_url(url, media=False):
    try:
        p = urlparse(url)
        host = (p.hostname or '').lower()
        return p.scheme in ('http', 'https') and not p.username and not p.password and p.port in (None, 80, 443) and any(
            host == d or host.endswith('.' + d) for d in (MEDIA_DOMAINS if media else SHARE_DOMAINS))
    except ValueError:
        return False


def extract_links(text):
    links = re.findall(r'https?://[^\s<>"\u3000]+', text)
    result = []
    for link in links:
        link = link.rstrip('。，、；！!）)]}》”’\'.,;')
        if allowed_url(link) and link not in result:
            result.append(link)
    if not result:
        raise UserError('没有找到抖音链接。请粘贴完整分享文字或 https://v.douyin.com/… 链接。')
    return result


def post_id(url):
    m = re.search(r'/(?:video|note)/(\d{10,})', url)
    if m:
        return m[1]
    query = parse_qs(urlparse(url).query)
    for key in ('modal_id', 'aweme_id', 'item_id'):
        val = query.get(key, [''])[0]
        if re.fullmatch(r'\d{10,}', val):
            return val
    return ''


def state_objects(page):
    """Decode data as JSON only. Never evaluate scripts from a shared page."""
    decoder = json.JSONDecoder()
    for match in re.finditer(r'(?:window\.)?(?:_ROUTER_DATA|__INITIAL_STATE__|__NEXT_DATA__|SIGI_STATE)\s*=\s*', page):
        try:
            yield decoder.raw_decode(page[match.end():].lstrip())[0]
        except (ValueError, RecursionError):
            pass
    for match in re.finditer(r'<script\b([^>]*)>(.*?)</script\s*>', page, re.S | re.I):
        attrs, text = match.groups()
        if re.search(r'RENDER_DATA|__NEXT_DATA__|SIGI_STATE|application/json', attrs, re.I):
            for raw in (text.strip(), unquote(text.strip()), html.unescape(text.strip())):
                try:
                    yield json.loads(raw)
                    break
                except (ValueError, RecursionError):
                    pass


def find_item(value, target):
    stack = [value]
    while stack:
        current = stack.pop()
        if isinstance(current, dict):
            identity = str(current.get('aweme_id') or current.get('awemeId') or current.get('item_id') or '')
            if identity == target and any(current.get(k) for k in ('video', 'images', 'image_post_info', 'imagePostInfo')):
                return current
            stack.extend(current.values())
        elif isinstance(current, list):
            stack.extend(reversed(current))
    return None


def urls(value):
    if isinstance(value, str):
        return [value] if allowed_url(value, media=True) else []
    if isinstance(value, list):
        return list(dict.fromkeys(u for entry in value for u in urls(entry)))
    if isinstance(value, dict):
        result = []
        for key in ('url_list', 'urlList', 'url', 'src'):
            result.extend(urls(value.get(key)))
        return list(dict.fromkeys(result))
    return []


def has_platform_watermark(url):
    parsed = urlparse(url)
    path = unquote(parsed.path).lower()
    if re.search(r'watermark|dy-water|water-v[0-9]', path):
        return True
    for key, values in parse_qs(parsed.query).items():
        if key.casefold() in ('watermark', 'water_mark') and any(v.casefold() not in ('0', 'false', 'none', '') for v in values):
            return True
        if any('watermark' in unquote(v).casefold() for v in values):
            return True
    return False


def number(value):
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


@dataclass
class Asset:
    index: int
    kind: str
    candidates: list
    width: int = 0
    height: int = 0
    bitrate: int = 0
    label: str = ''


@dataclass
class Post:
    id: str
    title: str
    author: str
    kind: str
    assets: list = field(default_factory=list)
    page_url: str = ''


def parse_item(item, target, page_url=''):
    if str(item.get('aweme_id') or item.get('awemeId') or '') != target:
        raise UserError('页面内容与分享作品不一致，未下载其他作品。')
    author = item.get('author') or {}
    post = Post(target, str(item.get('desc') or item.get('title') or '未命名作品'),
                str(author.get('nickname') or '') if isinstance(author, dict) else '', '', page_url=page_url)
    images = item.get('images')
    if not images:
        image_info = item.get('image_post_info') or item.get('imagePostInfo') or {}
        images = image_info.get('images') if isinstance(image_info, dict) else None
    if images:
        post.kind = '图集'
        for i, image in enumerate(images, 1):
            if not isinstance(image, dict):
                raise UserError(f'第 {i} 张图片结构无法识别，未把不完整图集当作完整结果。')
            candidates = []
            # download_url_list commonly applies tplv-dy-water-v2. Prefer the
            # site's actual origin/display address, never a known watermarked fallback.
            for key in ('origin_image', 'originImage', 'url_list', 'urlList',
                        'display_image', 'displayImage', 'download_url_list', 'downloadUrlList'):
                candidates.extend(urls(image.get(key)))
            candidates = [u for u in dict.fromkeys(candidates) if not has_platform_watermark(u)]
            if not candidates:
                raise UserError(f'第 {i} 张图片未提供可用的无平台水印地址，已停止，不会用带平台水印的图片代替。')
            post.assets.append(Asset(i, 'image', candidates, number(image.get('width')),
                                     number(image.get('height')), label=f'图片 {i:03d}'))
        return post
    video = item.get('video') or {}
    if not isinstance(video, dict):
        raise UserError('未识别到视频或图集。')
    formats = []
    # Each format holds alternate CDN URLs, not separate pictures/videos.
    for bit in video.get('bit_rate') or video.get('bitRate') or []:
        if not isinstance(bit, dict):
            continue
        address = bit.get('play_addr') or bit.get('playAddr') or {}
        candidates = urls(address)
        if candidates:
            formats.append((number(address.get('width')) or number(video.get('width')),
                            number(address.get('height')) or number(video.get('height')),
                            number(bit.get('bit_rate') or bit.get('bitRate')), 1, candidates))
    for key in ('play_addr', 'playAddr', 'play_addr_h264', 'playAddrH264', 'play_addr_265', 'download_addr', 'downloadAddr'):
        address = video.get(key) or {}
        candidates = urls(address)
        if candidates and isinstance(address, dict):
            formats.append((number(address.get('width')) or number(video.get('width')),
                            number(address.get('height')) or number(video.get('height')), 0,
                            0 if key.startswith('download') else 1, candidates))
    formats.sort(key=lambda f: (f[0] * f[1], f[2], f[3]), reverse=True)
    if not formats:
        raise UserError('页面没有提供可保存的视频地址，请在专用浏览器中正常登录后重试。')
    w, h, bitrate, _, candidates = formats[0]
    # Keep exact format alternatives; do not silently fall back to lower quality.
    post.kind = '视频'
    post.assets.append(Asset(1, 'video', candidates, w, h, bitrate, '最高可获取清晰度视频'))
    return post


def safe_name(name, max_len=65):
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', str(name)).strip(' .')[:max_len].rstrip(' .')
    if not name:
        name = '未命名作品'
    if name.split('.')[0].upper() in {'CON', 'PRN', 'AUX', 'NUL'} | {f'{a}{n}' for a in ('COM', 'LPT') for n in range(1, 10)}:
        name = '_' + name
    return name


def get_checked(session, url, cancel, media=False, stream=False):
    for _ in range(9):
        check_cancel(cancel)
        if not allowed_url(url, media=media):
            raise UserError('已拦截不属于抖音及其媒体域名的地址。')
        response = session.get(url, timeout=(10, 25), allow_redirects=False, stream=stream)
        if response.status_code in (301, 302, 303, 307, 308):
            from urllib.parse import urljoin
            next_url = urljoin(url, response.headers.get('Location', ''))
            response.close()
            if next_url == url:
                raise UserError('链接重定向异常。')
            url = next_url
            continue
        response.raise_for_status()
        return response
    raise UserError('分享链接重定向次数过多，请换用作品完整链接。')


def extension(header, mime, kind):
    if header.startswith(b'\xff\xd8\xff'):
        return '.jpg'
    if header.startswith(b'\x89PNG\r\n\x1a\n'):
        return '.png'
    if header[:4] == b'RIFF' and header[8:12] == b'WEBP':
        return '.webp'
    if header[:6] in (b'GIF87a', b'GIF89a'):
        return '.gif'
    if header[4:8] == b'ftyp':
        brand = header[8:12]
        if brand in (b'avif', b'avis'):
            return '.avif'
        if brand in (b'heic', b'heix', b'hevc', b'mif1'):
            return '.heic'
        if kind == 'video':
            return '.mp4'
    if kind == 'video' and header.startswith(b'\x1aE\xdf\xa3'):
        return '.webm'
    raise UserError('下载结果不是可识别的原始媒体文件，可能是登录页、验证页或失效地址。')


class Engine:
    def __init__(self, state_dir, cancel=None, log=None):
        self.state_dir = Path(state_dir)
        self.cancel = cancel or threading.Event()
        self.log = log or (lambda _: None)
        self.session = requests.Session()
        self.session.headers.update({'User-Agent': MOBILE_UA, 'Referer': 'https://www.douyin.com/', 'Accept-Encoding': 'identity'})

    def resolve(self, link, visible=False):
        self.log('读取分享链接…')
        try:
            response = get_checked(self.session, link, self.cancel)
            try:
                target = post_id(response.url) or post_id(link)
                if not target:
                    raise UserError('请使用单个作品的视频或图集分享链接，不支持主页或直播间。')
                for state in state_objects(response.text):
                    item = find_item(state, target)
                    if item:
                        return parse_item(item, target, f'https://www.douyin.com/video/{target}')
            finally:
                response.close()
        except requests.RequestException:
            target = post_id(link)
        if target:
            try:
                response = self.session.get('https://www.douyin.com/aweme/v1/web/aweme/detail/',
                    params={'aweme_id': target, 'aid': '6383', 'device_platform': 'webapp'}, timeout=(6, 10))
                try:
                    item = find_item(response.json(), target)
                    if item:
                        return parse_item(item, target, f'https://www.douyin.com/video/{target}')
                finally:
                    response.close()
            except (requests.RequestException, ValueError):
                pass
        check_cancel(self.cancel)
        self.log('网页需完整加载，正在使用专用浏览器解析…')
        from browser import browser_resolve
        return browser_resolve(self, link, target, visible)

    def download(self, post, indices, destination, progress, file_event=None):
        dest = Path(destination).expanduser().resolve()
        folder = dest / safe_name(f'{post.id}_{post.title}', 95)
        folder.mkdir(parents=True, exist_ok=True)
        results = []
        file_event = file_event or (lambda *args: None)
        selected = [a for a in post.assets if a.index in set(indices)]
        if not selected:
            raise UserError('请至少勾选一个文件。')
        for nth, asset in enumerate(selected, 1):
            check_cancel(self.cancel)
            self.log(f'[{nth}/{len(selected)}] 正在保存 {asset.label}…')
            file_event(asset.index, 'downloading', '')
            errors = []
            result = None
            for url in asset.candidates:
                partial = folder / f'.{asset.index:03d}.part'
                try:
                    response = get_checked(self.session, url, self.cancel, media=True, stream=True)
                    try:
                        total = number(response.headers.get('Content-Length'))
                        received = 0
                        digest = hashlib.sha256()
                        ext = None
                        with partial.open('wb') as f:
                            for chunk in response.iter_content(256 * 1024):
                                check_cancel(self.cancel)
                                if not chunk:
                                    continue
                                if ext is None:
                                    ext = extension(chunk, response.headers.get('Content-Type', ''), asset.kind)
                                    if asset.kind == 'image' and ext in ('.mp4', '.webm'):
                                        raise UserError('该图像地址返回的是视频，已停止保存。')
                                f.write(chunk)
                                digest.update(chunk)
                                received += len(chunk)
                                progress(nth, len(selected), received, total)
                        if not received or ext is None or (total and received != total):
                            raise UserError('文件下载不完整，请重试。')
                    finally:
                        response.close()
                    stem = f'{asset.index:03d}' if asset.kind == 'image' else '视频'
                    final = folder / (stem + ext)
                    suffix = 2
                    while final.exists():
                        final = folder / f'{stem}_{suffix}{ext}'
                        suffix += 1
                    os.replace(partial, final)
                    result = {'index': asset.index, 'file': final.name, 'bytes': received,
                              'sha256': digest.hexdigest(), 'width': asset.width, 'height': asset.height}
                    results.append(result)
                    file_event(asset.index, 'done', str(final))
                    break
                except Cancelled:
                    raise
                except (requests.RequestException, OSError, UserError) as exc:
                    errors.append(type(exc).__name__)
                finally:
                    partial.unlink(missing_ok=True)
            if result is None:
                file_event(asset.index, 'failed', '')
                raise UserError(f'第 {asset.index} 个文件下载失败（{", ".join(errors)}）。已成功的文件保留；可重新解析后重试。')
        # No signed CDN URLs or authentication data in the export manifest.
        manifest = {'id': post.id, 'title': post.title, 'author': post.author, 'type': post.kind,
                    'source': post.page_url, 'total_assets': len(post.assets), 'exported': results,
                    'quality': '图片排除已知平台水印地址；优先使用平台提供的无平台水印图片源；不保证作者源图中没有文字或署名；未二次压缩'}
        manifest_path = folder / '作品信息.json'
        if manifest_path.exists():
            manifest_path = folder / f'作品信息-{time.time_ns()}.json'
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
        return folder, results
