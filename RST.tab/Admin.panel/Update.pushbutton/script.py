# -*- coding: utf-8 -*-
"""Update RST - pulls latest via git, or downloads zip from GitHub as fallback."""
import io
import os
import sys
import subprocess
import shutil
import zipfile
import tempfile

_script_dir = os.path.dirname(os.path.abspath(__file__))
_root = os.path.join(_script_dir, '..', '..', '..')
_root = os.path.normpath(_root)

sys.path.insert(0, os.path.join(_root, 'app'))
from logger import get_logger
log = get_logger('update')

from pyrevit import forms

REPO_ZIP_URL = 'https://github.com/jedbjorn/RST/archive/refs/heads/main.zip'

log.info('Updating RST from %s', _root)

# ── Try pyRevit's git first ──────────────────────────────────────────────────
pulled = False
result_msg = ''

try:
    from pyrevit.coreutils import git
    repo = git.get_repo(_root)
    if repo:
        log.info('Using pyRevit git')
        head_before = str(repo.last_commit_hash)
        repo.fetch('origin')
        repo.merge('origin/main')
        head_after = str(repo.last_commit_hash)
        if head_before == head_after:
            result_msg = 'already_up_to_date'
        else:
            result_msg = 'updated'
        pulled = True
except Exception as e:
    log.warning('pyRevit git failed: %s', e)

# ── Try system git ────────────────────────────────────────────────────────────
if not pulled:
    git_paths = [
        'git',
        r'C:\Program Files\Git\cmd\git.exe',
        r'C:\Program Files\Git\bin\git.exe',
        r'C:\Program Files (x86)\Git\cmd\git.exe',
        os.path.join(os.environ.get('LOCALAPPDATA', ''), 'Programs', 'Git', 'cmd', 'git.exe'),
    ]
    for git_cmd in git_paths:
        try:
            out = subprocess.check_output(
                [git_cmd, 'pull'],
                cwd=_root,
                stderr=subprocess.STDOUT
            )
            out_str = out.decode('utf-8', errors='replace').strip()
            log.info('Git pull: %s', out_str)
            if 'Already up' in out_str:
                result_msg = 'already_up_to_date'
            else:
                result_msg = 'updated'
            pulled = True
            break
        except Exception:
            continue

