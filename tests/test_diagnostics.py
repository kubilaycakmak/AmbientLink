import asyncio
import io
import json
import zipfile
from types import SimpleNamespace

from ambientlink.diagnostics import Diagnostics, DeviceError, snapshot, error_fields
from ambientlink.engine import Engine
from ambientlink.settings import validate
from ambientlink.tapo_driver import TapoL530


def content(bundle):
    with zipfile.ZipFile(io.BytesIO(bundle)) as archive:
        assert set(archive.namelist()) == {'README.txt','report.json','recent-events.jsonl'}
        return '\n'.join(archive.read(n).decode() for n in archive.namelist())


def test_report_and_persistent_history_exclude_private_fields(tmp_path):
    secrets = ['supersecret', 'alice@example.invalid', '192.168.1.81', 'AA:BB:CC:DD:EE:FF',
               'Private bedroom', r'C:\Users\Alice', 'csrf-token-123']
    config = validate({'devices':[{'driver':'tapo-l530','address':secrets[2],'name':secrets[4]}]})
    config.update(password=secrets[0],account=secrets[1],token=secrets[-1])
    state = {'mode':'screen','colors':[[12,34,56]]*3,'fps':59.2,'error':' '.join(secrets),
             'devices':[{'error':' '.join(secrets),'connected':False,'sendMs':220,'outputRgb':[12,34,56]}]}
    diagnostics=Diagnostics(tmp_path)
    diagnostics.record('error',phase='send',message=' '.join(secrets),**error_fields(TimeoutError(' '.join(secrets)),'device_failure'))
    diagnostics.record('sample',sample=snapshot(config,state))
    diagnostics.close()
    resumed=Diagnostics(tmp_path)
    try:
        bundle=content(resumed.bundle(snapshot(config,state)))
        logs=''.join(p.read_text(encoding='utf-8') for p in (tmp_path/'diagnostics').glob('*'))
        assert all(secret not in bundle+logs for secret in secrets)
        assert 'outputRgb' not in bundle and '"colors"' not in bundle
        assert '"category": "timeout"' in bundle and '"sendMs": 220' in bundle
        assert '"hasError": true' in bundle
        assert '"kind": "error"' in bundle  # previous session retained
    finally:resumed.close()


def test_export_revalidates_saved_events_and_bounds_disk(tmp_path):
    diagnostics=Diagnostics(tmp_path)
    try:
        # A hand-edited or older file is not copied verbatim into support reports.
        with diagnostics.path.open('a',encoding='utf-8') as stream:
            stream.write(json.dumps({'at':'2026-10-25T00:00:00+00:00','kind':'error',
                                     'code':'device_failure','message':'do-not-export','password':'do-not-export'})+'\n')
        assert 'do-not-export' not in content(diagnostics.bundle(snapshot(validate({}),{})))
        for _ in range(2500):diagnostics.record('error',phase='send',code='device_failure',category='timeout')
        files=list((tmp_path/'diagnostics').glob('*'))
        assert len(files)==2 and sum(p.stat().st_size for p in files)<530_000
        assert len(diagnostics.recent())<=500
    finally:diagnostics.close()


def test_unwritable_history_does_not_prevent_in_memory_report(tmp_path):
    (tmp_path/'diagnostics').write_text('not a directory')
    diagnostics=Diagnostics(tmp_path)
    diagnostics.record('issue_marker')
    assert not diagnostics.storage_ok
    assert 'issue_marker' in content(diagnostics.bundle(snapshot(validate({}),{})))


def test_tapo_timeout_preserves_safe_category_without_secret_exception():
    class Request:
        def hue_saturation(self,*a):return self
        def brightness(self,*a):return self
        def on(self):return self
        async def send(self,*a):raise TimeoutError('password=never-export-this')
    async def run():
        driver=TapoL530({'address':'192.168.1.50'})
        driver.device=SimpleNamespace(set=lambda:Request())
        try:await driver.send((255,0,0),50)
        except DeviceError as error:
            assert error_fields(error,'device_failure')['category']=='timeout'
            assert error.code=='tapo_timeout' and 'never-export-this' not in str(error)
        else:raise AssertionError('Expected timeout')
    asyncio.run(run())


def test_sdk_errors_keep_safe_reason_stage_and_discovery_through_export():
    from ambientlink.tapo_driver import tapo_error
    error=tapo_error(Exception('Http(reqwest::Error { url: "http://192.168.1.81/private-token", source: TimedOut })'),
                     'login','no_reply')
    fields=error_fields(error,'device_failure')
    assert fields['code']=='tapo_timeout' and fields['category']=='timeout'
    diagnostics=Diagnostics()
    diagnostics.record('error',phase='connect',**fields)
    text=content(diagnostics.bundle(snapshot(validate({}),{})))
    assert '"stage": "login"' in text and '"discovery": "no_reply"' in text
    assert 'private-token' not in text and '192.168.1.81' not in text
    diagnostics.record('error',stage='private-token',discovery='192.168.1.81',retryPaused='private-token')
    assert all(secret not in content(diagnostics.bundle({})) for secret in ('private-token','192.168.1.81'))


def test_auth_failure_pauses_sender_without_blocking_stop():
    from ambientlink.tapo_driver import tapo_error
    class Device:
        rate=10
        def __init__(self,spec):self.calls=0
        async def connect(self):
            self.calls+=1
            raise tapo_error(Exception('Tapo(Unauthorized { kind: "HASH_MISMATCH" })'),'login','replied')
        async def close(self,restore=True):pass
    async def run():
        e=Engine(validate({'devices':[{'driver':'tapo-l530','address':'192.168.1.50'}]}),{'tapo-l530':Device})
        await e.manual();await asyncio.sleep(.02)
        client=e.clients[0]
        assert client.calls==1 and e.state['devices'][0]['retryPaused']
        event=next(x for x in e.diagnostics.recent() if x['kind']=='error')
        assert event['retryPaused'] and 'retryInSeconds' not in event
        await asyncio.wait_for(e.stop(),.5)
        assert client.calls==1
    asyncio.run(run())


def test_sender_reports_error_recovery_and_timings(monkeypatch):
    import ambientlink.engine as module
    class Device:
        rate=5
        def __init__(self,spec):self.spec=spec;self.attempts=0
        async def connect(self):pass
        async def send(self,rgb,brightness):
            self.attempts+=1
            if self.attempts==1:raise DeviceError('Safe error','tapo_update',TimeoutError())
            return self.attempts==2
        async def close(self,restore=True):pass
    original_sleep=asyncio.sleep
    async def quick_sleep(delay):await original_sleep(min(delay,.001))
    async def fast_pace(*args):await original_sleep(.001)
    monkeypatch.setattr(module.asyncio,'sleep',quick_sleep)
    monkeypatch.setattr(module,'pace',fast_pace)
    async def run():
        e=Engine(validate({'devices':[{'driver':'tapo-l530','address':'192.168.1.50'}]}),{'tapo-l530':Device})
        try:
            await e.manual();await original_sleep(.04)
            row=e.state['devices'][0]
            assert row['errors']==1 and row['timeouts']==1 and row['connections']==2
            assert row['writes']==1 and row['sendSamples']==1 and row['sendP95Ms']>=0
            assert row['deduplicated']>0 and row['rateLimitHz']==5
            assert row['consecutiveErrors']==0
            events=e.diagnostics.recent()
            assert any(x.get('phase')=='send' and x.get('category')=='timeout' for x in events)
        finally:await e.stop()
    asyncio.run(run())
