"""Ordered authored-content coverage, independent of converter-derived totals.

The comparison alphabet retains structural owners, every text token, mathematical
cell, reference, citation and graphic occurrence. Formatting-only wrappers are
transparent. This checks the supported syntax, not arbitrary TeX semantics.
"""
from collections import Counter
from pathlib import Path
import re
import unicodedata

from lxml import etree
from mathsyntax import normalize_math, math_rows
from canonical import visible_text

NS = {'l': 'http://dlmf.nist.gov/LaTeXML'}
XID = '{http://www.w3.org/XML/1998/namespace}id'
STRUCTURES = {'section', 'subsection', 'subsubsection', 'paragraph_heading',
              'appendix', 'abstract', 'proposition', 'theorem', 'corollary',
              'definition', 'remark', 'proof', 'figure', 'table', 'caption',
              'tabular', 'row', 'cell', 'itemize', 'enumerate', 'item'}
FRONT = ('title', 'author', 'affil', 'abstract', 'email', 'keywords', 'pacs')


def text_tokens(value):
    value = unicodedata.normalize('NFKC', value or '')
    value = value.translate(str.maketrans({'’': "'", '‘': "'", '“': '"', '”': '"'}))
    value = value.replace('---', '—').replace('--', '–')
    return re.findall(r'\w+|[^\w\s]', value, re.UNICODE)


class Stream:
    def __init__(self):
        self.events = []
        self.owner = 'document'
        self.node_id = None

    def add(self, kind, value):
        self.events.append({'kind': kind, 'value': value, 'owner': self.owner, 'node_id': self.node_id})

    def text(self, value):
        for token in text_tokens(value):
            self.add('text', token)


def source_stream(inventory, labels, *, html=False):
    objects = {obj['id']: obj for obj in inventory['objects']}
    maths = {obj['id']: obj for obj in inventory['math']}
    stream = Stream()

    def mathematical_rows(math):
        for row in math.get('cell_rows', math_rows(math['tex'])):
            stream.add('open', 'alignment-row')
            for cell in row:
                stream.add('open', 'alignment-cell')
                if cell:
                    stream.add('math', normalize_math(cell))
                    stream.events[-1]['node_id'] = math['id']
                stream.add('close', 'alignment-cell')
            stream.add('close', 'alignment-row')

    def mixed(tokens):
        for token in tokens:
            kind = token['kind']
            if kind == 'object':
                visit(objects[token['id']])
            elif kind == 'text':
                stream.text(token['text'])
            elif kind == 'math':
                math = maths[token['id']]
                if math.get('representation') == 'container':
                    continue
                if math.get('mode') in ('display', 'row'):
                    owner = 'equation-block' if math['mode'] == 'display' else 'equation-row-owner'
                    stream.add('open', owner)
                    if math['mode'] == 'display':
                        stream.add('equation-form', 'equation')
                    stream.add('equation-number', [str(math['number'])] if math['numbered'] else [])
                    mathematical_rows(math)
                    stream.add('close', owner)
                else:
                    for cell in math['cells']:
                        stream.add('math', cell)
                        stream.events[-1]['node_id'] = math['id']
            elif kind in ('ref', 'eqref'):
                if kind == 'eqref':
                    stream.text('(')
                for target in token['targets']:
                    stream.add('ref', labels.get(target, 'UNRESOLVED:' + target) if html else target)
                if kind == 'eqref':
                    stream.text(')')
            elif kind == 'cite':
                stream.add('cite', (token.get('command', 'citep'), tuple(token['targets']),
                                   tuple(text_tokens(token.get('prenote', '').replace('~', ' '))),
                                   tuple(text_tokens(token.get('postnote', '').replace('~', ' ')))))
            elif kind == 'link':
                stream.add('link', token['target'])
                mixed(token['content'])
                stream.add('endlink', '')
            else:
                raise ValueError(f'Unsupported inventory token {kind}')

    def visit(obj):
        kind = obj['kind']
        previous = stream.owner
        previous_id, stream.node_id = stream.node_id, obj['id']
        stream.owner = f"{previous}/{kind} {obj.get('source', '')}:{obj.get('line', '')}"
        if kind == 'document':
            front = {objects[t['id']]['kind']: objects[t['id']] for t in obj['content']
                     if t['kind'] == 'object' and objects[t['id']]['kind'] in FRONT}
            for name in FRONT:
                if name in front:
                    visit(front[name])
            for token in obj['content']:
                if token['kind'] != 'object' or objects[token['id']]['kind'] not in FRONT:
                    mixed([token])
        elif kind in ('title', 'author', 'affil'):
            stream.add('open', 'metadata:' + kind)
            mixed(obj['content'])
            stream.add('close', 'metadata:' + kind)
        elif kind == 'email':
            value = ''.join(t['text'] for t in obj['content'])
            stream.add('link', 'mailto:' + value)
            mixed(obj['content'])
            stream.add('endlink', '')
        elif kind in ('keywords', 'pacs'):
            stream.text('Keywords:' if kind == 'keywords' else obj['option'] + ':')
            mixed(obj['content'])
        elif kind == 'bibliography':
            pass  # Fresh canonical .bbl has its own complete ordered comparison.
        elif kind == 'graphic':
            target = obj['target']
            stream.add('graphic', 'figures/' + Path(target).with_suffix('.svg').name if html else target)
        elif kind == 'align':
            stream.add('open', 'equation-block')
            stream.add('equation-form', 'align')
            stream.add('equation-number', [])
            mixed(obj['content'])
            stream.add('close', 'equation-block')
        else:
            if kind == 'section' and obj.get('appendix'):
                kind = 'appendix'
            structural = kind in STRUCTURES
            if structural:
                stream.add('open', kind)
            if kind == 'proof':
                stream.add('proof-title', 'Proof.')
            if obj.get('title'):
                stream.add('open', 'heading')
                mixed(obj['title'])
                stream.add('close', 'heading')
            mixed(obj.get('content', []))
            if structural:
                stream.add('close', kind)
        stream.owner = previous
        stream.node_id = previous_id

    visit(next(obj for obj in inventory['objects'] if obj['kind'] == 'document'))
    return stream.events


