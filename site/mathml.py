"""Compare Presentation MathML without interpreting or rewriting mathematics."""
TOKENS = {'mi', 'mn', 'mo', 'mtext', 'ms'}
ANNOTATIONS = {'annotation', 'annotation-xml'}


def _content(node, annotations=False):
    parts = []

    def add_text(value):
        # Indentation between elements is serialization; whitespace inside tokens
        # (especially mtext) is content and must not be silently discarded.
        if value and (node.tag in TOKENS or value.strip()):
            if parts and isinstance(parts[-1], str):
                parts[-1] += value
            else:
                parts.append(value)

    add_text(node.text)
    for child in node:
        if isinstance(child.tag, str) and not (annotations and child.tag in ANNOTATIONS):
            parts.append((child.tag, tuple(sorted(child.attrib.items())), _content(child)))
        # Ignore comments, preserving any actual text following them.
        add_text(child.tail)
    return tuple(parts)


def presentation_structure(math):
    """Names, hierarchy, ordered tokens and all attributes must match.

    Attribute order, comments and inter-element indentation are irrelevant.
    A direct semantics container and its non-rendered annotations are metadata;
    its attributes are still compared. Unwrapping it also handles the documented
    literal-0 annotation repair, whose presentation child must remain unchanged.
    TeX annotations are checked independently against the converter XML.
    """
    elements = [child for child in math if isinstance(child.tag, str)]
    if len(elements) == 1 and elements[0].tag == 'semantics':
        semantics = elements[0]
        return (math.tag, tuple(sorted(math.attrib.items())),
                tuple(sorted(semantics.attrib.items())), _content(semantics, annotations=True),
                (math.text or '').strip(), (semantics.tail or '').strip())
    return (math.tag, tuple(sorted(math.attrib.items())), (), _content(math), '', '')
