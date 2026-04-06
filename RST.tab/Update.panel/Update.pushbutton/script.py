# -*- coding: utf-8 -*-
"""Update RST - downloads update, stages it, reloads pyRevit to unlock files,
then a background script applies the update."""
__title__ = 'Update'
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

# ── Fallback: download zip, stage, then apply after pyRevit reload ───────────
_zip_error = ''
if not pulled:
    log.info('Git not available — downloading zip from GitHub')
    try:
        if sys.version_info[0] >= 3:
            from urllib.request import urlopen
        else:
            from urllib2 import urlopen

        staging_dir = os.path.join(os.environ.get('TEMP', tempfile.gettempdir()), 'rst_update')
        if os.path.exists(staging_dir):
            shutil.rmtree(staging_dir, ignore_errors=True)
        os.makedirs(staging_dir)

        zip_path = os.path.join(staging_dir, 'rst.zip')

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
        extract_dir = os.path.join(staging_dir, 'extracted')
        with zipfile.ZipFile(zip_path, 'r') as zf:
            zf.extractall(extract_dir)

        # Find source dir inside zip
        entries = os.listdir(extract_dir)
        if len(entries) == 1 and os.path.isdir(os.path.join(extract_dir, entries[0])):
            source_dir = os.path.join(extract_dir, entries[0])
        else:
            source_dir = extract_dir

        # Preserve user data to staging
        preserve_dir = os.path.join(staging_dir, 'preserve')
        _preserve = ['app/active_profile.json', 'app/profiles', 'rester.log',
                      'icons/branding.png']
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

        # Write a batch script that applies the update after pyRevit releases locks
        apply_bat = os.path.join(staging_dir, 'apply_update.bat')
        with open(apply_bat, 'w') as f:
            f.write('@echo off\r\n')
            f.write('echo RST Update: waiting for pyRevit to release files...\r\n')
            f.write('timeout /t 5 /nobreak >nul\r\n')
            f.write('echo RST Update: applying...\r\n')
            # Wipe install dir (except .git and rester.log)
            f.write('for /d %%D in ("%s\\*") do (\r\n' % _root)
            f.write('  if /i not "%%~nxD"==".git" (\r\n')
            f.write('    rmdir /s /q "%%D" 2>nul\r\n')
            f.write('  )\r\n')
            f.write(')\r\n')
            f.write('for %%F in ("%s\\*") do (\r\n' % _root)
            f.write('  if /i not "%%~nxF"=="rester.log" (\r\n')
            f.write('    del /q "%%F" 2>nul\r\n')
            f.write('  )\r\n')
            f.write(')\r\n')
            # Copy new files
            f.write('xcopy "%s\\*" "%s\\" /e /y /q\r\n' % (source_dir, _root))
            # Restore user data
            f.write('if exist "%s" (\r\n' % preserve_dir)
            f.write('  xcopy "%s\\*" "%s\\" /e /y /q\r\n' % (preserve_dir, _root))
            f.write(')\r\n')
            # Cleanup staging
            f.write('echo RST Update: done. Reload pyRevit to complete.\r\n')
            f.write('timeout /t 2 /nobreak >nul\r\n')
            f.write('rmdir /s /q "%s" 2>nul\r\n' % staging_dir)

        # Launch the batch script in background (hidden window)
        CREATE_NO_WINDOW = 0x08000000
        subprocess.Popen(
            ['cmd', '/c', apply_bat],
            creationflags=CREATE_NO_WINDOW,
        )
        log.info('Staged update and launched apply script')

        result_msg = 'staged'
        pulled = True

    except Exception as e:
        log.error('Zip download failed: %s', e)
        import traceback
        log.error(traceback.format_exc())
        _zip_error = str(e)
        try:
            if 'staging_dir' in dir():
                shutil.rmtree(staging_dir, ignore_errors=True)
        except Exception:
            pass

# ── Result ────────────────────────────────────────────────────────────────────
if not pulled:
    err_detail = _zip_error or 'Git not available'
    forms.alert(
        'Could not update RST.\n\n%s' % err_detail,
        title='RST Update'
    )
elif result_msg == 'already_up_to_date':
    forms.alert('RST is already up to date.', title='RST Update')
else:
    # For git updates, reload immediately
    if result_msg == 'updated':
        log.info('Git update complete, reloading pyRevit...')
        try:
            from pyrevit.loader import sessionmgr
            sessionmgr.reload()
        except Exception as e:
            log.warning('Reload failed: %s', e)
            forms.alert('Updated. Please reload pyRevit manually.', title='RST Update')
    # For staged zip updates, reload pyRevit to release locks, then batch script takes over
    elif result_msg == 'staged':
        forms.alert(
            'Update downloaded. pyRevit will reload now to apply.\n\n'
            'After reload, click Update again if the RST tab looks unchanged.',
            title='RST Update'
        )
        try:
            from pyrevit.loader import sessionmgr
            sessionmgr.reload()
        except Exception as e:
            log.warning('Reload failed: %s', e)
