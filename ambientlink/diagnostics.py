"""Bounded, local-only support reports built from allowlisted fields, never raw logs."""
from collections import deque
from datetime import datetime, timezone
import io
import json
import logging
from logging.handlers import RotatingFileHandler
import math
from pathlib import Path
import platform
import re
import threading
import time
import zipfile

from . import __version__

DRIVERS = {'govee-h600b', 'govee-lan', 'tapo-l530'}
PHASES = {'connect', 'send', 'heartbeat', 'capture', 'restore', 'api', 'startup', 'background'}
CODES = {'device_failure', 'capture_failure', 'restore_failure', 'request_failed',
         'startup_failure', 'background_failure', 'tapo_connect', 'tapo_update',
         'tapo_restore', 'tapo_model', 'tapo_effect', 'tapo_account'}
KINDS = {'session', 'start', 'manual', 'stop', 'connected', 'error', 'sample',
         'issue_marker', 'settings_changed'}
CATEGORIES = {'timeout', 'network', 'permission', 'invalid_input', 'other'}
METRICS = {'writes', 'updateFps', 'sendMs', 'sendP50Ms', 'sendP95Ms', 'sendMaxMs',
           'frameAgeMs', 'lastSuccessAgeMs', 'connectMs', 'connections', 'errors',
           'timeouts', 'consecutiveErrors', 'rateLimitHz', 'transportCeilingHz', 'sendSamples', 'deduplicated'}


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def error_category(error):
    if isinstance(error, TimeoutError): return 'timeout'
    if isinstance(error, PermissionError): return 'permission'
    if isinstance(error, OSError): return 'network'
    if isinstance(error, ValueError): return 'invalid_input'
    return 'other'


class DeviceError(ValueError):
    """User-safe message with a stable diagnostic code and no raw cause text."""
    def __init__(self, message, code, cause=None):
        super().__init__(message)
        self.code = code
        self.category = error_category(cause) if cause is not None else 'invalid_input'


def error_fields(error, fallback):
    code = getattr(error, 'code', fallback)
    category = getattr(error, 'category', error_category(error))
    fields = {'code': code if code in CODES else fallback,
              'category': category if category in CATEGORIES else 'other'}
    trace = getattr(error, '__traceback__', None)
    while trace:
        source = Path(trace.tb_frame.f_code.co_filename)
        if source.parent == Path(__file__).parent and source.name in SOURCE_FILES:
            fields['source'] = source.name
            fields['line'] = trace.tb_lineno
        trace = trace.tb_next
    return fields


def numeric(value):
    return type(value) in (int, float) and math.isfinite(value) and abs(value) < 1e15


SOURCE_FILES = {'app.py', 'engine.py', 'capture.py', 'colors.py', 'color_smoothing.py',
                'drivers.py', 'tapo_driver.py', 'govee_ble.py', 'credentials.py',
                'diagnostics.py', 'settings.py', 'led_color.py'}


def snapshot(config, state):
    """Omit names, addresses, paths, accounts, colors and arbitrary error strings."""
    report = {'settings': {}, 'state': {}, 'devices': []}
    for key in ('brightness', 'fps', 'smoothing'):
        if numeric(config.get(key)): report['settings'][key] = config[key]
    if config.get('mode') in ('dominant', 'zones', 'average'):
        report['settings']['mode'] = config['mode']
    for key in ('fps', 'frames', 'captureMs'):
        if numeric(state.get(key)): report['state'][key] = state[key]
    report['state']['active'] = state.get('active') is True
    if state.get('mode') in ('idle', 'screen', 'manual', 'error'):
        report['state']['mode'] = state['mode']
    report['state']['hasError'] = bool(state.get('error'))
    for index, spec in enumerate(config.get('devices', [])[:24]):
        row = state.get('devices', [])[index] if index < len(state.get('devices', [])) else {}
        item = {'light': index + 1, 'driver': spec.get('driver') if spec.get('driver') in DRIVERS else 'unknown',
                'enabled': spec.get('enabled') is True, 'gamma': spec.get('gamma') is True,
                'connected': row.get('connected') is True, 'hasError': bool(row.get('error'))}
        if spec.get('zone') in (0, 1, 2): item['zone'] = spec['zone']
        gains = spec.get('gains')
        if isinstance(gains, list) and len(gains) == 3 and all(numeric(v) for v in gains): item['gains'] = gains
        for key in METRICS:
            if numeric(row.get(key)): item[key] = row[key]
        if row.get('errorCode') in CODES: item['errorCode'] = row['errorCode']
        if row.get('errorCategory') in CATEGORIES: item['errorCategory'] = row['errorCategory']
        report['devices'].append(item)
    return report


