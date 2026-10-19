"""Archive candidates before atomically replacing the single verified ZIP."""
from datetime import datetime, timezone
import hashlib
import os
from pathlib import Path
import shutil
import subprocess
import tempfile


def release_id(root):
    revision = subprocess.check_output(['git', 'rev-parse', '--short=12', 'HEAD'], cwd=root, text=True).strip()
    dirty = bool(subprocess.check_output(['git', 'status', '--porcelain'], cwd=root).strip())
    return datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ') + '-' + revision + ('-dirty' if dirty else '')


def promote(root, candidate, report, validate):
    root, candidate = Path(root).resolve(), Path(candidate).resolve()
    if not candidate.is_relative_to(root / 'build/history') or candidate.name != 'ArcaneVaults-NG.zip':
        raise ValueError('Promotion requires a candidate from build/history/')
    checksum = hashlib.sha256(candidate.read_bytes()).hexdigest()
    if not report.get('complete') or not report.get('passed') or report.get('zip_sha256') != checksum:
        raise ValueError('Incomplete, failed or stale release verification')
    validate(root, candidate)
    destination = root / 'build/ArcaneVaults-NG.zip'
    with tempfile.NamedTemporaryFile(dir=destination.parent, prefix='.verified-', suffix='.zip', delete=False) as stream:
        temporary = Path(stream.name)
        try:
            with candidate.open('rb') as source:
                shutil.copyfileobj(source, stream)
            stream.flush()
            os.fsync(stream.fileno())
        except BaseException:
            temporary.unlink(missing_ok=True)
            raise
    try:
        if hashlib.sha256(temporary.read_bytes()).hexdigest() != checksum:
            raise ValueError('Candidate changed during promotion')
        os.replace(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)
    return destination