def _root(tree):
    return tree.getroot() if hasattr(tree, 'getroot') else tree


def _local(node):
    return etree.QName(node).localname if isinstance(node.tag, str) else ''


def _cite_notes(node, command):
    refs = node.xpath('./l:bibref', namespaces=NS)
    if len(refs) != 1:
        raise ValueError('Unsupported citation layout: expected one key group')
    prefix, suffix = (node.text or '').strip(), (refs[0].tail or '').strip()
    if command == 'citep':
        if not prefix.startswith('(') or not suffix.endswith(')'):
            raise ValueError('Unsupported parenthetical citation delimiters')
        prefix, suffix = prefix[1:], suffix[:-1]
    elif command == 'citet':
        phrases = refs[0].xpath('./l:bibrefphrase', namespaces=NS)
        if len(phrases) != 2:
            raise ValueError('Unsupported textual citation notes')
        prefix, suffix = [visible_text(phrase) for phrase in phrases]
        if not prefix.startswith('(') or not suffix.endswith(')'):
            raise ValueError('Unsupported textual citation delimiters')
        prefix, suffix = prefix[1:], suffix[:-1]
    return tuple(text_tokens(prefix)), tuple(text_tokens(suffix.lstrip(', ')))


def converted_stream(tree, xml, *, is_html=False, raw=False):
    stream = Stream()
    visited_math = set()
    root = _root(tree)
    if is_html and root.tag != 'article':
        articles = root.xpath('.//article')
        if len(articles) != 1:
            raise ValueError('Expected one complete article')
        root = articles[0]
    bibkeys = {node.get(XID): node.get('key') for node in xml.xpath('//l:bibitem', namespaces=NS)}
    graphics = {node.get(XID): node.get('graphic') for node in xml.xpath('//l:graphics', namespaces=NS)}
    citations = iter(xml.xpath('//l:cite[not(ancestor::l:toccaption)]', namespaces=NS))

    def classes(node):
        return set(node.get('class', '').split())

    def kind_of(node):
        tag, css = _local(node), classes(node)
        if not is_html:
            if tag == 'theorem':
                return next((c.removeprefix('ltx_theorem_') for c in css if c.startswith('ltx_theorem_')), 'theorem')
            return {'paragraph': 'paragraph_heading', 'tr': 'row', 'td': 'cell'}.get(tag, tag)
        if tag == 'article':
            return 'document'
        for kind in ('section', 'subsection', 'subsubsection', 'appendix', 'paragraph',
                     'abstract', 'proof', 'figure', 'table', 'caption', 'tabular', 'itemize', 'enumerate', 'item'):
            if 'ltx_' + kind in css:
                return 'paragraph_heading' if kind == 'paragraph' else kind
        if 'ltx_theorem' in css:
            return next((c.removeprefix('ltx_theorem_') for c in css if c.startswith('ltx_theorem_')), 'theorem')
        if tag == 'tr':
            return 'row'
        if tag in ('td', 'th'):
            return 'cell'
        if 'ltx_tr' in css:
            return 'row'
        if css.intersection({'ltx_td', 'ltx_th'}):
            return 'cell'
        if tag == 'table':
            return 'layout_table'
        return tag

    def children(node, *, table=False, proof=False):
        stream.text((node.text or '').replace('∎', '') if proof else node.text)
        for child in node:
            visit(child, table=table, proof=proof)
            stream.text((child.tail or '').replace('∎', '') if proof else child.tail)

    def heading(node, *, statement=False):
        stream.add('open', 'heading')
        start = len(stream.events)
        children(node)
        if statement:
            values = stream.events[start:]
            # amsthm adds parentheses and final punctuation around the optional title.
            if values and values[-1]['value'] == '.':
                values.pop()
            if len(values) >= 2 and values[0]['value'] == '(' and values[-1]['value'] == ')':
                values = values[1:-1]
            stream.events[start:] = values
        stream.add('close', 'heading')
        if start == len(stream.events) - 1:
            del stream.events[-2:]

    def hidden(node):
        style = re.sub(r'\s+', '', node.get('style', '')).lower()
        return ('hidden' in node.attrib or node.get('aria-hidden') == 'true' or
                'display:none' in style or 'visibility:hidden' in style)

    def require_visible_equation(node, category):
        # Equation projections traverse layout wrappers directly. Their hidden
        # state, including MathFork/MathBranch and tbody ancestors, still counts.
        if hidden(node) or any(hidden(parent) for parent in node.iterancestors()):
            raise ValueError(f'{category}: hidden equation content')

    def equation_number(node, *, group=False):
        role = 'ltx_tag_equationgroup' if group else 'ltx_tag_equation'
        tags = (node.xpath('.//*[contains(concat(" ",@class," "),$role)]', role=' ' + role + ' ')
                if is_html else node.xpath('./l:tags/l:tag[@role="refnum"]', namespaces=NS))
        for tag in tags:
            require_visible_equation(tag, 'Equation ownership')
        values = [visible_text(tag) for tag in tags]
        if not is_html:
            return values
        if any(not re.fullmatch(r'\([0-9]+\)', value) for value in values):
            raise ValueError('Equation ownership: unsupported or hidden equation number')
        return [value[1:-1] for value in values]

    def equation_rows(node):
        """Yield actual rows and their scientific cells, excluding only padding."""
        if not is_html:
            if _local(node) == 'equationgroup':
                children = node.xpath('./l:equation', namespaces=NS)
                for child in children:
                    if equation_number(child):
                        raise ValueError('Equation ownership: unexpected number on a nested non-numbering row')
                    yield from equation_rows(child)
                return
            branches = node.xpath('./l:MathFork/l:MathBranch', namespaces=NS)
            if branches:
                if len(branches) != 1:
                    raise ValueError('Alignment-row ownership: ambiguous mathematical branch')
                branch = branches[0]
                rows = branch.xpath('./l:tr', namespaces=NS)
                if rows:
                    for row in rows:
                        yield row, row.xpath('./l:td', namespaces=NS)
                else:
                    yield node, branch.xpath('./l:td', namespaces=NS)
            else:
                maths = node.xpath('./l:Math', namespaces=NS)
                if len(maths) != 1:
                    raise ValueError('Alignment-row ownership: expected one direct mathematical cell')
                yield node, maths
        else:
            rows = node.xpath('.//tr[contains(concat(" ",@class," ")," ltx_eqn_row ")]')
            if not rows:
                # Simple non-table equations are also emitted by LaTeXML.
                maths = node.xpath('./math')
                if len(maths) != 1:
                    raise ValueError('Alignment-row ownership: missing equation row')
                yield node, maths
            for row in rows:
                cells = [cell for cell in row if _local(cell) in ('td', 'th') and
                         not classes(cell).intersection({'ltx_eqn_center_padleft', 'ltx_eqn_center_padright',
                                                          'ltx_eqn_leftpad', 'ltx_eqn_rightpad', 'ltx_eqn_eqno'})]
                yield row, cells

    def equation_scaffolding(node, consumed):
        """Account for the entire layout against its consumed scientific cells.

        Mathematical leaves retain the existing source/MathML checks. Only the
        explicit MathFork fallback and validated numbering metadata are exempt
        from that projection; layout itself must contain no prose or math.
        """
        def unexpected(current, reason):
            key = current.get('id') if is_html else current.get(XID)
            raise ValueError(f'Unexpected equation content: {_local(current)} {key or ""}: {reason}')

        def layout(current, allowed, consume):
            if (current.text or '').strip():
                unexpected(current, 'text outside an authored mathematical cell or numbering tag')
            for child in current:
                if isinstance(child.tag, str):
                    if (_local(child) not in allowed or
                            not is_html and etree.QName(child).namespace != NS['l']):
                        unexpected(child, 'unsupported child in equation layout')
                    consume(child)
                if (child.tail or '').strip():
                    unexpected(current, 'unconsumed text after an equation-layout child')

        def empty(current):
            # Formatting can occupy space, but neither CSS nor a padding class
            # authorizes content. Even hidden math/annotations are not padding.
            layout(current, {'span', 'br'} if is_html else set(), empty)

        def number_tag(current):
            if len(current):
                unexpected(current, 'unsupported markup inside a numbering tag')
            if is_html and not re.fullmatch(r'\([0-9]+\)', visible_text(current)):
                unexpected(current, 'invalid numbering tag')

        def html_node(current):
            tag, css = _local(current), classes(current)
            if tag == 'math':
                if current not in visited_math:
                    unexpected(current, 'mathematics outside the consumed source cells')
                return  # Source annotation and Presentation MathML checks own this leaf.
            if tag == 'span' and css.intersection({'ltx_tag_equation', 'ltx_tag_equationgroup'}):
                number_tag(current)
            elif tag in ('td', 'th') and css.intersection({
                    'ltx_eqn_center_padleft', 'ltx_eqn_center_padright', 'ltx_eqn_leftpad', 'ltx_eqn_rightpad'}):
                empty(current)
            elif tag in ('td', 'th') and 'ltx_eqn_eqno' in css:
                tags = current.xpath('.//span[contains(concat(" ",@class," ")," ltx_tag_equation ") or '
                                     'contains(concat(" ",@class," ")," ltx_tag_equationgroup ")]')
                if len(tags) > 1:
                    unexpected(current, 'multiple numbering tags in one number cell')
                def number_layout(child):
                    if child in tags:
                        number_tag(child)
                    else:
                        layout(child, {'span', 'br'}, number_layout)
                layout(current, {'span', 'br'}, number_layout)
            elif tag in ('td', 'th'):
                if current not in consumed:
                    unexpected(current, 'scientific cell excluded from the equation projection')
                layout(current, {'math'}, html_node)
            else:
                allowed = {'table': {'tbody', 'tr'}, 'tbody': {'tr'}, 'tr': {'td', 'th'},
                           'div': {'math', 'span'}}.get(tag)
                if allowed is None:
                    unexpected(current, 'unsupported equation wrapper')
                layout(current, allowed, html_node)

        def xml_node(current):
            tag = _local(current)
            if tag == 'Math':
                if _local(current.getparent()) != 'MathFork' and current not in visited_math:
                    unexpected(current, 'mathematics outside the consumed source cells')
                return  # Includes only the recognized MathFork fallback at that position.
            if tag == 'tags':
                numbers = current.xpath('./l:tag[@role="refnum"]/text()', namespaces=NS)
                if len(numbers) != 1 or not re.fullmatch(r'[0-9]+', numbers[0]):
                    unexpected(current, 'unsupported equation numbering metadata')
                expected = {None: '(' + numbers[0] + ')', 'refnum': numbers[0], 'autoref': 'Equation ' + numbers[0]}
                seen = set()
                def metadata(child):
                    number_tag(child)
                    role = child.get('role')
                    if role not in expected or role in seen or visible_text(child) != expected[role]:
                        unexpected(child, 'unexpected equation numbering metadata')
                    seen.add(role)
                layout(current, {'tag'}, metadata)
                return
            allowed = {'equation': {'tags', 'Math', 'MathFork'},
                       'equationgroup': {'tags', 'equation', 'equationgroup'},
                       'MathFork': {'Math', 'MathBranch'}, 'MathBranch': {'tr', 'td'},
                       'tr': {'td'}, 'td': {'Math'}}[tag]
            children = [_local(child) for child in current if isinstance(child.tag, str)]
            if tag == 'td' and current not in consumed:
                unexpected(current, 'scientific cell excluded from the equation projection')
            if tag == 'equation' and children.count('Math') + children.count('MathFork') != 1:
                unexpected(current, 'expected one mathematical representation')
            if tag == 'MathFork' and children != ['Math', 'MathBranch']:
                unexpected(current, 'expected one fallback Math followed by one delivered MathBranch')
            layout(current, allowed, xml_node)

        (html_node if is_html else xml_node)(node)

    def emit_rows(node, consumed):
        for row, cells in equation_rows(node):
            require_visible_equation(row, 'Alignment-row ownership')
            previous_id = stream.node_id
            stream.node_id = row.get('id') if is_html else row.get(XID)
            stream.add('open', 'alignment-row')
            if not cells:
                raise ValueError('Alignment-row ownership: missing scientific cells')
            for cell in cells:
                consumed.add(cell)
                require_visible_equation(cell, 'Alignment-row ownership')
                stream.add('open', 'alignment-cell')
                visit(cell)
                stream.add('close', 'alignment-cell')
            stream.add('close', 'alignment-row')
            stream.node_id = previous_id

    def equation_block(node):
        consumed = set()
        aligned = 'ltx_eqn_align' in classes(node)
        group = _local(node) == 'equationgroup' or 'ltx_equationgroup' in classes(node)
        stream.add('open', 'equation-block')
        stream.add('equation-form', 'align' if aligned else 'equation')
        stream.add('equation-number', equation_number(node, group=group))
        if aligned:
            if is_html:
                bodies = node.xpath('./tbody')
                owners = []
                for body in bodies:
                    owners.extend([body] if body.get('id') else body.xpath('./tr[@id]'))
            else:
                owners = node.xpath('./l:equation | ./l:equationgroup', namespaces=NS)
            if not owners:
                raise ValueError('Alignment-row ownership: missing align owners')
            for owner in owners:
                previous_id = stream.node_id
                stream.node_id = owner.get('id') if is_html else owner.get(XID)
                stream.add('open', 'equation-row-owner')
                stream.add('equation-number', equation_number(owner))
                emit_rows(owner, consumed)
                stream.add('close', 'equation-row-owner')
                stream.node_id = previous_id
        else:
            if group and is_html and equation_number(node):
                raise ValueError('Equation ownership: unexpected number on a nested non-numbering row')
            emit_rows(node, consumed)
        equation_scaffolding(node, consumed)
        stream.add('close', 'equation-block')

    def visit(node, *, table=False, proof=False):
        tag, css = _local(node), classes(node)
        if not tag:
            return
        # Hidden authored content cannot satisfy visible coverage. Generated
        # annotations/fallback branches are handled separately below.
        if hidden(node):
            return
        kind = kind_of(node)
        if kind == 'cell' and table:
            for attribute in ('colspan', 'rowspan'):
                if node.get(attribute, '1') != '1':
                    raise ValueError(f'Table-grid span violation: {attribute}={node.get(attribute)!r}')
        previous = stream.owner
        node_id = node.get('id') if is_html else node.get(XID)
        previous_id, stream.node_id = stream.node_id, node_id
        stream.owner = f'{kind} {node_id or ""}'
        if (not is_html and tag in ('tags', 'tag', 'resource', 'pagination', 'toccaption', 'toctitle', 'bibliography') or
                is_html and ('ltx_tag' in css or 'source-anchor' in css or 'ltx_bibliography' in css or 'ltx_pagination' in css)):
            pass
        elif not is_html and tag == 'Math' and _local(node.getparent()) == 'MathFork':
            pass  # Only the explicit MathBranch is delivered by the HTML transform.
        elif (not is_html and tag in ('equation', 'equationgroup') or
              is_html and tag in ('table', 'div') and classes(node).intersection({'ltx_equation', 'ltx_equationgroup'})):
            equation_block(node)
        elif tag == ('math' if is_html else 'Math'):
            tex = node.get('alttext') if is_html else node.get('tex')
            if tex is None:
                raise ValueError('Missing mathematical source annotation')
            tex = re.sub(r'^\\displaystyle\s*', '', tex)
            stream.add('math', normalize_math(tex))
            visited_math.add(node)
        elif tag == 'sup' and (not is_html or 'ltx_sup' in css):
            stream.add('math', normalize_math('^{' + visible_text(node) + '}'))
        elif not is_html and tag == 'graphics':
            stream.add('graphic', node.get('graphic'))
        elif is_html and tag == 'img':
            if raw:
                if node.get('src') != '' or node_id not in graphics:
                    raise ValueError('Unexpected raw graphic placeholder')
                stream.add('graphic', 'figures/' + Path(graphics[node_id]).with_suffix('.svg').name)
            else:
                stream.add('graphic', node.get('src'))
        elif tag == 'cite':
            command = next((c.removeprefix('ltx_citemacro_') for c in css if c.startswith('ltx_citemacro_')), 'citep')
            if is_html:
                links = node.xpath('.//a[@href]')
                targets = tuple(bibkeys.get(link.get('href', '').removeprefix('#'), 'UNRESOLVED:' + link.get('href', '')) for link in links)
                original = next(citations, None)
                if original is None or not links:
                    raise ValueError('Missing or unexpected citation group')
                expected_pre, _ = _cite_notes(original, command)
                prefix = visible_text(node)
                suffix = (links[-1].tail or '').strip()
                if command == 'citep':
                    if not prefix.startswith('(') or not suffix.endswith(')'):
                        raise ValueError('Unsupported rendered citation delimiters')
                    prefix, suffix = prefix[1:], suffix[:-1]
                elif command == 'citet':
                    if not suffix.endswith(')'):
                        raise ValueError('Unsupported textual citation delimiters')
                    suffix = suffix[:-1]
                # Canonical natbib display validation independently checks the
                # repeated textual-note placement inside each author group.
                pre = expected_pre if command == 'citet' else tuple(text_tokens(prefix)[:len(expected_pre)])
                post = tuple(text_tokens(suffix.lstrip(', ')))
            else:
                targets = tuple(key for ref in node.xpath('.//l:bibref', namespaces=NS)
                                for key in ref.get('bibrefs', '').split(','))
                pre, post = _cite_notes(node, command)
            stream.add('cite', (command, targets, pre, post))
        elif not is_html and tag == 'ref' and node.get('labelref'):
            stream.add('ref', node.get('labelref').removeprefix('LABEL:'))
        elif not is_html and tag == 'ref' and 'ltx_nolink' in css:
            children(node, table=table, proof=proof)
        elif is_html and tag == 'a' and node.get('href', '').startswith('#'):
            stream.add('ref', node.get('href')[1:])
        elif (not is_html and tag == 'ref' and node.get('href') is not None or
              is_html and tag == 'a' and node.get('href') is not None and not node.xpath('.//img')):
            stream.add('link', node.get('href'))
            children(node, table=table, proof=proof)
            stream.add('endlink', '')
        elif ((not is_html and tag in ('title', 'creator', 'date') and _local(node.getparent()) == 'document') or
              (is_html and css.intersection({'ltx_title_document', 'ltx_authors', 'ltx_dates'}))):
            field = ('title' if tag == 'title' or 'ltx_title_document' in css else
                     'author' if tag == 'creator' or 'ltx_authors' in css else 'affil')
            stream.add('open', 'metadata:' + field)
            if field == 'affil' and is_html:
                value = visible_text(node)
                if not value.startswith('(') or not value.endswith(')'):
                    raise ValueError('Unsupported rendered affiliation')
                stream.text(value[1:-1])
            else:
                children(node)
            stream.add('close', 'metadata:' + field)
        elif tag == 'title' or is_html and ('ltx_title' in css or any(c.startswith('ltx_title_') for c in css)):
            parent_kind = kind_of(node.getparent())
            if parent_kind == 'proof':
                stream.add('proof-title', visible_text(node))
            elif parent_kind != 'abstract':
                heading(node, statement=parent_kind in ('theorem', 'proposition', 'corollary', 'definition', 'remark'))
        else:
            structural = kind in STRUCTURES and (kind not in ('row', 'cell') or table)
            if structural:
                stream.add('open', kind)
            children(node, table=table or kind == 'tabular', proof=proof or kind == 'proof')
            if structural:
                stream.add('close', kind)
        stream.owner = previous
        stream.node_id = previous_id

    visit(root)
    return stream.events


