# -*- coding: utf-8 -*-
"""Update RST - pulls latest via git, or downloads zip from GitHub as fallback."""
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

# ── Download zip from GitHub and copy directly ───────────────────────────────
pulled = False
result_msg = ''
_zip_error = ''
if not pulled:
    log.info('Git not available — downloading zip from GitHub')
    staging_dir = None
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

        # 1. Preserve user data
        _preserve = ['app/active_profile.json', 'app/profiles', 'rst.log',
                      'icons/branding.png', 'lookup/config.json',
                      'app/custom_tools.json', 'app/panel_colors.json']
        preserve_dir = os.path.join(staging_dir, 'preserve')
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

        # 2. Wipe install dir (skip .git, skip locked files)
        _skip_root = {'.git', 'rst.log'}
        for item in os.listdir(_root):
            if item in _skip_root:
                continue
            item_path = os.path.join(_root, item)
            try:
                if os.path.isdir(item_path):
                    # Walk bottom-up, skip locked files
                    for dp, dns, fns in os.walk(item_path, topdown=False):
                        for fn in fns:
                            try:
                                os.remove(os.path.join(dp, fn))
                            except (OSError, IOError):
                                pass
                        for dn in dns:
                            try:
                                os.rmdir(os.path.join(dp, dn))
                            except (OSError, IOError):
                                pass
                    try:
                        os.rmdir(item_path)
                    except OSError:
                        pass
                else:
                    os.remove(item_path)
            except (OSError, IOError) as e:
                log.warning('Could not remove %s: %s', item, e)

        # 3. Copy new files (skip locked)
        skipped = []
        for dp, dns, fns in os.walk(source_dir):
            rel_dir = os.path.relpath(dp, source_dir)
            target_dir = os.path.join(_root, rel_dir) if rel_dir != '.' else _root
            if not os.path.exists(target_dir):
                os.makedirs(target_dir)
            for fn in fns:
                try:
                    shutil.copy2(os.path.join(dp, fn), os.path.join(target_dir, fn))
                except (OSError, IOError):
                    skipped.append(fn)

        # 4. Restore user data (skip locked)
        if os.path.exists(preserve_dir):
            for dp, dns, fns in os.walk(preserve_dir):
                rel_dir = os.path.relpath(dp, preserve_dir)
                target_dir = os.path.join(_root, rel_dir) if rel_dir != '.' else _root
                if not os.path.exists(target_dir):
                    os.makedirs(target_dir)
                for fn in fns:
                    try:
                        shutil.copy2(os.path.join(dp, fn), os.path.join(target_dir, fn))
                    except (OSError, IOError):
                        pass

        # Cleanup staging
        shutil.rmtree(staging_dir, ignore_errors=True)

        if skipped:
            log.warning('Skipped locked files: %s', skipped)
        result_msg = 'updated'
        pulled = True
        log.info('Updated from GitHub zip (direct copy)')

    except Exception as e:
        log.error('Zip download failed: %s', e)
        import traceback
        log.error(traceback.format_exc())
        _zip_error = str(e)
        if staging_dir:
            shutil.rmtree(staging_dir, ignore_errors=True)

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
    log.info('Update complete, reloading pyRevit...')
    from reload_ui import reload_with_message
    reload_with_message()
