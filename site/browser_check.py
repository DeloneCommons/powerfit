#!/usr/bin/env python3
"""Exercise both reading themes under /powerfit/ at desktop and phone widths."""
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import hashlib
import json
import os
import re
from pathlib import Path
import tempfile
from threading import Thread
from urllib.parse import quote, unquote, urlsplit
from playwright.sync_api import expect, sync_playwright

ROOT = Path(__file__).resolve().parents[1]


def load_browser_expectations(report_path, article_path):
    """Require successful independent validation bound to this exact article.

    Expected inventories come only from this internal report, never from the
    DOM under test. The digest prevents reuse after an article changes.
    """
    try:
        report = json.loads(Path(report_path).read_text())
        article_sha256 = hashlib.sha256(Path(article_path).read_bytes()).hexdigest()
    except (OSError, ValueError) as exc:
        raise ValueError(f'Missing or malformed source-validation report/article: {exc}') from exc
    if (not isinstance(report, dict) or type(report.get('schema_version')) is not int
            or report.get('schema_version') != 1 or report.get('valid') is not True):
        raise ValueError('Browser checks require a successful schema-1 source-validation report')
    if report.get('article_sha256') != article_sha256:
        raise ValueError('Stale source-validation report: article hash differs')
    expected = report.get('browser')
    if not isinstance(expected, dict):
        raise ValueError('Missing browser expectations in source-validation report')
    for field in ('math', 'figures', 'tables', 'bibliography'):
        value = expected.get(field)
        if type(value) is not int or value < 0:
            raise ValueError(f'Invalid source-validation report browser count: {field}')
    for field in ('toc_targets', 'reference_targets', 'bibliography_targets', 'capture_targets', 'contrast_targets'):
        values = expected.get(field)
        if (not isinstance(values, list) or any(not isinstance(value, str) or not value.strip() for value in values)
                or len(values) != len(set(values))):
            raise ValueError(f'Invalid source-validation report browser targets: {field}')
    return expected


def visible_destination(page, anchor):
    """Resolve a unique fragment and show its actual content container."""
    target = page.locator('[id=' + json.dumps(anchor) + ']')
    expect(target).to_have_count(1)
    if target.evaluate('(n) => {const r=n.getBoundingClientRect(); return r.width === 0 || r.height === 0}'):
        # Source label aliases are zero-size spans immediately preceding their
        # visible equation/table/section (possibly after other label aliases).
        assert 'source-anchor' in (target.get_attribute('class') or '').split(), anchor
        target = target.locator('xpath=following-sibling::*[not(contains(concat(" ", normalize-space(@class), " "), " source-anchor "))][1]')
        expect(target).to_have_count(1)
    target.scroll_into_view_if_needed()
    expect(target).to_be_visible()
    return target


def click_fragment(page, scope, anchor):
    links = page.locator(scope + ' a[href=' + json.dumps('#' + anchor) + ']')
    assert links.count() > 0, f'Missing validated navigation link: {anchor}'
    links.first.click()
    assert unquote(urlsplit(page.url).fragment) == anchor
    visible_destination(page, anchor)


def capture_key(index, anchor):
    """Keep report-provided IDs out of filesystem path components."""
    slug = re.sub(r'[^A-Za-z0-9_-]+', '-', anchor).strip('-')[:80] or 'target'
    return f'{index:02d}-{slug}'


class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, *_):
        pass


def theme(page, mode, resolved):
    # Link clicks can return before DOMContentLoaded initializes the selector.
    # Wait for the user-visible state, rather than sampling its hidden default.
    control = page.get_by_label('Theme', exact=True)
    expect(control).to_be_visible()
    expect(control).to_have_value(mode)
    expect(page.locator('html')).to_have_attribute('data-theme', resolved)
    assert page.locator('html').evaluate('(n) => getComputedStyle(n).colorScheme') == resolved


def contrast(page, selector, minimum=4.5, property='color'):
    """Check foreground/focus contrast against the effective ancestor background."""
    ratio = page.locator(selector).first.evaluate('''(node, property) => {
      const rgb = value => value.match(/[\\d.]+/g).slice(0, 3).map(Number);
      const luminance = value => rgb(value).map(c => {
        c /= 255; return c <= .04045 ? c / 12.92 : ((c + .055) / 1.055) ** 2.4;
      }).reduce((sum, c, i) => sum + c * [.2126, .7152, .0722][i], 0);
      let ancestor = node, background;
      do {
        background = getComputedStyle(ancestor).backgroundColor;
        ancestor = ancestor.parentElement;
      } while (ancestor && (background === 'transparent' || background === 'rgba(0, 0, 0, 0)'));
      const a = luminance(getComputedStyle(node)[property]), b = luminance(background);
      return (Math.max(a, b) + .05) / (Math.min(a, b) + .05);
    }''', property)
    assert ratio >= minimum, f'{selector} {property}: contrast {ratio:.2f} < {minimum}'


