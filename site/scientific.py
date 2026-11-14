"""Explicitly reviewed mathematical roles, located through source labels.

These are the three PR #8 scientific expectations, rather than a MathML snapshot
or a symbolic-equivalence checker. Changing/removing a reviewed expression needs
scientific review. A label-only rename is allowed when its unchanged syntactic
source identity has exactly one match. Generated converter IDs are used only to
join that resolved XML Math element to the rendered math element.
"""
from mathsyntax import normalize_math

NS = {'l': 'http://dlmf.nist.gov/LaTeXML'}
XID = '{http://www.w3.org/XML/1998/namespace}id'
SELECTED_MATH = '//l:Math[not(ancestor::l:toccaption) and not(parent::l:MathFork)]'

# Reviewed source expressions identify the scope of each expectation. They do
# not supply the expected Presentation MathML structure below.
REVIEWED_TEX = {
    'eq:connector-clearance': r'''\boxed{c_{ij}(w)=\min_{\substack{k\notin\{i,j\}\\\|e_{ijk}\|>0}}\frac{g_{ijk}(w)}{2\|e_{ijk}\|}.}''',
    'eq:measurement-error-energy': r'''\|R^{1/2}\eta\|_2^2=\sum_{r=1}^m\lambda_r(\Delta y_r)^2.''',
    'eq:reduced-spectral-bound': r'''\|\widehat w-w^\star\|_2\le\frac{\|R^{1/2}\eta\|_2}{\sqrt{\lambda_{\min}}},\qquad\|\widehat w-w^\star\|_\infty\le\frac{\|R^{1/2}\eta\|_2}{\sqrt{\lambda_{\min}}}.''',
}

# Keep these predicates exact: independent powers/roots, sum limits and a
# two-row minimum constraint catch converter-level mistakes even when XML,
# intermediate HTML and final HTML agree with one another.
ROLES = {
    'eq:reduced-spectral-bound': (
        ('two starred weights', './/msup[*[1][self::mi and .="w"] and *[2][self::mo and .="⋆"]]', 2),
        ('two half powers of R', './/msup[*[1][self::mi and .="R"]]/*[2][self::mrow and *[1][self::mn and .="1"] and *[2][self::mo and .="/"] and *[3][self::mn and .="2"]]', 2),
        ('two square-root minimum-eigenvalue denominators', './/mfrac/*[2][self::msqrt]/msub[*[1][self::mi and .="λ"] and *[2][self::mi and .="min"]]', 2),
    ),
    'eq:measurement-error-energy': (
        ('sum lower and upper limits', './/munderover[*[1][self::mo and .="∑"] and *[2][self::mrow and *[1][self::mi and .="r"] and *[2][self::mo and .="="] and *[3][self::mn and .="1"]] and *[3][self::mi and .="m"]]', 1),
        ('squared two-norm', './/msubsup[*[2][self::mn and .="2"] and *[3][self::mn and .="2"]]', 1),
    ),
    'eq:connector-clearance': (
        ('two minimum constraint rows', './/munder[*[1][self::mi and .="min"]]/*[2][self::mtable]/mtr', 2),
        ('fraction following minimum', './/munder[*[1][self::mi and .="min"]]/following-sibling::*[1][self::mfrac]', 1),
        ('boxed clearance', './semantics/menclose[@notation="box"]', 1),
    ),
}


def _review_error(label, detail):
    return ValueError(f'Scientific mathematics review required: {label}: {detail}')


def resolve_scientific_math(xml, page, label):
    """Return the one rendered math for a reviewed label, or fail closed.

    Inputs are parsed lxml XML and HTML trees/elements. No generated ID is an
    expectation. Duplicate labels, Math candidates, IDs or rename fingerprints
    are rejected instead of selecting the first candidate.
    """
    expected = normalize_math(REVIEWED_TEX[label])
    owners = xml.xpath('//*[@labels and contains(concat(" ",normalize-space(@labels)," "),$label)]',
                       label=' LABEL:' + label + ' ')
    if len(owners) > 1:
        raise _review_error(label, 'ambiguous source label')
    if owners:
        maths = owners[0].xpath('.//l:Math[not(ancestor::l:toccaption) and not(parent::l:MathFork)]', namespaces=NS)
        if len(maths) != 1:
            raise _review_error(label, f'expected one source Math, found {len(maths)}')
        try:
            unchanged = normalize_math(maths[0].get('tex', '')) == expected
        except ValueError:
            unchanged = False
        if not unchanged:
            raise _review_error(label, 'reviewed source expression changed')
    else:
        maths = []
        for candidate in xml.xpath(SELECTED_MATH, namespaces=NS):
            try:
                if normalize_math(candidate.get('tex', '')) == expected:
                    maths.append(candidate)
            except ValueError:
                # Unrelated unsupported expressions are diagnosed by the source
                # inventory; they cannot satisfy this reviewed identity.
                continue
        if len(maths) != 1:
            raise _review_error(label, f'missing label; unchanged reviewed expression has {len(maths)} matches')
    key = maths[0].get(XID)
    if key and len(xml.xpath('//*[@xml:id=$key]', key=key)) != 1:
        raise _review_error(label, f'ambiguous XML Math identifier: {key}')
    matches = page.xpath('//*[@id=$key]', key=key) if key else []
    if len(matches) != 1 or matches[0].tag != 'math':
        raise _review_error(label, f'expected one rendered math for XML Math {key!r}, found {len(matches)}')
    return matches[0]


def scientific_math_errors(label, node):
    """Apply only independently specified structural roles to one math node."""
    errors = []
    for description, query, expected in ROLES[label]:
        actual = len(node.xpath(query))
        if actual != expected:
            errors.append(f'Scientific MathML role mismatch: {label}: {description}: expected {expected}, found {actual}')
    return errors


def validate_scientific_math(xml, page):
    """Validate every explicitly reviewed expression and return readable errors."""
    errors = []
    for label in REVIEWED_TEX:
        try:
            node = resolve_scientific_math(xml, page, label)
        except ValueError as exc:
            errors.append(str(exc))
        else:
            errors.extend(scientific_math_errors(label, node))
    return errors
