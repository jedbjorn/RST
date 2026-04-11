# -*- coding: utf-8 -*-
"""
health_scanner.py — System health snapshot for RST_Pro.

Captures hardware, OS, and Revit session data at a point in time.
Currently runs at load; future: runs when a Revit model is opened.

Uses stdlib only (ctypes, winreg, shutil, platform, subprocess).
One PowerShell call gathers all WMI-dependent data (GPU, network,
disk type, monitors) to minimize overhead.
"""

import ctypes
import json
import logging
import os
import platform
import shutil
import socket
import subprocess
from datetime import datetime, timezone

log = logging.getLogger('rst')


# ── RAM ──────────────────────────────────────────────────────────────────────

class _MEMORYSTATUSEX(ctypes.Structure):
    _fields_ = [
        ('dwLength',                ctypes.c_ulong),
        ('dwMemoryLoad',            ctypes.c_ulong),
        ('ullTotalPhys',            ctypes.c_ulonglong),
        ('ullAvailPhys',            ctypes.c_ulonglong),
        ('ullTotalPageFile',        ctypes.c_ulonglong),
        ('ullAvailPageFile',        ctypes.c_ulonglong),
        ('ullTotalVirtual',         ctypes.c_ulonglong),
        ('ullAvailVirtual',         ctypes.c_ulonglong),
        ('ullAvailExtendedVirtual', ctypes.c_ulonglong),
    ]


def _get_ram():
    """Return RAM info in MB via GlobalMemoryStatusEx."""
    try:
        mem = _MEMORYSTATUSEX()
        mem.dwLength = ctypes.sizeof(_MEMORYSTATUSEX)
        ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(mem))
        total_mb = round(mem.ullTotalPhys / (1024 * 1024))
        avail_mb = round(mem.ullAvailPhys / (1024 * 1024))
        return {
            'totalMB':     total_mb,
            'availableMB': avail_mb,
            'usedMB':      total_mb - avail_mb,
            'usedPercent':  mem.dwMemoryLoad,
        }
    except Exception as e:
        log.warning('Failed to read RAM info: %s', e)
        return {'totalMB': None, 'availableMB': None, 'usedMB': None, 'usedPercent': None}


# ── CPU ──────────────────────────────────────────────────────────────────────

def _get_cpu():
    """Return CPU info from registry and os module."""
    import winreg
    name = ''
    try:
        key = winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE,
            r"HARDWARE\DESCRIPTION\System\CentralProcessor\0"
        )
        name, _ = winreg.QueryValueEx(key, "ProcessorNameString")
        winreg.CloseKey(key)
        name = name.strip()
    except OSError:
        pass

    logical_cores = os.cpu_count() or 0

    # Physical cores: count processor subkeys
    physical_cores = 0
    try:
        key = winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE,
            r"HARDWARE\DESCRIPTION\System\CentralProcessor"
        )
        i = 0
        while True:
            try:
                winreg.EnumKey(key, i)
                physical_cores += 1
                i += 1
            except OSError:
                break
        winreg.CloseKey(key)
    except OSError:
        physical_cores = logical_cores

    return {
        'name':          name,
        'logicalCores':  logical_cores,
        'physicalCores': physical_cores,
    }


# ── Disk ─────────────────────────────────────────────────────────────────────

def _get_disk():
    """Return C: drive usage via shutil."""
    try:
        usage = shutil.disk_usage('C:\\')
        total_gb = round(usage.total / (1024 ** 3), 1)
        free_gb = round(usage.free / (1024 ** 3), 1)
        return {
            'totalGB':     total_gb,
            'availableGB': free_gb,
            'usedGB':      round(total_gb - free_gb, 1),
            'usedPercent': round((1 - usage.free / usage.total) * 100, 1),
        }
    except Exception as e:
        log.warning('Failed to read disk info: %s', e)
        return {'totalGB': None, 'availableGB': None, 'usedGB': None, 'usedPercent': None}


# ── OS ───────────────────────────────────────────────────────────────────────

def _get_os():
    """Return Windows version info."""
    return {
        'name':    platform.system(),
        'version': platform.version(),
        'release': platform.release(),
        'build':   platform.win32_ver()[1] if hasattr(platform, 'win32_ver') else '',
    }


# ── WMI Data (single PowerShell call) ────────────────────────────────────────

_PS_SCRIPT = r"""
$gpu = Get-CimInstance Win32_VideoController | Select-Object -First 1 `
    Name, DriverVersion, `
    @{N='VRAMTotalMB';E={[math]::Round($_.AdapterRAM / 1MB)}}, `
    @{N='VRAMCurrentMB';E={if($_.AdapterRAM){[math]::Round(($_.AdapterRAM - $_.AdapterRAM) / 1MB)}else{$null}}}

$net = Get-CimInstance Win32_NetworkAdapter -Filter "NetConnectionStatus=2" | Select-Object -First 1 `
    Name, AdapterType, `
    @{N='Speed';E={$_.Speed}}

$disk = Get-PhysicalDisk | Where-Object DeviceID -eq 0 | Select-Object -First 1 `
    MediaType, BusType, FriendlyName

$mon = Get-CimInstance Win32_DesktopMonitor | Select-Object `
    @{N='Width';E={$_.ScreenWidth}}, @{N='Height';E={$_.ScreenHeight}}

$monCount = @(Get-CimInstance Win32_DesktopMonitor).Count
# Fallback: if DesktopMonitor gives 0 resolution, try VideoController
if (-not $mon -or ($mon | ForEach-Object { $_.Width }) -notcontains $null -eq $false) {
    $vc = Get-CimInstance Win32_VideoController | Select-Object -First 1 `
        CurrentHorizontalResolution, CurrentVerticalResolution
}

[PSCustomObject]@{
    GPU = $gpu
    Network = $net
    Disk = $disk
    MonitorCount = $monCount
    Monitors = $mon
    PrimaryResolution = if ($vc) { "$($vc.CurrentHorizontalResolution)x$($vc.CurrentVerticalResolution)" } `
        elseif ($mon -and $mon[0].Width) { "$($mon[0].Width)x$($mon[0].Height)" } `
        else { "" }
} | ConvertTo-Json -Depth 3
"""