def layout(page, name, width):
    assert page.locator('h1').count() == 1
    assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth + 1'), f'{name}: overflow at {width}'
    for selector in ['body', 'a', '.identity' if name == 'article.html' else '.revision', '#theme-select']:
        contrast(page, selector)
    control = page.get_by_label('Theme', exact=True)
    page.keyboard.press('Tab')
    control.focus()
    assert control.evaluate('(n) => n.matches(":focus-visible")')
    assert control.evaluate('(n) => parseFloat(getComputedStyle(n).outlineWidth)') >= 2
    contrast(page, '#theme-select', 3, 'outlineColor')
    control.blur()
    if name == 'index.html':
        contrast(page, '.button')


def article_checks(page, base, reports, width, mode, expected):
    assert page.locator('math').count() == expected['math']
    assert page.locator('math semantics annotation').count() == expected['math']
    assert page.locator('figure.ltx_figure img').count() == expected['figures']
    assert page.locator('figure.ltx_table').count() == expected['tables']
    assert page.locator('.ltx_bibitem').count() == expected['bibliography']
    assert page.locator('math').evaluate_all('(nodes) => nodes.every(n => n.getBoundingClientRect().width > 0 && n.getBoundingClientRect().height > 0)')
    for selector in expected['contrast_targets']:
        contrast(page, selector)
    details = page.locator('.toc details')
    assert details.evaluate('(n) => n.open') == (width > 760)
    assert page.locator('.toc a').count() == len(expected['toc_targets'])
    if width <= 760:
        page.locator('.toc summary').focus()
        page.keyboard.press('Enter')
        assert details.evaluate('(n) => n.open')
        if expected['toc_targets']:
            expect(page.locator('.toc a[href=' + json.dumps('#' + expected['toc_targets'][0]) + ']')).to_be_visible()
    for field, scope in [('toc_targets', '.toc'), ('reference_targets', 'article'), ('bibliography_targets', 'article')]:
        if expected[field]:
            click_fragment(page, scope, expected[field][0])
    levels = page.locator('article h1, article h2, article h3, article h4, article h5, article h6').evaluate_all('(nodes) => nodes.map(n => Number(n.tagName.slice(1)))')
    assert all(level <= previous + 1 for previous, level in zip([0, *levels], levels)), 'Skipped heading level'
    for index, anchor in enumerate(expected['capture_targets']):
        page.goto(base + 'article.html#' + quote(anchor, safe=''))
        visible_destination(page, anchor)
        assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth + 1')
        page.screenshot(path=str(reports / f'{width}-{mode}-{capture_key(index, anchor)}.png'))
    for image in page.locator('img').all():
        image.scroll_into_view_if_needed()
        page.wait_for_function('(n) => n.complete && n.naturalWidth > 0 && n.alt.trim().length > 0', arg=image.element_handle())
        assert image.evaluate('(n) => getComputedStyle(n.parentElement).backgroundColor') == 'rgb(255, 255, 255)'
        assert image.evaluate('(n) => {for (; n; n=n.parentElement) if (getComputedStyle(n).filter !== "none") return false; return true}')
    if expected['figures']:
        page.locator('.ltx_figure').first.scroll_into_view_if_needed()
        page.screenshot(path=str(reports / f'{width}-{mode}-figure.png'))


def preferences(page, base):
    # Fresh storage, both OS preferences, and live OS changes in System mode.
    page.goto(base + 'index.html', wait_until='networkidle')
    assert page.get_by_label('Theme', exact=True).locator('option').all_text_contents() == ['System', 'Light', 'Dark']
    theme(page, 'system', 'light')
    page.emulate_media(color_scheme='dark')
    page.wait_for_function('document.documentElement.dataset.theme === "dark"')
    theme(page, 'system', 'dark')
    page.reload(wait_until='networkidle')
    theme(page, 'system', 'dark')
    for mode, opposite in [('light', 'dark'), ('dark', 'light')]:
        page.get_by_label('Theme', exact=True).select_option(mode)
        page.emulate_media(color_scheme=opposite)
        theme(page, mode, mode)
        assert page.evaluate('localStorage.getItem("powerfit-theme")') == mode
        page.reload(wait_until='networkidle')
        theme(page, mode, mode)
        page.get_by_role('navigation', name='Primary').get_by_role('link', name='Article', exact=True).click()
        theme(page, mode, mode)
        page.locator('.brand').click()
        theme(page, mode, mode)
    page.get_by_label('Theme', exact=True).select_option('system')
    assert page.evaluate('localStorage.getItem("powerfit-theme")') is None
    theme(page, 'system', 'light')
    page.emulate_media(color_scheme='dark')
    page.wait_for_function('document.documentElement.dataset.theme === "dark"')
    page.get_by_role('navigation', name='Primary').get_by_role('link', name='Article', exact=True).click()
    theme(page, 'system', 'dark')


