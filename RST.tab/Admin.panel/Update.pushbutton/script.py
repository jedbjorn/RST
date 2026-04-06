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
    """Find git executable - system git or pyRevit's bundled git."""
    # Try system git first
    try:
        subprocess.check_output(['git', '--version'], stderr=subprocess.STDOUT)
        return 'git'
    except Exception:
        pass

    # Try pyRevit's bundled git
    try:
        from pyrevit.coreutils import git as pyrevit_git
        return None  # use pyRevit's git module instead
    except Exception:
        pass

    # Search common locations
    for path in [
        r'C:\Program Files\Git\bin\git.exe',
        r'C:\Program Files (x86)\Git\bin\git.exe',
        os.path.join(os.environ.get('LOCALAPPDATA', ''), 'Programs', 'Git', 'bin', 'git.exe'),
    ]:
        if os.path.exists(path):
            return path

    return None


def pull_with_system_git(git_cmd):
    """Pull using system/found git executable."""
    result = subprocess.check_output(
        [git_cmd, 'pull'],
        cwd=_root,
        stderr=subprocess.STDOUT,
        text=True
    )
    return result.strip()


def pull_with_pyrevit_git():
    """Pull using pyRevit's built-in git module."""
    from pyrevit.coreutils import git
    repo = git.get_repo(_root)
    if repo:
        repo.git.pull()
        return 'Pulled via pyRevit git'
    return None


log.info('Updating RST...')
try:
    git_cmd = find_git()
    result = None

    if git_cmd:
        log.info('Using git: %s', git_cmd)
        result = pull_with_system_git(git_cmd)
    else:
        log.info('No system git, trying pyRevit git...')
        try:
            result = pull_with_pyrevit_git()
        except Exception as e:
            log.error('pyRevit git failed: %s', e)

    if result is None:
        from pyrevit import forms
        forms.alert('Could not find git. Install Git for Windows or update manually.', title='RST Update')
    elif 'Already up to date' in result or 'up-to-date' in result.lower():
        from pyrevit import forms
        forms.alert('RST is already up to date.', title='RST Update')
    else:
        log.info('Update result: %s', result)
        log.info('Reloading pyRevit...')
        try:
            from pyrevit.loader import sessionmgr
            sessionmgr.reload()
        except Exception as e:
            log.error('Reload failed: %s', e)
            from pyrevit import forms
            forms.alert('Updated successfully. Please reload pyRevit manually.', title='RST Update')

except Exception as e:
    log.error('Update failed: %s', e)
    try:
        from pyrevit import forms
        forms.alert('Update failed: ' + str(e), title='RST Update Error')
    except Exception:
        pass
