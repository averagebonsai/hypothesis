"""Install one checksum-pinned native Muse release during the image build."""
import hashlib
import json
import platform
import shutil
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import urlopen

release = json.loads(Path('/opt/toolkit/docker/muse-release.json').read_text())
artifact = release['artifacts'][platform.machine()]
url = 'https://lookaside.facebook.com/lookaside/muse/download/?' + urlencode({
    'channel': 'muse', 'version': release['version'], 'file': artifact['file'],
})
cache = Path('/var/cache/muse')
cache.mkdir(parents=True, exist_ok=True)
cached = cache / artifact['sha256']
if not cached.is_file() or hashlib.file_digest(cached.open('rb'), 'sha256').hexdigest() != artifact['sha256']:
    temporary = cache / (artifact['sha256'] + '.download')
    digest = hashlib.sha256()
    size = 0
    with urlopen(url, timeout=180) as response, temporary.open('wb') as stream:
        while chunk := response.read(1024 * 1024):
            size += len(chunk)
            if size > 500_000_000:
                raise RuntimeError('Muse binary exceeds expected download budget')
            digest.update(chunk)
            stream.write(chunk)
    if digest.hexdigest() != artifact['sha256']:
        temporary.unlink()
        raise RuntimeError('Muse release checksum mismatch')
    temporary.replace(cached)
target = Path('/usr/local/bin/muse')
shutil.copyfile(cached, target)
target.chmod(0o755)
print('Installed Muse', release['version'], 'SHA256', artifact['sha256'], flush=True)
