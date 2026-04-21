"""Select a deterministic random PubChem-backed main molecule set for QTAIM runs.

The selector performs two PubChem searches, applies local RDKit filtering, and
writes manifest plus audit files for the larger benchmark dataset. Console
progress is part of the user experience only and does not affect saved outputs.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import math
import os
import random
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable, Sequence

# Project-specific PubChem selector for the larger QTAIM molecular benchmark.
# The script intentionally uses only the Python standard library plus RDKit.
#
# Selection philosophy:
# - two server-side PubChem searches (acyclic-window and cyclic-window)
# - local RDKit filtering for the exact chemistry and topology requirements
# - deterministic random-page sampling with fixed seed
# - connectivity-SMILES de-duplication
# - manifest output ready for run_pyscf_geomopt.py / run_pyscf_singlepoint.py / run_multiwfn_topology.py

try:
    from rdkit import Chem
except Exception as exc:  # pragma: no cover - import error path
    raise SystemExit(
        'RDKit is required for select_pubchem_main.py. Install the qtaim environment first.'
    ) from exc

try:
    from tqdm.auto import tqdm as _tqdm
except Exception:  # pragma: no cover - tqdm is optional at runtime
    _tqdm = None


ESEARCH_URL = 'https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi'
PUG_PROPERTY_URL_TEMPLATE = (
    'https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/cid/{cid_text}/property/{prop_text}/CSV'
)
PUG_SDF_URL_TEMPLATE = 'https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/cid/{cid}/SDF'

ALLOWED_ELEMENTS = {'H', 'C', 'N', 'O', 'F', 'S', 'Cl'}
PROPERTY_FIELDS = (
    'ConnectivitySMILES',
    'CanonicalSMILES',
    'IsomericSMILES',
    'MolecularFormula',
    'HeavyAtomCount',
)


@dataclass(frozen=True)
class StratumConfig:
    name: str
    query: str
    target: int
    reserve: int
    oversample: int
    page_size: int
    min_sssr: int
    min_cyclic_atoms: int
    require_acyclic: bool
    system_prefix: str


@dataclass(frozen=True)
class CandidateRecord:
    cid: str
    connectivity_smiles: str
    smiles: str
    canonical_smiles: str
    isomeric_smiles: str
    molecular_formula: str
    heavy_atom_count: int
    ring_count: int
    cyclic_atoms: int
    aromatic_atoms: int
    cyclic_non_aromatic_atoms: int
    class_label: str
    hash_rank: int


@dataclass(frozen=True)
class AuditRecord:
    stratum: str
    page_index: int
    cid: str
    status: str
    reason: str
    connectivity_smiles: str
    molecular_formula: str
    heavy_atom_count: str
    ring_count: str
    cyclic_atoms: str


class RateLimiter:
    def __init__(self, min_interval_seconds: float) -> None:
        self.min_interval_seconds = min_interval_seconds
        self._last = 0.0

    def wait(self) -> None:
        now = time.monotonic()
        delta = now - self._last
        if delta < self.min_interval_seconds:
            time.sleep(self.min_interval_seconds - delta)
        self._last = time.monotonic()


class _TextProgress:
    def __init__(self, total: int, desc: str, unit: str, *, status_every_seconds: float) -> None:
        self.total = max(int(total), 0)
        self.desc = desc
        self.unit = unit
        self.status_every_seconds = max(float(status_every_seconds), 0.0)
        self.current = 0
        self.postfix = ''
        self._last_emit = 0.0
        _log(f'[{self.desc}] starting: total={self.total} {self.unit}')

    def update(self, n: int = 1) -> None:
        self.current += n
        self._emit(force=self.current >= self.total)

    def set_postfix_str(self, text: str) -> None:
        self.postfix = text

    def refresh(self) -> None:
        self._emit(force=False)

    def close(self) -> None:
        self._emit(force=True)

    def _emit(self, *, force: bool) -> None:
        now = time.monotonic()
        if not force and self.status_every_seconds > 0 and (now - self._last_emit) < self.status_every_seconds:
            return
        pct = 100.0 if self.total == 0 else 100.0 * min(self.current, self.total) / self.total
        suffix = f' | {self.postfix}' if self.postfix else ''
        _log(f'[{self.desc}] {self.current}/{self.total} {self.unit} ({pct:5.1f} %){suffix}')
        self._last_emit = now


class _NullProgress:
    def update(self, n: int = 1) -> None:
        return None

    def set_postfix_str(self, text: str) -> None:
        return None

    def refresh(self) -> None:
        return None

    def close(self) -> None:
        return None


def _log(message: str) -> None:
    if _tqdm is not None:
        try:
            _tqdm.write(message)
            return
        except Exception:
            pass
    print(message, flush=True)


def _make_progress(
    *,
    total: int,
    desc: str,
    unit: str,
    show_progress: bool,
    status_every_seconds: float,
):
    if not show_progress:
        return _NullProgress()
    if _tqdm is not None:
        return _tqdm(total=total, desc=desc, unit=unit, dynamic_ncols=True, mininterval=0.2)
    return _TextProgress(total=total, desc=desc, unit=unit, status_every_seconds=status_every_seconds)


def _positive_int(value: str) -> int:
    try:
        parsed = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f'Expected a positive integer, got {value!r}') from exc
    if parsed < 1:
        raise argparse.ArgumentTypeError(f'Expected a positive integer, got {value!r}')
    return parsed


def _nonnegative_int(value: str) -> int:
    try:
        parsed = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f'Expected a non-negative integer, got {value!r}') from exc
    if parsed < 0:
        raise argparse.ArgumentTypeError(f'Expected a non-negative integer, got {value!r}')
    return parsed


def _path(value: str) -> Path:
    return Path(os.path.expandvars(os.path.expanduser(value))).resolve()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            'Select a deterministic random PubChem-based molecular dataset for qtaim_main. '
            'The script performs two PubChem searches (acyclic-window and cyclic-window), '
            'then applies local RDKit filtering and writes a manifest for downstream QChem stages.'
        )
    )
    parser.add_argument('--output-dir', type=_path, default=Path('data/qtaim_main').resolve(), help='Output directory (default: data/qtaim_main).')
    parser.add_argument('--tool', default='powerfit_qtaim_sampler', help='NCBI tool name sent to E-utilities.')
    parser.add_argument('--email', required=True, help='Contact email sent to E-utilities / PubChem.')
    parser.add_argument('--api-key', default='', help='Optional NCBI API key for higher request limits.')
    parser.add_argument('--seed', type=_nonnegative_int, default=20260410, help='Master random seed (default: 20260410).')
    parser.add_argument('--page-size', type=_positive_int, default=200, help='ESearch page size (default: 200).')
    parser.add_argument('--request-timeout', type=_positive_int, default=120, help='HTTP request timeout in seconds (default: 120).')
    parser.add_argument('--max-retries', type=_positive_int, default=5, help='Maximum retries for failed HTTP requests (default: 5).')
    parser.add_argument('--sleep-no-key', type=float, default=0.40, help='Minimum delay between requests without API key (default: 0.40 s).')
    parser.add_argument('--sleep-with-key', type=float, default=0.12, help='Minimum delay between requests with API key (default: 0.12 s).')
    parser.add_argument('--no-progress', action='store_true', help='Disable tqdm-style progress bars; only print milestone messages.')
    parser.add_argument('--status-every-seconds', type=float, default=8.0, help='Fallback text-progress update interval in seconds (default: 8.0).')

    parser.add_argument('--n-acyclic', type=_positive_int, default=50, help='Number of accepted acyclic molecules (default: 50).')
    parser.add_argument('--n-cyclic', type=_positive_int, default=50, help='Number of accepted cyclic molecules (default: 50).')
    parser.add_argument('--reserve-per-class', type=_nonnegative_int, default=25, help='Reserve molecules per class (default: 25).')
    parser.add_argument('--oversample-per-class', type=_nonnegative_int, default=25, help='Extra accepted molecules per class before final stable ranking (default: 25).')

    parser.add_argument('--acyclic-min-heavy', type=_positive_int, default=6, help='Acyclic heavy-atom lower bound for the PubChem search (default: 6).')
    parser.add_argument('--acyclic-max-heavy', type=_positive_int, default=15, help='Acyclic heavy-atom upper bound for the PubChem search (default: 15).')
    parser.add_argument('--cyclic-min-heavy', type=_positive_int, default=12, help='Cyclic heavy-atom lower bound for the PubChem search (default: 12).')
    parser.add_argument('--cyclic-max-heavy', type=_positive_int, default=30, help='Cyclic heavy-atom upper bound for the PubChem search (default: 30).')
    parser.add_argument('--cyclic-min-sssr', type=_positive_int, default=2, help='Local cyclic post-filter: minimum ring count / SSSR proxy (default: 2).')
    parser.add_argument('--cyclic-min-cyclic-atoms', type=_positive_int, default=9, help='Local cyclic post-filter: minimum cyclic atoms (default: 9).')

    parser.add_argument('--download-sdf', action='store_true', help='Download SDF records for final + reserve selections.')
    parser.add_argument('--sdf-record-type', default='', choices=('', '2d', '3d'), help='Optional PubChem SDF record_type query parameter.')
    parser.add_argument('--overwrite', action='store_true', help='Overwrite existing output files.')
    return parser


def _stable_seed_int(seed: int, label: str) -> int:
    digest = hashlib.sha256(f'{seed}|{label}'.encode('utf-8')).hexdigest()
    return int(digest[:16], 16)


def _stable_rank(seed: int, label: str, text: str) -> int:
    digest = hashlib.sha256(f'{seed}|{label}|{text}'.encode('utf-8')).hexdigest()
    return int(digest, 16)


def _request(
    url: str,
    *,
    params: dict[str, str],
    timeout: int,
    max_retries: int,
    rate_limiter: RateLimiter,
    tool: str,
    email: str,
) -> bytes:
    query = urllib.parse.urlencode({k: v for k, v in params.items() if v != ''})
    full_url = f'{url}?{query}' if query else url
    headers = {
        'User-Agent': f'{tool} ({email})',
        'Accept': '*/*',
    }
    last_exc: Exception | None = None
    for attempt in range(max_retries):
        try:
            rate_limiter.wait()
            req = urllib.request.Request(full_url, headers=headers)
            with urllib.request.urlopen(req, timeout=timeout) as response:
                return response.read()
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError) as exc:
            last_exc = exc
            backoff = min(30.0, 1.5 ** attempt)
            if attempt + 1 < max_retries:
                _log(
                    f'HTTP request failed ({attempt + 1}/{max_retries}) for {url} '
                    f'with {type(exc).__name__}: {exc}. Retrying in {backoff:.1f} s...'
                )
            time.sleep(backoff)
    raise RuntimeError(f'HTTP request failed after {max_retries} attempts: {full_url}') from last_exc


def esearch_count(
    term: str,
    *,
    timeout: int,
    max_retries: int,
    rate_limiter: RateLimiter,
    tool: str,
    email: str,
    api_key: str,
) -> int:
    payload = _request(
        ESEARCH_URL,
        params={
            'db': 'pccompound',
            'term': term,
            'retmode': 'json',
            'rettype': 'count',
            'retmax': '0',
            'tool': tool,
            'email': email,
            'api_key': api_key,
        },
        timeout=timeout,
        max_retries=max_retries,
        rate_limiter=rate_limiter,
        tool=tool,
        email=email,
    )
    data = json.loads(payload.decode('utf-8'))
    return int(data['esearchresult']['count'])


def esearch_ids(
    term: str,
    *,
    retstart: int,
    retmax: int,
    timeout: int,
    max_retries: int,
    rate_limiter: RateLimiter,
    tool: str,
    email: str,
    api_key: str,
) -> list[str]:
    payload = _request(
        ESEARCH_URL,
        params={
            'db': 'pccompound',
            'term': term,
            'retmode': 'json',
            'rettype': 'uilist',
            'retstart': str(retstart),
            'retmax': str(retmax),
            'tool': tool,
            'email': email,
            'api_key': api_key,
        },
        timeout=timeout,
        max_retries=max_retries,
        rate_limiter=rate_limiter,
        tool=tool,
        email=email,
    )
    data = json.loads(payload.decode('utf-8'))
    return list(data['esearchresult'].get('idlist', []))


def _chunked(items: Sequence[str], size: int) -> Iterable[list[str]]:
    for start in range(0, len(items), size):
        yield list(items[start:start + size])


def fetch_pubchem_properties(
    cids: Sequence[str],
    *,
    timeout: int,
    max_retries: int,
    rate_limiter: RateLimiter,
    tool: str,
    email: str,
) -> list[dict[str, str]]:
    if not cids:
        return []
    rows: list[dict[str, str]] = []
    prop_text = ','.join(PROPERTY_FIELDS)
    for chunk in _chunked(cids, 100):
        cid_text = ','.join(chunk)
        url = PUG_PROPERTY_URL_TEMPLATE.format(cid_text=cid_text, prop_text=prop_text)
        payload = _request(
            url,
            params={},
            timeout=timeout,
            max_retries=max_retries,
            rate_limiter=rate_limiter,
            tool=tool,
            email=email,
        )
        text = payload.decode('utf-8', errors='replace')
        reader = csv.DictReader(io.StringIO(text))
        rows.extend({k: (v or '') for k, v in row.items()} for row in reader)
    return rows


def _sssr_count(mol: Chem.Mol) -> int:
    try:
        value = Chem.GetSSSR(mol)
    except Exception:
        return int(mol.GetRingInfo().NumRings())
    if isinstance(value, int):
        return int(value)
    try:
        return len(value)
    except TypeError:
        return int(value)


def _pick_smiles_for_manifest(row: dict[str, str]) -> tuple[str, str, str, str]:
    connectivity = row.get('ConnectivitySMILES', '').strip()
    canonical = row.get('CanonicalSMILES', '').strip()
    isomeric = row.get('IsomericSMILES', '').strip()
    preferred = isomeric or canonical or connectivity
    return preferred, connectivity, canonical, isomeric


def _analyze_candidate(row: dict[str, str], *, stratum: StratumConfig, master_seed: int) -> tuple[CandidateRecord | None, str]:
    cid = row.get('CID', '').strip()
    preferred_smiles, connectivity, canonical, isomeric = _pick_smiles_for_manifest(row)
    formula = row.get('MolecularFormula', '').strip()
    if not cid:
        return None, 'missing_cid'
    if not preferred_smiles:
        return None, 'missing_smiles'

    mol = Chem.MolFromSmiles(preferred_smiles)
    if mol is None:
        return None, 'rdkit_parse_failed'

    elements = {atom.GetSymbol() for atom in mol.GetAtoms()}
    if not elements.issubset(ALLOWED_ELEMENTS):
        return None, 'disallowed_elements'

    if len(Chem.GetMolFrags(mol)) != 1:
        return None, 'multiple_fragments'

    net_charge = sum(atom.GetFormalCharge() for atom in mol.GetAtoms())
    if net_charge != 0:
        return None, 'local_net_charge_nonzero'

    if any(atom.GetNumRadicalElectrons() for atom in mol.GetAtoms()):
        return None, 'radical_electrons_present'

    heavy_atom_count = int(mol.GetNumHeavyAtoms())
    ring_count = _sssr_count(mol)
    cyclic_atoms = sum(1 for atom in mol.GetAtoms() if atom.IsInRing())
    aromatic_atoms = sum(1 for atom in mol.GetAtoms() if atom.GetIsAromatic())
    cyclic_non_aromatic_atoms = sum(1 for atom in mol.GetAtoms() if atom.IsInRing() and not atom.GetIsAromatic())

    if stratum.require_acyclic:
        if ring_count != 0:
            return None, 'not_acyclic_after_local_filter'
        class_label = 'acyclic'
    else:
        if ring_count < stratum.min_sssr:
            return None, 'ring_count_too_low'
        if cyclic_atoms < stratum.min_cyclic_atoms:
            return None, 'cyclic_atoms_too_low'
        class_label = 'cyclic'

    conn = connectivity or Chem.MolToSmiles(mol, canonical=True, isomericSmiles=False)
    rank = _stable_rank(master_seed, stratum.name, conn)
    return (
        CandidateRecord(
            cid=cid,
            connectivity_smiles=conn,
            smiles=preferred_smiles,
            canonical_smiles=canonical,
            isomeric_smiles=isomeric,
            molecular_formula=formula,
            heavy_atom_count=heavy_atom_count,
            ring_count=ring_count,
            cyclic_atoms=cyclic_atoms,
            aromatic_atoms=aromatic_atoms,
            cyclic_non_aromatic_atoms=cyclic_non_aromatic_atoms,
            class_label=class_label,
            hash_rank=rank,
        ),
        '',
    )


def sample_stratum(
    stratum: StratumConfig,
    *,
    seed: int,
    timeout: int,
    max_retries: int,
    rate_limiter: RateLimiter,
    tool: str,
    email: str,
    api_key: str,
    show_progress: bool,
    status_every_seconds: float,
) -> tuple[list[CandidateRecord], list[AuditRecord], dict[str, int | str]]:
    _log(f'[{stratum.name}] query: {stratum.query}')
    total_count = esearch_count(
        stratum.query,
        timeout=timeout,
        max_retries=max_retries,
        rate_limiter=rate_limiter,
        tool=tool,
        email=email,
        api_key=api_key,
    )
    if total_count <= 0:
        raise RuntimeError(f'PubChem search returned no candidates for stratum {stratum.name!r}: {stratum.query}')

    n_pages = math.ceil(total_count / stratum.page_size)
    if n_pages <= 0:
        raise RuntimeError(f'PubChem search returned an invalid page count for {stratum.name!r}')

    required_pool = stratum.target + stratum.reserve + stratum.oversample
    _log(
        f'[{stratum.name}] search hits={total_count:,}, pages={n_pages:,}, '
        f'need accepted pool={required_pool} (main={stratum.target}, reserve={stratum.reserve}, oversample={stratum.oversample})'
    )

    local_seed = _stable_seed_int(seed, stratum.name)
    rng = random.Random(local_seed)
    page_indices = list(range(n_pages))
    rng.shuffle(page_indices)

    accepted: list[CandidateRecord] = []
    seen_connectivity: set[str] = set()
    audit: list[AuditRecord] = []

    pages_checked = 0
    rejected_total = 0
    duplicate_total = 0
    progress = _make_progress(
        total=required_pool,
        desc=f'{stratum.name}:accepted_pool',
        unit='mol',
        show_progress=show_progress,
        status_every_seconds=status_every_seconds,
    )

    try:
        for page_index in page_indices:
            if len(accepted) >= required_pool:
                break
            retstart = page_index * stratum.page_size
            cid_list = esearch_ids(
                stratum.query,
                retstart=retstart,
                retmax=stratum.page_size,
                timeout=timeout,
                max_retries=max_retries,
                rate_limiter=rate_limiter,
                tool=tool,
                email=email,
                api_key=api_key,
            )
            props = fetch_pubchem_properties(
                cid_list,
                timeout=timeout,
                max_retries=max_retries,
                rate_limiter=rate_limiter,
                tool=tool,
                email=email,
            )
            page_accept = 0
            page_reject = 0
            page_duplicate = 0
            for row in props:
                rec, reason = _analyze_candidate(row, stratum=stratum, master_seed=seed)
                if rec is None:
                    rejected_total += 1
                    page_reject += 1
                    audit.append(
                        AuditRecord(
                            stratum=stratum.name,
                            page_index=page_index,
                            cid=row.get('CID', ''),
                            status='rejected',
                            reason=reason,
                            connectivity_smiles=row.get('ConnectivitySMILES', ''),
                            molecular_formula=row.get('MolecularFormula', ''),
                            heavy_atom_count=row.get('HeavyAtomCount', ''),
                            ring_count='',
                            cyclic_atoms='',
                        )
                    )
                    continue
                if rec.connectivity_smiles in seen_connectivity:
                    duplicate_total += 1
                    page_duplicate += 1
                    audit.append(
                        AuditRecord(
                            stratum=stratum.name,
                            page_index=page_index,
                            cid=rec.cid,
                            status='duplicate',
                            reason='connectivity_duplicate',
                            connectivity_smiles=rec.connectivity_smiles,
                            molecular_formula=rec.molecular_formula,
                            heavy_atom_count=str(rec.heavy_atom_count),
                            ring_count=str(rec.ring_count),
                            cyclic_atoms=str(rec.cyclic_atoms),
                        )
                    )
                    continue
                seen_connectivity.add(rec.connectivity_smiles)
                accepted.append(rec)
                page_accept += 1
                audit.append(
                    AuditRecord(
                        stratum=stratum.name,
                        page_index=page_index,
                        cid=rec.cid,
                        status='accepted_pool',
                        reason='',
                        connectivity_smiles=rec.connectivity_smiles,
                        molecular_formula=rec.molecular_formula,
                        heavy_atom_count=str(rec.heavy_atom_count),
                        ring_count=str(rec.ring_count),
                        cyclic_atoms=str(rec.cyclic_atoms),
                    )
                )
                progress.update(1)
                if len(accepted) >= required_pool:
                    break

            pages_checked += 1
            progress.set_postfix_str(
                f'pages={pages_checked}/{n_pages} last+={page_accept} last_rej={page_reject} '
                f'last_dup={page_duplicate} total_dup={duplicate_total} total_rej={rejected_total}'
            )
            progress.refresh()
    finally:
        progress.close()

    if len(accepted) < stratum.target + stratum.reserve:
        raise RuntimeError(
            f'Not enough accepted molecules for stratum {stratum.name!r}. '
            f'Needed at least {stratum.target + stratum.reserve}, got {len(accepted)} '
            f'after checking {pages_checked} / {n_pages} pages.'
        )

    accepted_sorted = sorted(accepted, key=lambda rec: (rec.hash_rank, rec.cid))
    selected_pool = accepted_sorted[: stratum.target + stratum.reserve]
    stats = {
        'name': stratum.name,
        'query': stratum.query,
        'total_search_count': total_count,
        'pages_available': n_pages,
        'pages_checked': pages_checked,
        'accepted_pool_size': len(accepted),
        'selected_pool_size': len(selected_pool),
        'target': stratum.target,
        'reserve': stratum.reserve,
        'oversample': stratum.oversample,
        'duplicates_seen': duplicate_total,
        'rejected_seen': rejected_total,
    }
    _log(
        f'[{stratum.name}] finished: accepted_pool={len(accepted)}, selected_pool={len(selected_pool)}, '
        f'pages_checked={pages_checked}/{n_pages}, duplicates={duplicate_total}, rejected={rejected_total}'
    )
    return selected_pool, audit, stats


def _ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def _write_csv(path: Path, rows: Sequence[dict[str, object]], *, overwrite: bool) -> None:
    if path.exists() and not overwrite:
        raise FileExistsError(f'Output file already exists: {path}. Pass --overwrite to replace it.')
    _ensure_parent(path)
    fieldnames: list[str] = []
    for row in rows:
        for key in row:
            if key not in fieldnames:
                fieldnames.append(key)
    with path.open('w', encoding='utf-8', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def _portable_relative(path: Path, base_dir: Path) -> str:
    return os.path.relpath(path.resolve(), start=base_dir.resolve())


def build_manifest_rows(
    records: Sequence[CandidateRecord],
    *,
    manifest_dir: Path,
    system_prefix: str,
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for index, rec in enumerate(records, start=1):
        system_key = f'{system_prefix}_{index:03d}'
        xyz_path = manifest_dir / 'structures' / f'{system_key}.xyz'
        molden_path = manifest_dir / 'molden' / f'{system_key}.molden'
        json_path = manifest_dir / 'qtaim' / f'{system_key}.json'
        rows.append(
            {
                'system_key': system_key,
                'name': f'CID{rec.cid}',
                'cid': rec.cid,
                'source': 'pubchem',
                'selection_stratum': rec.class_label,
                'connectivity_smiles': rec.connectivity_smiles,
                'smiles': rec.smiles,
                'canonical_smiles': rec.canonical_smiles,
                'isomeric_smiles': rec.isomeric_smiles,
                'molecular_formula': rec.molecular_formula,
                'heavy_atom_count': rec.heavy_atom_count,
                'ring_count': rec.ring_count,
                'cyclic_atoms': rec.cyclic_atoms,
                'aromatic_atoms': rec.aromatic_atoms,
                'cyclic_non_aromatic_atoms': rec.cyclic_non_aromatic_atoms,
                'charge': 0,
                'multiplicity': 1,
                'input_xyz_path': '',
                'xyz_path': _portable_relative(xyz_path, manifest_dir),
                'molden_path': _portable_relative(molden_path, manifest_dir),
                'json_path': _portable_relative(json_path, manifest_dir),
                'notes': '',
            }
        )
    return rows


def download_selected_sdfs(
    manifest_rows: Sequence[dict[str, object]],
    *,
    output_dir: Path,
    record_type: str,
    timeout: int,
    max_retries: int,
    rate_limiter: RateLimiter,
    tool: str,
    email: str,
    overwrite: bool,
    show_progress: bool,
    status_every_seconds: float,
) -> None:
    sdf_dir = output_dir / 'pubchem_sdf'
    sdf_dir.mkdir(parents=True, exist_ok=True)
    _log(f'[sdf] downloading up to {len(manifest_rows)} SDF files into {sdf_dir}')
    progress = _make_progress(
        total=len(manifest_rows),
        desc='pubchem_sdf',
        unit='file',
        show_progress=show_progress,
        status_every_seconds=status_every_seconds,
    )
    skipped = 0
    try:
        for row in manifest_rows:
            cid = str(row['cid'])
            system_key = str(row['system_key'])
            path = sdf_dir / f'{system_key}.sdf'
            if path.exists() and not overwrite:
                skipped += 1
                progress.update(1)
                progress.set_postfix_str(f'skipped={skipped} last={system_key}')
                progress.refresh()
                continue
            params = {'record_type': record_type} if record_type else {}
            payload = _request(
                PUG_SDF_URL_TEMPLATE.format(cid=cid),
                params=params,
                timeout=timeout,
                max_retries=max_retries,
                rate_limiter=rate_limiter,
                tool=tool,
                email=email,
            )
            path.write_bytes(payload)
            progress.update(1)
            progress.set_postfix_str(f'skipped={skipped} last={system_key}')
            progress.refresh()
    finally:
        progress.close()
    _log(f'[sdf] finished: files={len(manifest_rows)}, skipped={skipped}, dir={sdf_dir}')


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.acyclic_min_heavy > args.acyclic_max_heavy:
        raise SystemExit('Acyclic heavy-atom window is invalid: min > max.')
    if args.cyclic_min_heavy > args.cyclic_max_heavy:
        raise SystemExit('Cyclic heavy-atom window is invalid: min > max.')

    output_dir = args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    for subdir in ('structures', 'molden', 'qtaim', 'multiwfn_raw'):
        (output_dir / subdir).mkdir(parents=True, exist_ok=True)

    manifest_path = output_dir / 'systems.csv'
    reserve_path = output_dir / 'systems_reserve.csv'
    audit_path = output_dir / 'selection_audit.csv'
    reject_path = output_dir / 'selection_rejections.csv'
    meta_path = output_dir / 'selection_metadata.json'

    rate_limiter = RateLimiter(args.sleep_with_key if args.api_key else args.sleep_no_key)

    acyclic_query = f'0[CHG] AND 1[CUC] AND {args.acyclic_min_heavy}:{args.acyclic_max_heavy}[HAC]'
    cyclic_query = f'0[CHG] AND 1[CUC] AND {args.cyclic_min_heavy}:{args.cyclic_max_heavy}[HAC]'

    _log('Starting PubChem main-set selection')
    _log(f'Output directory: {output_dir}')
    _log(f'Seed: {args.seed}')
    _log(
        f'Acyclic target/reserve/oversample: {args.n_acyclic}/{args.reserve_per_class}/{args.oversample_per_class} '
        f'with heavy-atom window {args.acyclic_min_heavy}:{args.acyclic_max_heavy}'
    )
    _log(
        f'Cyclic target/reserve/oversample: {args.n_cyclic}/{args.reserve_per_class}/{args.oversample_per_class} '
        f'with heavy-atom window {args.cyclic_min_heavy}:{args.cyclic_max_heavy}, '
        f'min_sssr={args.cyclic_min_sssr}, min_cyclic_atoms={args.cyclic_min_cyclic_atoms}'
    )
    if args.no_progress:
        _log('Progress bars disabled (--no-progress); using milestone prints only.')
    elif _tqdm is None:
        _log('tqdm is not available; falling back to periodic text progress messages.')

    acyclic_cfg = StratumConfig(
        name='acyclic',
        query=acyclic_query,
        target=args.n_acyclic,
        reserve=args.reserve_per_class,
        oversample=args.oversample_per_class,
        page_size=args.page_size,
        min_sssr=0,
        min_cyclic_atoms=0,
        require_acyclic=True,
        system_prefix='acyclic_pubchem',
    )
    cyclic_cfg = StratumConfig(
        name='cyclic',
        query=cyclic_query,
        target=args.n_cyclic,
        reserve=args.reserve_per_class,
        oversample=args.oversample_per_class,
        page_size=args.page_size,
        min_sssr=args.cyclic_min_sssr,
        min_cyclic_atoms=args.cyclic_min_cyclic_atoms,
        require_acyclic=False,
        system_prefix='cyclic_pubchem',
    )

    acyclic_pool, acyclic_audit, acyclic_stats = sample_stratum(
        acyclic_cfg,
        seed=args.seed,
        timeout=args.request_timeout,
        max_retries=args.max_retries,
        rate_limiter=rate_limiter,
        tool=args.tool,
        email=args.email,
        api_key=args.api_key,
        show_progress=not args.no_progress,
        status_every_seconds=args.status_every_seconds,
    )
    cyclic_pool, cyclic_audit, cyclic_stats = sample_stratum(
        cyclic_cfg,
        seed=args.seed,
        timeout=args.request_timeout,
        max_retries=args.max_retries,
        rate_limiter=rate_limiter,
        tool=args.tool,
        email=args.email,
        api_key=args.api_key,
        show_progress=not args.no_progress,
        status_every_seconds=args.status_every_seconds,
    )

    acyclic_selected = acyclic_pool[: args.n_acyclic]
    acyclic_reserve = acyclic_pool[args.n_acyclic : args.n_acyclic + args.reserve_per_class]
    cyclic_selected = cyclic_pool[: args.n_cyclic]
    cyclic_reserve = cyclic_pool[args.n_cyclic : args.n_cyclic + args.reserve_per_class]

    manifest_rows = build_manifest_rows(acyclic_selected, manifest_dir=output_dir, system_prefix=acyclic_cfg.system_prefix)
    manifest_rows += build_manifest_rows(cyclic_selected, manifest_dir=output_dir, system_prefix=cyclic_cfg.system_prefix)

    reserve_rows = build_manifest_rows(acyclic_reserve, manifest_dir=output_dir, system_prefix='acyclic_pubchem_reserve')
    reserve_rows += build_manifest_rows(cyclic_reserve, manifest_dir=output_dir, system_prefix='cyclic_pubchem_reserve')

    _write_csv(manifest_path, manifest_rows, overwrite=args.overwrite)
    _write_csv(reserve_path, reserve_rows, overwrite=args.overwrite)

    audit_rows = [asdict(row) for row in (acyclic_audit + cyclic_audit)]
    _write_csv(audit_path, audit_rows, overwrite=args.overwrite)
    reject_rows = [row for row in audit_rows if row['status'] != 'accepted_pool']
    _write_csv(reject_path, reject_rows, overwrite=args.overwrite)

    metadata = {
        'created_utc': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
        'tool': args.tool,
        'email': args.email,
        'api_key_used': bool(args.api_key),
        'seed': args.seed,
        'page_size': args.page_size,
        'allowed_elements': sorted(ALLOWED_ELEMENTS),
        'property_fields': list(PROPERTY_FIELDS),
        'selection': {
            'acyclic': acyclic_stats,
            'cyclic': cyclic_stats,
        },
        'manifest_path': str(manifest_path),
        'reserve_path': str(reserve_path),
        'audit_path': str(audit_path),
        'rejections_path': str(reject_path),
    }
    if meta_path.exists() and not args.overwrite:
        raise FileExistsError(f'Output file already exists: {meta_path}. Pass --overwrite to replace it.')
    meta_path.write_text(json.dumps(metadata, indent=2, sort_keys=True), encoding='utf-8')

    if args.download_sdf:
        download_selected_sdfs(
            manifest_rows + reserve_rows,
            output_dir=output_dir,
            record_type=args.sdf_record_type,
            timeout=args.request_timeout,
            max_retries=args.max_retries,
            rate_limiter=rate_limiter,
            tool=args.tool,
            email=args.email,
            overwrite=args.overwrite,
            show_progress=not args.no_progress,
            status_every_seconds=args.status_every_seconds,
        )

    _log(f'Wrote main manifest:    {manifest_path}')
    _log(f'Wrote reserve manifest: {reserve_path}')
    _log(f'Wrote audit log:        {audit_path}')
    _log(f'Wrote rejection log:    {reject_path}')
    _log(f'Wrote metadata:         {meta_path}')
    if args.download_sdf:
        _log(f'Downloaded SDF files to: {output_dir / "pubchem_sdf"}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
