# -*- coding: utf-8 -*-
"""Update RST - pulls latest from git and reloads pyRevit."""
import os
import sys
import subprocess

_script_dir = os.path.dirname(os.path.abspath(__file__))
_root = os.path.join(_script_dir, '..', '..', '..')
_root = os.path.normpath(_root)

sys.path.insert(0, os.path.join(_root, 'app'))
from logger import get_logger
log = get_logger('update')


def find_git():
    """Find git executable."""
    # Try system git
    try:
        subprocess.check_output(['git', '--version'], stderr=subprocess.STDOUT)
        return 'git'
    except Exception:
        pass

    # Common install locations
    candidates = [
        r'C:\Program Files\Git\cmd\git.exe',
        r'C:\Program Files\Git\bin\git.exe',
        r'C:\Program Files (x86)\Git\cmd\git.exe',
        r'C:\Program Files (x86)\Git\bin\git.exe',
        os.path.join(os.environ.get('LOCALAPPDATA', ''), 'Programs', 'Git', 'cmd', 'git.exe'),
        os.path.join(os.environ.get('LOCALAPPDATA', ''), 'Programs', 'Git', 'bin', 'git.exe'),
    ]

    # pyRevit may bundle git
    pyrevit_git = os.path.join(os.environ.get('APPDATA', ''), 'pyRevit', 'bin', 'git.exe')
    candidates.append(pyrevit_git)

    for path in candidates:
        if os.path.exists(path):
            log.info('Found git at: %s', path)
            return path

    return None


log.info('Updating RST...')

git_cmd = find_git()

if not git_cmd:
    log.error('Git not found')
    # Try using pyRevit's extension manager as fallback
    try:
        from pyrevit import forms
        forms.alert(
            'Git not found. To update RST:\n\n'
            '1. Install Git for Windows from git-scm.com\n'
            '2. Restart Revit\n'
            '3. Click Update again\n\n'
            'Or update manually via pyRevit Extensions Manager.',
            title='RST Update'
        )
    except Exception:
        pass
else:
    try:
        result = subprocess.check_output(
            [git_cmd, 'pull'],
            cwd=_root,
            stderr=subprocess.STDOUT
        )
        result_str = result.decode('utf-8', errors='replace').strip()
        log.info('Git pull: %s', result_str)

        if 'Already up' in result_str:
            try:
                from pyrevit import forms
                forms.alert('RST is already up to date.', title='RST Update')
            except Exception:
                pass
        else:
            log.info('Update found, reloading pyRevit...')
            try:
                from pyrevit.loader import sessionmgr
                sessionmgr.reload()
            except Exception as e:
                log.error('Reload failed: %s', e)
                try:
                    from pyrevit import forms
                    forms.alert('Updated. Please reload pyRevit manually.', title='RST Update')
                except Exception:
                    pass

    except subprocess.CalledProcessError as e:
        log.error('Git pull failed: %s', e)
        try:
            from pyrevit import forms
            forms.alert('Update failed:\n\n' + str(e), title='RST Update Error')
        except Exception:
            pass
    except Exception as e:
        log.error('Update failed: %s', e)
        try:
            from pyrevit import forms
            forms.alert('Update failed: ' + str(e), title='RST Update Error')
        except Exception:
            pass
