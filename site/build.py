#!/usr/bin/env python3
"""Build only public reading assets from the authoritative committed manuscript."""
import hashlib
from collections import Counter
import json
from pathlib import Path
import re
import shutil
import subprocess

from lxml import etree
from source import ROOT, authored_sources, collect_dependencies, make_wrapper, read_tex, source_metadata
from render import assemble
from inventory import read_inventory
from conversion_warnings import check_conversion_warnings


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def figure_destinations(paths):
    """Keep published URLs, rejecting distinct sources before any SVG is written."""
    destinations, owners = {}, {}
    for path in paths:
        relative = 'figures/' + path.with_suffix('.svg').name
        if relative in owners and owners[relative] != path:
            raise ValueError(f'Figure output collision: {relative}: {owners[relative]} and {path}')
        owners[relative] = path
        destinations[path] = relative
    return destinations


def run(command, cwd, log):
    print('+', ' '.join(map(str, command)), flush=True)
    with log.open('w') as stream:
        result = subprocess.run(command, cwd=cwd, stdout=stream, stderr=subprocess.STDOUT)
    if result.returncode:
        raise RuntimeError(f'Command failed ({result.returncode}); see {log}')


def git(*args):
    return subprocess.check_output(['git', *args], cwd=ROOT, text=True).strip()


def check_conversion_log(path):
    text = path.read_text(errors='replace')
    diagnostics = Counter(line for line in text.splitlines() if re.match(r'(?:Error:|Fatal:|Warning:)', line))
    errors = list(diagnostics.elements())
    if errors or re.search(r'\b[1-9]\d* (?:errors?|undefined macros?|missing files?)\b', text):
        raise RuntimeError(f'Unexpected converter diagnostics in {path}: ' + '\n'.join(errors))


def main():
    manuscript = ROOT / 'manuscript'
    build = ROOT / 'build'
    output, work = build / 'site', build / 'site-work'
    for path in (build, output, work):
        if path.is_symlink():
            raise RuntimeError(f'Refusing symbolic build directory: {path}')
    # Fixed, owned output directories prevent accidental publication or deletion elsewhere.
    for path in (output, work):
        if path.exists():
            shutil.rmtree(path)
        path.mkdir(parents=True)
    (output / 'figures').mkdir()
    inventory = read_inventory(manuscript / 'manuscript.tex')
    (work / 'source-inventory.json').write_text(json.dumps(inventory, indent=2) + '\n')
    deps = collect_dependencies(manuscript)
    figure_paths = figure_destinations(p for p in deps if p.suffix == '.pdf')
    source_hashes = {p.relative_to(ROOT).as_posix(): digest(p) for p in deps}
    run(['bash', 'scripts/build_manuscript_pdfs.sh'], ROOT, work / 'pdf-build.log')
    for path in deps:
        target = work / path.relative_to(manuscript)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, target)
    for name in ('manuscript.bbl', 'manuscript.aux', 'manuscript.fls'):
        shutil.copy2(manuscript / name, work / name)
    text = read_tex(manuscript / 'manuscript.tex')
    (work / 'article.tex').write_text(make_wrapper(text), encoding='utf-8')
    version = subprocess.check_output(['latexml', '--VERSION'], stderr=subprocess.STDOUT, text=True).strip()
    (work / 'tool-versions.json').write_text(json.dumps({
        'latexml': version, 'pdflatex': subprocess.check_output(['pdflatex', '--version'], text=True).splitlines()[0],
        'latexmlpost': subprocess.check_output(['latexmlpost', '--VERSION'], stderr=subprocess.STDOUT, text=True).strip(),
    }, indent=2) + '\n')
    # Source-location comments otherwise leak through Springer's \doiurl -> \url
    # expansion at 25-line boundaries in the canonical .bbl. Never edit the .bbl.
    run(['latexml', '--nocomments', '--dest=article.xml', 'article.tex'], work, work / 'conversion.log')
    check_conversion_warnings(work / 'conversion.log', work / 'article.latexml.log', inventory,
                              version, ROOT / 'site/reviewed-math-warnings.json', work / 'warning-matches.json')
    run(['latexmlpost', '--format=html5', '--nosplit', '--pmml', '--mathtex',
         '--nographicimages', '--dest=article.html', 'article.xml'], work, work / 'postprocess.log')
    check_conversion_log(work / 'postprocess.log')
    figures = {}
    for pdf, relative in sorted(figure_paths.items()):
        run(['pdftocairo', '-svg', str(pdf), str(output / relative)], ROOT,
            work / (pdf.stem + '.log'))
        figures[relative] = {'source': pdf.relative_to(ROOT).as_posix(),
                             'source_sha256': digest(pdf), 'sha256': digest(output / relative)}
    shutil.copy2(manuscript / 'manuscript.pdf', output / 'manuscript.pdf')
    shutil.copy2(ROOT / 'site/site.css', output / 'site.css')
    shutil.copy2(ROOT / 'site/site.js', output / 'site.js')
    shutil.copy2(ROOT / 'LICENSE', output / 'LICENSE.txt')
    # Manuscript date follows scientific source history, not this site's build clock.
    science = [p.relative_to(ROOT).as_posix() for p in authored_sources(manuscript)]
    science += ['manuscript/refs.bib', *[p.relative_to(ROOT).as_posix() for p in deps if p.suffix == '.pdf']]
    revision = git('log', '-1', '--format=%H %cs', '--', *science).split()
    provenance = {
        'schema_version': 1,
        'repository': 'https://github.com/DeloneCommons/powerfit',
        'build_commit': git('rev-parse', 'HEAD'),
        'dirty': bool(git('status', '--porcelain', '--untracked-files=normal')),
        'manuscript_revision': {'commit': revision[0], 'date': revision[1]},
        'publication_status': 'Author manuscript submitted for peer review; not accepted or published',
        'archive_note': 'The current manuscript differs from the published v2.0.0 archive (10.5281/zenodo.24047266).',
        'source_sha256': source_hashes,
        'pdf_sha256': digest(output / 'manuscript.pdf'),
        'figures': figures,
        'converter': version,
    }
    assemble(work / 'article.html', etree.parse(str(work / 'article.xml')), output, source_metadata(text), provenance)
    (output / 'provenance.json').write_text(json.dumps(provenance, indent=2) + '\n', encoding='utf-8')
    for path in deps:
        if digest(path) != source_hashes[path.relative_to(ROOT).as_posix()]:
            raise RuntimeError(f'Authoritative source changed during build: {path}')
    from validate import validate
    errors = validate(output, work, manuscript)
    if errors:
        raise RuntimeError('Website validation failed:\n' + '\n'.join(errors))
    print(f'Validated website: {output}')


if __name__ == '__main__':
    main()