def main():
    expected = load_browser_expectations(ROOT / 'build/site-work/source-validation.json', ROOT / 'build/site/article.html')
    reports = ROOT / 'build/site-reports'
    reports.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory() as temporary:
        (Path(temporary) / 'powerfit').symlink_to(ROOT / 'build/site', target_is_directory=True)
        server = ThreadingHTTPServer(('127.0.0.1', 0), partial(QuietHandler, directory=temporary))
        Thread(target=server.serve_forever, daemon=True).start()
        base = f'http://127.0.0.1:{server.server_port}/powerfit/'
        results = []
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(executable_path=os.environ.get('POWERFIT_BROWSER'), args=['--no-sandbox'])
                for width, height in [(1440, 1000), (390, 844), (320, 740)]:
                    context = browser.new_context(viewport={'width': width, 'height': height}, device_scale_factor=1, color_scheme='light')
                    page = context.new_page()
                    failures, requests = [], []
                    page.on('pageerror', lambda error: failures.append(str(error)))
                    page.on('requestfailed', lambda request: failures.append(request.url))
                    context.on('request', lambda request: requests.append(request.url))
                    preferences(page, base)
                    for mode in ['light', 'dark']:
                        page.get_by_label('Theme', exact=True).select_option(mode)
                        for name in ['index.html', 'article.html']:
                            response = page.goto(base + name, wait_until='networkidle')
                            assert response.status == 200
                            theme(page, mode, mode)
                            layout(page, name, width)
                            page.screenshot(path=str(reports / f'{width}-{mode}-{name.removesuffix(".html")}.png'))
                            if name == 'article.html':
                                article_checks(page, base, reports, width, mode, expected)
                    pdf = context.request.get(base + 'manuscript.pdf')
                    assert pdf.ok and pdf.body().startswith(b'%PDF-')
                    assert not failures, failures
                    assert all(url.startswith(base) for url in requests), 'Unexpected external runtime request'
                    results.append({'width': width, 'height': height, 'themes': ['system', 'light', 'dark'], 'status': 'passed', 'external_requests': 0})
                    context.close()
                # Storage denial must not disable the control or throw page errors.
                context = browser.new_context(color_scheme='light')
                context.add_init_script("Object.defineProperty(window, 'localStorage', {get() {throw new Error('Storage blocked')}})")
                page = context.new_page()
                failures = []
                page.on('pageerror', lambda error: failures.append(str(error)))
                page.goto(base + 'index.html')
                page.get_by_label('Theme', exact=True).select_option('dark')
                theme(page, 'dark', 'dark')
                page.emulate_media(media='print')
                assert page.locator('body').evaluate('(n) => getComputedStyle(n).backgroundColor') == 'rgb(255, 255, 255)'
                assert not failures, failures
                context.close()
                # Progressive enhancement: CSS honors System without JavaScript.
                for mode in ['light', 'dark']:
                    context = browser.new_context(java_script_enabled=False, color_scheme=mode)
                    page = context.new_page()
                    page.goto(base + 'article.html')
                    assert page.locator('html').evaluate('(n) => getComputedStyle(n).colorScheme') == mode
                    assert page.get_by_label('Theme', exact=True).is_hidden()
                    assert page.locator('.toc details').evaluate('(n) => n.open')
                    assert page.locator('math').count() == expected['math']
                    page.emulate_media(media='print')
                    assert page.locator('body').evaluate('(n) => getComputedStyle(n).backgroundColor') == 'rgb(255, 255, 255)'
                    context.close()
                browser.close()
        finally:
            server.shutdown()
            server.server_close()
    (reports / 'browser.json').write_text(json.dumps(results, indent=2) + '\n')
    print('Browser checks passed at 1440, 390 and 320 px under /powerfit/: System/Light/Dark, OS changes, persistence, contrast, mobile TOC, MathML, navigation, images, PDF, no overflow or external requests.')


if __name__ == '__main__':
    main()
