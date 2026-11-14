#!/usr/bin/env python3
"""Build only public reading assets from the authoritative committed manuscript."""
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess

from lxml import etree
from source import ROOT, authored_sources, collect_dependencies, make_wrapper, read_tex, source_metadata
from render import assemble


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(command, cwd, log):
    print('+', ' '.join(map(str, command)), flush=True)
    with log.open('w') as stream:
        result = subprocess.run(command, cwd=cwd, stdout=stream, stderr=subprocess.STDOUT)
    if result.returncode:
        raise RuntimeError(f'Command failed ({result.returncode}); see {log}')


def git(*args):
    return subprocess.check_output(['git', *args], cwd=ROOT, text=True).strip()


def check_conversion_log(path, allow_math_parser=False):
    text = path.read_text(errors='replace')
    errors = [line for line in text.splitlines() if re.match(r'(?:Error:|Fatal:|Warning:)', line)
              and not (allow_math_parser and line.startswith('Warning:not_parsed:'))]
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
    deps = collect_dependencies(manuscript)
    source_hashes = {p.relative_to(ROOT).as_posix(): digest(p) for p in deps}
    run(['bash', 'scripts/build_manuscript_pdfs.sh'], ROOT, work / 'pdf-build.log')
    for path in deps:
        target = work / path.relative_to(manuscript)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, target)
    for name in ('manuscript.bbl', 'manuscript.aux'):
        shutil.copy2(manuscript / name, work / name)
    text = read_tex(manuscript / 'manuscript.tex')
    (work / 'article.tex').write_text(make_wrapper(text), encoding='utf-8')
    run(['latexml', '--dest=article.xml', 'article.tex'], work, work / 'conversion.log')
    check_conversion_log(work / 'conversion.log', allow_math_parser=True)
    run(['latexmlpost', '--format=html5', '--nosplit', '--pmml', '--mathtex',
         '--nographicimages', '--dest=article.html', 'article.xml'], work, work / 'postprocess.log')
    check_conversion_log(work / 'postprocess.log')
    figures = {}
    for pdf in sorted(p for p in deps if p.suffix == '.pdf'):
        relative = 'figures/' + pdf.with_suffix('.svg').name
        run(['pdftocairo', '-svg', str(pdf), str(output / relative)], ROOT,
            work / (pdf.stem + '.log'))
        figures[relative] = {'source': pdf.relative_to(ROOT).as_posix(),
                             'source_sha256': digest(pdf), 'sha256': digest(output / relative)}
    shutil.copy2(manuscript / 'manuscript.pdf', output / 'manuscript.pdf')
    shutil.copy2(ROOT / 'site/site.css', output / 'site.css')
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
        'converter': subprocess.check_output(['latexml', '--VERSION'], stderr=subprocess.STDOUT, text=True).strip(),
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
