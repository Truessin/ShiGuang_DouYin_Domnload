"""Read a normal browser's public page state and matching detail responses."""
import os
import time
from pathlib import Path

from core import UserError, allowed_url, check_cancel, find_item, parse_item, post_id, state_objects


def executable():
    for root in (os.environ.get('PROGRAMFILES', ''), os.environ.get('PROGRAMFILES(X86)', ''), os.environ.get('LOCALAPPDATA', '')):
        for tail in ('Microsoft/Edge/Application/msedge.exe', 'Google/Chrome/Application/chrome.exe'):
            path = Path(root) / tail
            if path.is_file():
                return str(path)
    raise UserError('没有找到 Edge 或 Chrome。请安装其中一个浏览器后再运行。')


def context_for(playwright, root, visible):
    profile = Path(root) / 'browser-profile'
    profile.mkdir(parents=True, exist_ok=True)
    return playwright.chromium.launch_persistent_context(str(profile), executable_path=executable(),
        headless=not visible, locale='zh-CN', viewport={'width': 1280, 'height': 900},
        accept_downloads=False, args=['--no-first-run'])


def sync_cookies(ctx, engine):
    # Cookie domain scoping is retained. Never send a global Cookie header to CDNs.
    for cookie in ctx.cookies():
        if any(cookie['domain'].lstrip('.') == d or cookie['domain'].lstrip('.').endswith('.' + d)
               for d in ('douyin.com', 'iesdouyin.com')):
            engine.session.cookies.set(cookie['name'], cookie['value'], domain=cookie['domain'],
                                       path=cookie.get('path', '/'), secure=cookie.get('secure', False))


def login(engine):
    from playwright.sync_api import Error, sync_playwright
    with sync_playwright() as p:
        ctx = context_for(p, engine.state_dir, True)
        try:
            page = ctx.pages[0] if ctx.pages else ctx.new_page()
            try:
                page.goto('https://www.douyin.com/', wait_until='domcontentloaded', timeout=30000)
            except Error:
                pass
            engine.log('请在专用浏览器里正常登录；完成后关闭该窗口，即可返回下载。')
            while ctx.pages:
                check_cancel(engine.cancel)
                try:
                    ctx.pages[0].wait_for_timeout(300)
                except Error:
                    break
        finally:
            try:
                ctx.close()
            except Error:
                pass


def browser_resolve(engine, link, target='', visible=False):
    from playwright.sync_api import Error, sync_playwright
    captured = []
    with sync_playwright() as p:
        ctx = context_for(p, engine.state_dir, visible)
        try:
            page = ctx.pages[0] if ctx.pages else ctx.new_page()
            engine.session.headers['User-Agent'] = page.evaluate('navigator.userAgent')

            def response_handler(response):
                # Do not collect arbitrary CDN images: avatars and previews are not the album.
                if not allowed_url(response.url) or not any(s in response.url for s in
                        ('/aweme/detail', '/aweme/post', '/aweme/feed', '/aweme/familiar')):
                    return
                try:
                    data = response.json()
                    if len(captured) < 40:
                        captured.append(data)
                except Exception:
                    pass

            page.on('response', response_handler)
            candidates = [f'https://www.douyin.com/video/{target}',
                          f'https://www.iesdouyin.com/share/video/{target}/'] if target else [link]
            for address in candidates:
                check_cancel(engine.cancel)
                engine.log('正在读取作品页；如需验证，可停止后打开登录 / 验证窗口。')
                try:
                    page.goto(address, wait_until='domcontentloaded', timeout=25000)
                except Error:
                    if page.is_closed():
                        raise UserError('浏览器窗口已关闭，请重新点击开始下载。')
                target = target or post_id(page.url)
                deadline = time.monotonic() + (65 if visible else 18)
                while time.monotonic() < deadline:
                    check_cancel(engine.cancel)
                    if target:
                        for value in captured:
                            item = find_item(value, target)
                            if item:
                                sync_cookies(ctx, engine)
                                return parse_item(item, target, f'https://www.douyin.com/video/{target}')
                        try:
                            value = page.evaluate('() => window._ROUTER_DATA || window.__INITIAL_STATE__ || null')
                            item = find_item(value, target)
                            if not item:
                                for value in state_objects(page.content()):
                                    item = find_item(value, target)
                                    if item:
                                        break
                            if item:
                                sync_cookies(ctx, engine)
                                return parse_item(item, target, f'https://www.douyin.com/video/{target}')
                        except Error:
                            if page.is_closed():
                                raise UserError('浏览器窗口已关闭。')
                    # Playwright dispatches network events here. time.sleep() does not.
                    page.wait_for_timeout(400)
            raise UserError('未读到该作品完整媒体清单。请点“登录 / 验证”，正常打开作品确认可见后重试；也可能是链接失效或页面结构变化。')
        finally:
            try:
                ctx.close()
            except Error:
                pass
