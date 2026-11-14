"""Presentation around LaTeXML output; no scientific prose is maintained here."""
from copy import deepcopy
from html import escape
from pathlib import Path
from lxml import html

REPOSITORY = 'https://github.com/DeloneCommons/powerfit'


def element(tag, text=None, **attrs):
    node = html.Element(tag, **attrs)
    node.text = text
    return node


def serialize(node):
    return html.tostring(node, encoding='unicode')


def shell(title, body, page_class):
    return f'''<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="description" content="Fixed-site inverse fitting of power-diagram weights: author manuscript, mathematics, and reproducibility materials.">
<title>{escape(title)} — powerfit</title><script src="site.js"></script><link rel="stylesheet" href="site.css">
</head><body class="{page_class}">
<a class="skip-link" href="#main">Skip to content</a>
<header class="site-header"><a class="brand" href="index.html">powerfit<span>Research article</span></a>
<div class="header-controls"><nav aria-label="Primary"><a href="article.html">Article</a><a href="manuscript.pdf">PDF</a><a href="{REPOSITORY}">Repository</a></nav>
<label class="theme-control" hidden>Theme <select id="theme-select" aria-label="Theme">
<option value="system">System</option><option value="light">Light</option><option value="dark">Dark</option></select></label></div></header>
{body}
<footer class="site-footer"><p>© 2026 Ivan Yu. Chernyshov · <a href="LICENSE.txt">MIT license</a> · <a href="provenance.json">Build provenance</a></p>
<p>Author manuscript submitted for peer review. Not an accepted or published journal article.</p></footer>
</body></html>'''


def identity(provenance):
    revision = provenance['manuscript_revision']
    commit = provenance['build_commit']
    dirty = ' · local working-tree build' if provenance['dirty'] else ''
    return (f'Author-manuscript revision: <time datetime="{revision["date"]}">{revision["date"]}</time>'
            f' · <a href="{REPOSITORY}/commit/{revision["commit"]}">manuscript {revision["commit"][:12]}</a><br>'
            f'Website source: <a href="{REPOSITORY}/commit/{commit}">{commit[:12]}</a>{dirty}')


def normalize_paragraph_headings(article):
    # LaTeXML reserves h4 for subsubsections even when a paragraph's actual
    # parent is a subsection. Follow the enclosing structure, preserving classes.
    for heading in article.xpath('.//*[contains(concat(" ",@class," ")," ltx_title_paragraph ")]'):
        owner = heading.getparent()
        for ancestor in owner.iterancestors('section'):
            parents = ancestor.xpath('./h2 | ./h3 | ./h4 | ./h5')
            if parents:
                heading.tag = 'h' + str(int(parents[0].tag[1]) + 1)
                break