# ── Fallback: download zip from GitHub ────────────────────────────────────────
if not pulled:
    log.info('Git not available — downloading zip from GitHub')
    try:
        if sys.version_info[0] >= 3:
            from urllib.request import urlopen
        else:
            from urllib2 import urlopen

        tmp_dir = tempfile.mkdtemp(prefix='rst_update_')
        zip_path = os.path.join(tmp_dir, 'rst.zip')

        # Download
        log.info('Downloading %s', REPO_ZIP_URL)
        import ssl
        ctx = ssl.create_default_context()
        resp = urlopen(REPO_ZIP_URL, timeout=30, context=ctx)
        with open(zip_path, 'wb') as f:
            while True:
                chunk = resp.read(65536)
                if not chunk:
                    break
                f.write(chunk)
        resp.close()
        log.info('Downloaded %d bytes', os.path.getsize(zip_path))

        # Extract
        extract_dir = os.path.join(tmp_dir, 'extracted')
        with zipfile.ZipFile(zip_path, 'r') as zf:
            zf.extractall(extract_dir)

        # GitHub zips contain a top-level folder like RST-main/
        entries = os.listdir(extract_dir)
        if len(entries) == 1 and os.path.isdir(os.path.join(extract_dir, entries[0])):
            source_dir = os.path.join(extract_dir, entries[0])
        else:
            source_dir = extract_dir

        # 1. Preserve user data
        _preserve = ['app/active_profile.json', 'app/profiles', 'rester.log']
        preserve_dir = os.path.join(tmp_dir, 'preserve')
        for rel in _preserve:
            src = os.path.join(_root, rel)
            if os.path.exists(src):
                bak = os.path.join(preserve_dir, rel)
                bak_parent = os.path.dirname(bak)
                if not os.path.exists(bak_parent):
                    os.makedirs(bak_parent)
                if os.path.isdir(src):
                    shutil.copytree(src, bak)
                else:
                    shutil.copy2(src, bak)

        # 2. Wipe install dir (except .git, skip locked files)
        _skip_root = {'.git', 'rester.log'}
        def _safe_rmtree(path):
            """Remove a directory tree, skipping any locked files."""
            for dirpath, dirnames, filenames in os.walk(path, topdown=False):
                for fn in filenames:
                    fp = os.path.join(dirpath, fn)
                    try:
                        os.remove(fp)
                    except OSError as e:
                        log.warning('Locked file, skipping: %s (%s)', fp, e)
                for dn in dirnames:
                    dp = os.path.join(dirpath, dn)
                    try:
                        os.rmdir(dp)
                    except OSError:
                        pass  # not empty due to locked files
            try:
                os.rmdir(path)
            except OSError:
                pass

        for item in os.listdir(_root):
            if item in _skip_root:
                continue
            item_path = os.path.join(_root, item)
            try:
                if os.path.isdir(item_path):
                    _safe_rmtree(item_path)
                else:
                    os.remove(item_path)
            except OSError as e:
                log.warning('Could not remove %s: %s (skipping)', item, e)

        # 3. Install new files from zip
        for dirpath, dirnames, filenames in os.walk(source_dir):
            rel_dir = os.path.relpath(dirpath, source_dir)
            target_dir = os.path.join(_root, rel_dir) if rel_dir != '.' else _root
            if not os.path.exists(target_dir):
                os.makedirs(target_dir)
            for fn in filenames:
                shutil.copy2(
                    os.path.join(dirpath, fn),
                    os.path.join(target_dir, fn),
                )

        # 4. Restore user data
        for dirpath, dirnames, filenames in os.walk(preserve_dir):
            rel_dir = os.path.relpath(dirpath, preserve_dir)
            target_dir = os.path.join(_root, rel_dir) if rel_dir != '.' else _root
            if not os.path.exists(target_dir):
                os.makedirs(target_dir)
            for fn in filenames:
                shutil.copy2(
                    os.path.join(dirpath, fn),
                    os.path.join(target_dir, fn),
                )

        # Cleanup temp
        shutil.rmtree(tmp_dir, ignore_errors=True)

        result_msg = 'updated'
        pulled = True
        log.info('Updated from GitHub zip')

    except Exception as e:
        log.error('Zip download failed: %s', e)
        import traceback
        log.error(traceback.format_exc())
        _zip_error = str(e)
        try:
            shutil.rmtree(tmp_dir, ignore_errors=True)
        except Exception:
            pass

# ── Result ────────────────────────────────────────────────────────────────────
if not pulled:
    err_detail = _zip_error if '_zip_error' in dir() else 'Git not available'
    forms.alert(
        'Could not update RST.\n\n%s' % err_detail,
        title='RST Update'
    )
elif result_msg == 'already_up_to_date':
    forms.alert('RST is already up to date.', title='RST Update')
else:
    log.info('Update complete, reloading pyRevit...')
    reloaded = False
    # Try pyRevit internal reload first (we're running inside Revit)
    try:
        from pyrevit.loader import sessionmgr
        sessionmgr.reload()
        reloaded = True
    except Exception as e:
        log.warning('sessionmgr.reload() failed: %s', e)
    # Fallback to CLI
    if not reloaded:
        cli_candidates = []
        appdata = os.environ.get('APPDATA', '')
        if appdata:
            cli_candidates.append(os.path.join(appdata, 'pyRevit-Master', 'bin', 'pyrevit.exe'))
            cli_candidates.append(os.path.join(appdata, 'pyRevit', 'bin', 'pyrevit.exe'))
        cli_candidates.append('pyrevit')
        CREATE_NO_WINDOW = 0x08000000
        for cli in cli_candidates:
            try:
                subprocess.Popen(
                    [cli, 'reload'],
                    creationflags=CREATE_NO_WINDOW,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                log.info('pyRevit reload triggered via CLI: %s', cli)
                reloaded = True
                break
            except Exception:
                continue
    if not reloaded:
        forms.alert('Updated. Please reload pyRevit manually.', title='RST Update')