def _get_wmi_data():
    """Run a single PowerShell call to gather GPU, network, disk type, and monitor info."""
    try:
        result = subprocess.run(
            ['powershell', '-NoProfile', '-NonInteractive', '-Command', _PS_SCRIPT],
            capture_output=True, text=True, timeout=15,
            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0),
        )
        if result.returncode != 0:
            log.warning('PowerShell WMI query failed: %s', result.stderr.strip())
            return {}
        return json.loads(result.stdout)
    except subprocess.TimeoutExpired:
        log.warning('PowerShell WMI query timed out')
        return {}
    except (json.JSONDecodeError, Exception) as e:
        log.warning('Failed to parse WMI data: %s', e)
        return {}


def _parse_gpu(wmi):
    """Extract GPU info from WMI data."""
    gpu = wmi.get('GPU') or {}
    return {
        'name':          gpu.get('Name', ''),
        'driverVersion': gpu.get('DriverVersion', ''),
        'vramTotalMB':   gpu.get('VRAMTotalMB'),
    }


def _parse_network(wmi):
    """Extract network adapter info from WMI data."""
    net = wmi.get('Network') or {}
    name = net.get('Name', '')
    adapter_type = net.get('AdapterType', '')

    # Determine connection type from adapter name/type
    name_lower = name.lower()
    if 'wi-fi' in name_lower or 'wireless' in name_lower or 'wifi' in name_lower:
        conn_type = 'WiFi'
    elif 'ethernet' in name_lower or 'realtek' in name_lower or 'intel.*ethernet' in name_lower:
        conn_type = 'Ethernet'
    elif adapter_type:
        conn_type = adapter_type
    else:
        conn_type = 'Unknown'

    speed = net.get('Speed')
    speed_mbps = round(int(speed) / 1_000_000) if speed else None

    return {
        'adapterName':  name,
        'type':         conn_type,
        'speedMbps':    speed_mbps,
    }


def _parse_disk_type(wmi):
    """Extract disk type (SSD/HDD) from WMI data."""
    disk = wmi.get('Disk') or {}
    media = disk.get('MediaType', '')
    return {
        'type':         media if media else 'Unknown',
        'busType':      disk.get('BusType', ''),
        'friendlyName': disk.get('FriendlyName', ''),
    }


def _parse_display(wmi):
    """Extract monitor info from WMI data."""
    return {
        'monitorCount':     wmi.get('MonitorCount', 0),
        'primaryResolution': wmi.get('PrimaryResolution', ''),
    }


# ── Model Info ───────────────────────────────────────────────────────────────

def _get_model_info(model_name, model_path):
    """Return model metadata including file size."""
    info = {
        'name': model_name or '',
        'path': model_path or '',
        'sizeMB': None,
    }
    if model_path:
        try:
            size_bytes = os.path.getsize(model_path)
            info['sizeMB'] = round(size_bytes / (1024 * 1024), 1)
        except OSError:
            pass
    return info


# ── Main Capture ─────────────────────────────────────────────────────────────

def capture_health_snapshot(revit_version=None, revit_build=None,
                            revit_username=None,
                            model_name=None, model_path=None):
    """Capture a full system health snapshot.

    Parameters are optional — pass what's available from the Revit session.
    Returns a dict ready to be saved as JSON.
    """
    log.info('Capturing system health snapshot')

    # Gather WMI data in one shot
    wmi = _get_wmi_data()

    snapshot = {
        'captureTimestamp': datetime.now(timezone.utc).isoformat(),
        'identity': {
            'windowsUsername': os.environ.get('USERNAME', os.environ.get('USER', '')),
            'revitUsername':   revit_username or '',
            'deviceName':     socket.gethostname(),
        },
        'ram':     _get_ram(),
        'cpu':     _get_cpu(),
        'gpu':     _parse_gpu(wmi),
        'disk':    {**_get_disk(), **_parse_disk_type(wmi)},
        'display': _parse_display(wmi),
        'network': _parse_network(wmi),
        'os':      _get_os(),
        'revit': {
            'version': revit_version or '',
            'build':   revit_build or '',
        },
        'model':   _get_model_info(model_name, model_path),
    }

    log.info('Health snapshot captured: %s / %dMB RAM used / %.1fGB disk free',
             snapshot['identity']['deviceName'],
             snapshot['ram'].get('usedMB', 0) or 0,
             snapshot['disk'].get('availableGB', 0) or 0)

    return snapshot


def save_health_snapshot(snapshot, path):
    """Write health snapshot to a JSON file."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(snapshot, f, indent=2, ensure_ascii=False)
    os.replace(tmp, path)
    log.info('Health snapshot saved to %s', path)