def assemble(raw_html, xml, output, metadata, provenance):
    doc = html.parse(str(raw_html))
    article = deepcopy(doc.xpath('//article')[0])
    article.set('id', 'article-content')
    # Layout-specific sizes do not belong in a responsive scientific article.
    for node in article.xpath('.//*[@style]'):
        del node.attrib['style']
    for comment in article.xpath('.//comment()'):
        comment.getparent().remove(comment)
    for node in article.xpath('.//h6[contains(@class,"ltx_title_theorem") or contains(@class,"ltx_title_proof")]'):
        node.tag = 'div'
    for node in article.xpath('.//h6[contains(@class,"ltx_title_abstract")]'):
        node.tag = 'h2'
    normalize_paragraph_headings(article)
    # LaTeXML 0.8.8 treats TeX "0" as false when adding annotations. Preserve
    # that valid source string explicitly; all presentation MathML stays intact.
    for math in article.xpath('.//math[not(semantics)]'):
        if math.get('alttext') != '0':
            raise ValueError('Unexpected MathML without TeX annotation')
        semantics = element('semantics')
        for child in list(math):
            semantics.append(child)
        semantics.append(element('annotation', '0', encoding='application/x-tex'))
        math.append(semantics)
    # Convert only the seven committed vector illustrations, never experiments.
    ns = {'l': 'http://dlmf.nist.gov/LaTeXML'}
    xid = '{http://www.w3.org/XML/1998/namespace}id'
    for graphic in xml.xpath('//l:graphics', namespaces=ns):
        target = 'figures/' + Path(graphic.get('graphic')).with_suffix('.svg').name
        image = article.get_element_by_id(graphic.get(xid))
        image.set('src', target)
        image.set('class', 'ltx_graphics')
        image.set('loading', 'lazy')
        figure = image.getparent()
        caption = figure.find('figcaption')
        caption_id = figure.get('id') + '-caption'
        caption.set('id', caption_id)
        image.set('aria-describedby', caption_id)
        visible_caption = deepcopy(caption)
        for annotation in visible_caption.xpath('.//annotation'):
            annotation.getparent().remove(annotation)
        image.set('alt', ' '.join(visible_caption.itertext()).split('. ')[0].strip() + '.')
        link = element('a', href=target, title='Open the vector figure at full size')
        figure.replace(image, link)
        link.append(image)
    # Named source labels are convenient stable deep links, in addition to converter IDs.
    for node in xml.xpath('//*[@labels]'):
        matches = article.xpath('.//*[@id=$id]', id=node.get(xid))
        if not matches:
            continue
        for label in node.get('labels').split():
            target = matches[0]
            tables = target.xpath('ancestor-or-self::table')
            if tables:
                target = tables[0]
            target.addprevious(element('span', id=label.removeprefix('LABEL:'), **{'class': 'source-anchor'}))
    # Only wide blocks scroll, never the document itself. They remain keyboard reachable.
    for table in list(article.xpath('.//table[not(ancestor::table)]')):
        wrapper = element('div', **{'class': 'wide-block', 'tabindex': '0',
                                   'role': 'region', 'aria-label': 'Equation or table; scroll horizontally if needed'})
        table.getparent().replace(table, wrapper)
        wrapper.append(table)
    for table in article.xpath('.//table[contains(@class,"ltx_tabular")]'):
        for header in table.xpath('./thead//td'):
            header.tag = 'th'
            header.set('scope', 'col')
    toc = element('nav', **{'aria-label': 'Article contents', 'class': 'toc'})
    details = element('details', open='open')
    details.append(element('summary', 'Contents'))
    listing = element('ol')
    for section in article.xpath('./section'):
        heading = next((c for c in section if c.tag in ('h2', 'h3')), None)
        if heading is None:
            continue
        li = element('li')
        li.append(element('a', ' '.join(heading.itertext()).strip(), href='#' + section.get('id')))
        children = section.xpath('./section')
        if children:
            sublist = element('ol')
            for child in children:
                heading2 = next((c for c in child if c.tag in ('h3', 'h4')), None)
                if heading2 is not None:
                    subli = element('li')
                    subli.append(element('a', ' '.join(heading2.itertext()).strip(), href='#' + child.get('id')))
                    sublist.append(subli)
            li.append(sublist)
        listing.append(li)
    details.append(listing)
    toc.append(details)
    notice = f'''<div class="manuscript-notice"><strong>Author manuscript · submitted for peer review</strong>
<p>Submitted to <em>Computational and Applied Mathematics</em>; not accepted or published.
This live HTML/PDF revision differs from the published v2.0.0 archive.</p>
<p class="identity">{identity(provenance)}</p>
<p><a href="manuscript.pdf">Download the PDF</a> · <a href="{REPOSITORY}/blob/main/docs/archives.md">Versions and archives</a></p></div>'''
    article_body = f'<div class="reading-layout">{serialize(toc)}<main id="main">{notice}<p class="wide-note">On narrow screens, swipe or scroll wide equations and tables to read them in full.</p>{serialize(article)}</main></div>'
    (output / 'article.html').write_text(shell(metadata['title'], article_body, 'article-page'), encoding='utf-8')
    abstract = deepcopy(article.xpath('.//*[contains(concat(" ",@class," ")," ltx_abstract ")]')[0])
    # The landing excerpt is copied from this build's converted abstract.
    for n in abstract.xpath('.//*[@id]'):
        del n.attrib['id']
    abstract.attrib.pop('id', None)
    landing = f'''<main id="main" class="landing">
<p class="eyebrow">Computational geometry · Inverse problems</p>
<h1>{escape(metadata['title'])}</h1>
<p class="byline">{escape(metadata['author'])}<br><span>{escape(metadata['affiliation'])}</span></p>
<p class="lede">Local separator estimates may disagree. This work fits them with a single power diagram at fixed sites, then checks the geometry supported by the fitted weights.</p>
<div class="reading-actions"><a class="button" href="article.html">Read the full article <span aria-hidden="true">→</span></a><a class="button secondary" href="manuscript.pdf" download>Download PDF</a></div>
<p class="revision">{identity(provenance)}</p>
<div class="landing-columns"><div class="landing-main">
<section class="contribution"><h2>From pairwise data to a spatial partition</h2>
<p>Each separator observation specifies a difference of site weights. Graph conditions characterize exact compatibility and identifiable differences; weighted least squares reconciles inconsistent observations.</p>
<p>A fitted separator does not guarantee a shared cell face. Local membership and centered clearance distinguish numerical fit from geometric support. Synthetic tests and a benchmark of 100 molecules illustrate both the possibilities and the limits.</p></section>
{serialize(abstract)}
<section class="software"><h2>Implementation and evidence</h2><p>The fitting software is maintained in <a href="https://github.com/DeloneCommons/pyvoro2">pyvoro2</a>. This repository provides the article and its scientific evidence. The reported calculations use <a href="https://doi.org/10.5281/zenodo.19143984">pyvoro2 0.6.3</a>.</p>
<p><a href="{REPOSITORY}/blob/main/docs/reproducibility.md">Reproducibility guide</a> · <a href="{REPOSITORY}/tree/main/manuscript">Authoritative LaTeX sources</a> · <a href="{REPOSITORY}/blob/main/docs/README.md">Documentation</a></p></section>
</div><aside class="research-details" aria-label="Status and archives">
<section><h2>Manuscript status</h2><p>Author manuscript submitted to <em>Computational and Applied Mathematics</em> for peer review. <strong>Not an accepted or published journal article.</strong></p><p>No journal publication DOI has been assigned here.</p></section>
<section><h2>Published archives</h2><p>These are fixed archival releases. The current HTML and PDF are a later manuscript revision and are <strong>not identical to v2.0.0</strong>.</p>
<dl><dt>powerfit v2.0.0</dt><dd>Revised article and reproducibility archive<br><a href="https://doi.org/10.5281/zenodo.24047266">10.5281/zenodo.24047266</a></dd>
<dt>powerfit v1.0.0</dt><dd>Original frozen scientific evidence<br><a href="https://doi.org/10.5281/zenodo.19673558">10.5281/zenodo.19673558</a></dd>
<dt>Project concept DOI</dt><dd>Published project versions<br><a href="https://doi.org/10.5281/zenodo.19673557">10.5281/zenodo.19673557</a></dd></dl>
<p><a href="{REPOSITORY}/blob/main/docs/archives.md">Archive and citation guidance →</a></p></section>
</aside></div></main>'''
    (output / 'index.html').write_text(shell(metadata['title'], landing, 'landing-page'), encoding='utf-8')