def _differences(expected, observed, stage):
    a = [(e['kind'], e['value']) for e in expected]
    b = [(e['kind'], e['value']) for e in observed]
    if a == b:
        return []
    i = next((i for i, pair in enumerate(zip(a, b)) if pair[0] != pair[1]), min(len(a), len(b)))
    want, got = expected[i:i + 1], observed[i:i + 1]
    kinds = {e['kind'] for e in want + got}
    boundaries = {e['value'] for e in want + got if e['kind'] in ('open', 'close')}
    owner = (want or expected[max(0, i - 1):i] or got)[0]['owner']
    categories = ['Source content']
    equation = bool(kinds.intersection({'equation-number', 'equation-form'}) or
                    boundaries.intersection({'equation-block', 'equation-row-owner'}))
    alignment = bool(boundaries.intersection({'alignment-row', 'alignment-cell'}))
    if 'math' in kinds or equation or alignment:
        categories.append('Source mathematics')
    if equation:
        categories.append('Equation ownership')
    if alignment:
        categories.append('Alignment-row ownership')
    return [f'{category} mismatch ({stage}, {owner}, event {i}): expected {a[i:i + 3]!r}; observed {b[i:i + 3]!r}'
            for category in categories]


def validate_label_ownership(inventory, xml, matches):
    """Bind labels to independently matched owners, not converter label names.

    Numbering alone is insufficient: a section and an equation can share a
    number. Source equation blocks and align-row owners are explicitly matched;
    mathematical cell matches also retain their independently inventoried owner.
    """
    nodes = {node.get(XID): node for node in xml.xpath('//*[@xml:id]', namespaces={'xml': 'http://www.w3.org/XML/1998/namespace'})}
    objects = {obj['id']: obj for obj in inventory['objects']}
    labelled = {}
    for node in xml.xpath('//*[@labels]'):
        for label in node.get('labels').split():
            labelled.setdefault(label.removeprefix('LABEL:'), []).append(node)
    structural, mathematical = {}, {}
    for match in matches:
        obj = objects.get(match['source_id'], {})
        equation_owner = (match['value'] == 'equation-block' and obj.get('kind') in ('equation', 'display', 'align') or
                          match['value'] == 'equation-row-owner' and obj.get('kind') == 'equation_row')
        if match['kind'] == 'open' and (match['value'] in STRUCTURES or equation_owner):
            structural.setdefault(match['source_id'], set()).add(match['xml_id'])
        elif match['kind'] == 'math':
            mathematical.setdefault(match['source_id'], set()).add(match['xml_id'])
    errors, destinations = [], {}
    for label, owner in inventory['labels'].items():
        obj = objects[owner]
        candidates = set(structural.get(owner, ()))
        if not candidates:
            for math in inventory['math']:
                if math.get('owner') != owner or math.get('representation') == 'container':
                    continue
                for key in mathematical.get(math['id'], ()):
                    node = nodes.get(key)
                    equations = [] if node is None else node.xpath('ancestor::l:equation[1]', namespaces=NS)
                    if equations:
                        candidates.add(equations[0].get(XID))
        actual = labelled.get(label, [])
        if len(candidates) != 1 or None in candidates or len(actual) != 1 or actual[0].get(XID) not in candidates:
            errors.append(f'Source label ownership mismatch: {label} belongs to {obj["kind"]} '
                          f'{obj.get("source", "")}:{obj.get("line", "")}; matched={sorted(str(x) for x in candidates)}')
        else:
            destinations[label] = next(iter(candidates))
    return errors, destinations