def clean_event(event):
    # Reapply the schema on export, including to previously saved JSONL files.
    if not isinstance(event, dict) or event.get('kind') not in KINDS: return None
    try: stamp = datetime.fromisoformat(event['at']).astimezone(timezone.utc).isoformat()
    except (KeyError, ValueError, TypeError): return None
    out = {'at': stamp, 'kind': event['kind']}
    if isinstance(event.get('appVersion'),str) and re.fullmatch(r'\d{1,4}\.\d{1,4}\.\d{1,4}',event['appVersion']):
        out['appVersion'] = event['appVersion']
    if event.get('source') in SOURCE_FILES and type(event.get('line')) is int:
        out.update(source=event['source'],line=event['line'])
    if event.get('phase') in PHASES: out['phase'] = event['phase']
    if event.get('code') in CODES: out['code'] = event['code']
    if event.get('category') in CATEGORIES: out['category'] = event['category']
    if type(event.get('light')) is int and 1 <= event['light'] <= 24: out['light'] = event['light']
    for key in ('durationMs', 'retryInSeconds'):
        if numeric(event.get(key)): out[key] = event[key]
    # Samples pass through the same snapshot allowlist a second time.
    sample = event.get('sample')
    if isinstance(sample, dict):
        devices = sample.get('devices', [])
        if isinstance(devices, list) and all(isinstance(d, dict) for d in devices):
            out['sample'] = snapshot({**sample.get('settings', {}), 'devices': devices},
                                     {**sample.get('state', {}), 'devices': devices})
            # snapshot's hasError is the only exported representation of errors.
            out['sample']['state']['hasError'] = sample.get('state', {}).get('hasError') is True
            for item, previous in zip(out['sample']['devices'], devices):
                item['hasError'] = previous.get('hasError') is True
    return out


class Diagnostics:
    def __init__(self, root=None):
        self.started = time.monotonic()
        self.lock = threading.RLock()
        self.events = deque(maxlen=500)
        self.handler = None
        self.storage_ok = True
        self.path = Path(root) / 'diagnostics' / 'events.jsonl' if root is not None else None
        if self.path:
            try:
                self.path.parent.mkdir(parents=True, exist_ok=True)
                self.handler = RotatingFileHandler(self.path, maxBytes=256*1024, backupCount=1, encoding='utf-8')
                self.handler.setFormatter(logging.Formatter('%(message)s'))
            except OSError: self.storage_ok = False
        self.record('session')

    def record(self, kind, **fields):
        event = clean_event({'at': utc_now(), 'kind': kind, 'appVersion': __version__, **fields})
        if event is None: return
        with self.lock:
            self.events.append(event)
            if self.handler:
                try:
                    raw = json.dumps(event, allow_nan=False)
                    record = logging.LogRecord('ambientlink.support', logging.INFO, '', 0, raw, (), None)
                    # Avoid logging's stderr error fallback in a windowless EXE.
                    if self.handler.shouldRollover(record): self.handler.doRollover()
                    self.handler.stream.write(raw + '\n'); self.handler.flush()
                except OSError: self.storage_ok = False

    def recent(self):
        with self.lock:
            result = []
            if self.path and self.storage_ok:
                for path in (self.path.with_name(self.path.name + '.1'), self.path):
                    try:
                        with path.open(encoding='utf-8') as stream:
                            raw = stream.read(256*1024 + 16384)
                        for line in raw.splitlines():
                            try:
                                event = clean_event(json.loads(line))
                                if event: result.append(event)
                            except (ValueError, TypeError, AttributeError): pass
                    except OSError: pass
            return result[-500:] if result else list(self.events)

    def bundle(self, safe_snapshot):
        report = {'schemaVersion': 1, 'appVersion': __version__, 'createdAt': utc_now(),
                  'uptimeSeconds': round(time.monotonic()-self.started, 1),
                  'environment': {'os': platform.system(), 'osVersion': platform.version(),
                                  'python': platform.python_version(), 'architecture': platform.machine()},
                  'localHistoryWritable': self.storage_ok, **safe_snapshot}
        readme = '''AmbientLink local diagnostic report
Share this ZIP manually with the maintainer after reproducing the problem.
No automatic upload takes place. Lights are numbered in panel order.
Includes app/OS versions, tuning settings, counters, sanitized errors and recent timing samples.
Excludes screenshots, sampled colors, passwords, tokens, account email, IP/MAC addresses,
device names, computer/user names, paths, raw exception messages and credential files.
History is bounded (two 256 KiB local files; at most 500 events exported).
sendMs / sendP95Ms measure command completion, NOT visible bulb response.
frameAgeMs measures capture-to-command completion, excluding physical bulb fade time.
updateFps counts changed writes over 3 seconds; a static scene can legitimately show zero.
sendP50/P95/Max cover the last 120 successful changed writes in this device session.
Tapo automatically adapts its send rate to replies, up to 10 Hz; capture FPS is separate.
Describe the exact model/firmware, observed delay, and whether Apply color also lags
in your accompanying message. Mark issue in the panel when you see the problem.
'''
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as archive:
            archive.writestr('README.txt', readme)
            archive.writestr('report.json', json.dumps(report, indent=2, allow_nan=False))
            archive.writestr('recent-events.jsonl', '\n'.join(json.dumps(e, allow_nan=False) for e in self.recent()))
        return buffer.getvalue()

    def close(self):
        with self.lock:
            if self.handler: self.handler.close(); self.handler = None
