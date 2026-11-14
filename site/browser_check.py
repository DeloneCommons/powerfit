#!/usr/bin/env python3
"""Exercise the assembled website under /powerfit/ at desktop and phone widths."""
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import tempfile
from threading import Thread
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]


class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, *_):
        pass


def main():
    reports = ROOT / 'build/site-reports'
    reports.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory() as temporary:
        (Path(temporary) / 'powerfit').symlink_to(ROOT / 'build/site', target_is_directory=True)
        server = ThreadingHTTPServer(('127.0.0.1', 0), partial(QuietHandler, directory=temporary))
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base = f'http://127.0.0.1:{server.server_port}/powerfit/'
        results = []
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(executable_path=os.environ.get('POWERFIT_BROWSER'), args=['--no-sandbox'])
                for width, height in [(1440, 1000), (390, 844), (320, 740)]:
                    context = browser.new_context(viewport={'width': width, 'height': height}, device_scale_factor=1)
                    page = context.new_page()
                    failures, requests = [], []
                    page.on('pageerror', lambda error: failures.append(str(error)))
                    page.on('requestfailed', lambda request: failures.append(request.url))
                    page.on('request', lambda request: requests.append(request.url))
                    for name in ['index.html', 'article.html']:
                        response = page.goto(base + name, wait_until='networkidle')
                        assert response.status == 200
                        assert page.locator('h1').count() == 1
                        assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth + 1'), f'{name}: overflow at {width}'
                        page.screenshot(path=str(reports / f'{width}-{name.removesuffix(".html")}.png'))
                        if name == 'article.html':
                            assert page.locator('math').count() == 710
                            assert page.locator('math semantics annotation').count() == 710
                            assert page.locator('figure.ltx_figure img').count() == 7
                            assert page.locator('figure.ltx_table').count() == 4
                            assert page.locator('.ltx_bibitem').count() == 34
                            assert page.locator('math').evaluate_all('(nodes) => nodes.every(n => n.getBoundingClientRect().width > 0 && n.getBoundingClientRect().height > 0)')
                            for anchor in ['S4', 'S4.E38', 'A3', 'A4', 'A5.T4']:
                                page.goto(base + name + '#' + anchor)
                                target = page.locator(f'[id="{anchor}"]')
                                target.scroll_into_view_if_needed()
                                assert target.is_visible()
                                assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth + 1')
                                if width != 320:
                                    page.screenshot(path=str(reports / f'{width}-{anchor}.png'))
                            # Click a real TOC link, equation reference and author/year citation.
                            page.goto(base + name)
                            page.locator('.toc a[href="#S4"]').click()
                            assert page.url.endswith('#S4')
                            reference = page.locator('article a[href="#S2.E3"]').first
                            reference.click()
                            assert page.url.endswith('#S2.E3')
                            citation = page.locator('article a[href^="#bib."]').first
                            citation.click()
                            assert '#bib.' in page.url
                            page.goto(base + name)
                            for image in page.locator('img').all():
                                image.scroll_into_view_if_needed()
                                page.wait_for_function('(id) => {const n=document.getElementById(id); return n.complete && n.naturalWidth > 0 && n.alt.length > 10}', arg=image.get_attribute('id'))
                    pdf = context.request.get(base + 'manuscript.pdf')
                    assert pdf.ok and pdf.body().startswith(b'%PDF-')
                    assert not failures, failures
                    assert all(url.startswith(base) for url in requests), 'Unexpected external runtime request'
                    results.append({'width': width, 'height': height, 'status': 'passed', 'external_requests': 0})
                    context.close()
                browser.close()
        finally:
            server.shutdown()
            server.server_close()
    (reports / 'browser.json').write_text(json.dumps(results, indent=2) + '\n')
    print('Browser checks passed at 1440, 390 and 320 px under /powerfit/: MathML, navigation, links, images, PDF, no page overflow or external requests.')


if __name__ == '__main__':
    main()