def validate_generated_identities(inventory, xml, raw, page, matches):
    """Check visible type/number prefixes against bounded source counters."""
    errors = []
    owners = {match['source_id']: match['xml_id'] for match in matches
              if match['kind'] == 'open' and match['value'] in STRUCTURES}
    headings = {'section', 'subsection', 'subsubsection', 'paragraph_heading'}
    statements = {'proposition', 'theorem', 'corollary', 'definition', 'remark'}
    def by_id(tree, attribute):
        index = {}
        for node in _root(tree).iter():
            key = node.get(attribute)
            if key is not None:
                index.setdefault(key, []).append(node)
        return index
    xml_ids = by_id(xml, XID)
    html_ids = [('raw HTML', by_id(raw, 'id')), ('final HTML', by_id(page, 'id'))]
    def visible(nodes):
        return [visible_text(node).rstrip(':').strip() for node in nodes]
    for obj in inventory['objects']:
        kind = obj['kind']
        if kind not in headings | statements | {'figure', 'table'} or 'number' not in obj:
            continue
        key, number = owners.get(obj['id']), obj['number']
        nodes = xml_ids.get(key, [])
        if len(nodes) != 1:
            errors.append(f'Source visible identity has no unique owner: {obj["id"]}')
            continue
        if number is None:
            expected, expected_number = [], []
        else:
            prefix = (obj['statement_heading'] + ' ' if kind in statements else
                      kind.title() + ' ' if kind in ('figure', 'table') else
                      'Appendix ' if kind == 'section' and obj.get('appendix') else '')
            expected, expected_number = [prefix + str(number)], [str(number)]
        node = nodes[0]
        if visible(node.xpath('./l:tags/l:tag[@role="refnum"]', namespaces=NS)) != expected_number:
            errors.append(f'Source visible identity numbering mismatch (XML metadata): {obj["id"]}')
        if visible(node.xpath('./l:title/l:tag | ./l:caption/l:tag', namespaces=NS)) != expected:
            errors.append(f'Source visible identity mismatch (XML): {obj["id"]}: expected {expected}')
        for stage, index in html_ids:
            nodes = index.get(key, [])
            tags = [] if len(nodes) != 1 else nodes[0].xpath(
                './*[contains(concat(" ",@class," ")," ltx_title ") or '
                'contains(concat(" ",@class," ")," ltx_caption ")]'
                '/*[contains(concat(" ",@class," ")," ltx_tag ")]')
            if visible(tags) != expected:
                errors.append(f'Source visible identity mismatch ({stage}): {obj["id"]}: expected {expected}')
    return errors


def validate_inventory(inventory, xml, raw, page):
    """Return errors and a report; counts are reported only after object matching."""
    labels = {label.removeprefix('LABEL:'): node.get(XID) for node in xml.xpath('//*[@labels]')
              for label in node.get('labels').split()}
    errors, streams, matches, equation_destinations = [], {}, [], {}
    for stage, tree, is_html, is_raw in [('XML', xml, False, False), ('raw HTML', raw, True, True), ('final HTML', page, True, False)]:
        try:
            expected = source_stream(inventory, labels, html=is_html)
            observed = converted_stream(tree, xml, is_html=is_html, raw=is_raw)
            differences = _differences(expected, observed, stage)
            errors.extend(differences)
            streams[stage] = {'expected_events': len(expected), 'matched': not differences}
            if not differences:
                equation_destinations[stage] = {
                    wanted['node_id']: actual['node_id'] for wanted, actual in zip(expected, observed)
                    if wanted['kind'] == 'open' and wanted['value'] in ('equation-block', 'equation-row-owner')}
            if stage == 'XML' and not differences:
                matches = [{'source_id': wanted['node_id'], 'kind': wanted['kind'], 'value': wanted['value'],
                            'xml_id': actual['node_id'], 'owner': wanted['owner']}
                           for wanted, actual in zip(expected, observed)
                           if wanted['kind'] in ('open', 'math', 'graphic')]
        except (ValueError, KeyError) as exc:
            errors.append(f'Source content mismatch ({stage}): {exc}')
    destinations = {}
    if streams.get('XML', {}).get('matched'):
        # The independent source comparison establishes content/number owners
        # in every stage first. Link destinations must then follow those same
        # owners, even when both HTML stages swap their generated container IDs.
        for stage in ('raw HTML', 'final HTML'):
            if stage in equation_destinations:
                for owner, key in equation_destinations['XML'].items():
                    if not key or equation_destinations[stage].get(owner) != key:
                        errors.append(f'Equation ownership destination mismatch ({stage}): {owner}')
        label_errors, destinations = validate_label_ownership(inventory, xml, matches)
        errors.extend(label_errors)
        errors.extend(validate_generated_identities(inventory, xml, raw, page, matches))
    expected_numbers = [str(m['number']) for m in inventory['math'] if m.get('numbered')]
    xml_numbers = xml.xpath('//l:equation/l:tags/l:tag[@role="refnum"]/text() | '
                            '//l:equationgroup/l:tags/l:tag[@role="refnum"]/text()', namespaces=NS)
    if xml_numbers != expected_numbers:
        errors.append(f'Source equation numbering mismatch (XML): {xml_numbers} != {expected_numbers}')
    for stage, tree in [('raw HTML', raw), ('final HTML', page)]:
        numbers = [visible_text(n) for n in tree.xpath('//*[contains(concat(" ",@class," ")," ltx_tag_equation ") or '
                                                      'contains(concat(" ",@class," ")," ltx_tag_equationgroup ")]')]
        if numbers != ['(' + number + ')' for number in expected_numbers]:
            errors.append(f'Source equation numbering mismatch ({stage}): {numbers} != {expected_numbers}')
    report = {'schema_version': 1, 'valid': not errors, 'representations': streams, 'matches': matches,
              'label_destinations': destinations,
              'source_objects': dict(Counter(obj['kind'] for obj in inventory['objects'])), 'errors': errors}
    return errors, report
