#!/usr/bin/env python3
"""Bounded, local-only view of the installed XPS backup evidence.

No NAS calls, logs, private manifests, keys, or shell interpolation. The runner
and systemd remain the only authorities for starting a due backup.
"""
import json
import fcntl
from datetime import datetime, timedelta
from pathlib import Path
import re
import subprocess

STATE = Path.home() / '.local/state/xps-nas-backup'
MAX_JSON = 256 * 1024


def read_json(name, state=STATE):
    path = state / name
    try:
        if path.stat().st_size > MAX_JSON:
            return None
        value = json.loads(path.read_text())
        return value if isinstance(value, dict) else None
    except (OSError, UnicodeError, ValueError):
        return None


def parse_time(value):
    try:
        result = datetime.fromisoformat(value)
        return result if result.tzinfo else None
    except (TypeError, ValueError):
        return None


def unit_properties(unit):
    try:
        result = subprocess.run(
            ['systemctl', '--user', 'show', unit, '--timestamp=unix', '--property=LoadState,ActiveState,SubState,UnitFileState,NextElapseUSecRealtime,Result'],
            capture_output=True, text=True, timeout=3, check=False)
        if result.returncode or len(result.stdout) > 8192:
            return None
        props = dict(line.split('=', 1) for line in result.stdout.splitlines() if '=' in line)
        return props if props.get('LoadState') == 'loaded' else None
    except (OSError, subprocess.TimeoutExpired):
        return None


def stamp(value, now):
    dt = parse_time(value)
    if not dt:
        return 'Unknown'
    local = dt.astimezone(now.tzinfo)
    if local.date() == now.date():
        prefix = 'Today'
    elif local.date() == (now - timedelta(days=1)).date():
        prefix = 'Yesterday'
    else:
        prefix = local.strftime('%b %-d')
    return f'{prefix}, {local:%H:%M}'


def absolute(value, now):
    dt = parse_time(value)
    return dt.astimezone(now.tzinfo).strftime('%Y-%m-%d %H:%M %Z') if dt else 'Unknown'


def slot_at(now):
    slot = now.replace(hour=18, minute=0, second=0, microsecond=0)
    return slot if now >= slot else slot - timedelta(days=1)


def receipt_valid(receipt):
    if not isinstance(receipt, dict) or not parse_time(receipt.get('finished')):
        return False
    size = receipt.get('archive_bytes')
    return (type(size) is int and 0 < size <= 20 * 1024**3 and
            isinstance(receipt.get('generation'), str) and
            re.fullmatch(r'\d{8}T\d{6}Z-[0-9a-f]{8}', receipt['generation']) is not None and
            isinstance(receipt.get('sha256'), str) and
            re.fullmatch(r'[0-9a-f]{64}', receipt['sha256']) is not None)


def checks_passed(receipt):
    samples = receipt.get('samples', {})
    return (receipt.get('NAS_digest_match') is True and
            receipt.get('full_download_match') is True and
            receipt.get('zstd_integrity') is True and
            isinstance(samples, dict) and
            all(isinstance(samples.get(key), dict) and samples[key].get('pass') is True
                for key in ('project', 'config')))


def next_check(props, now):
    raw = props.get('NextElapseUSecRealtime', '')
    if not raw or raw == 'n/a':
        return None
    if re.fullmatch(r'@[0-9]+(?:\.[0-9]+)?', raw):
        try:return datetime.fromtimestamp(float(raw[1:]),tz=now.tzinfo)
        except (ValueError,OverflowError,OSError):return None
    parsed = parse_time(raw)
    if parsed:
        return parsed
    try:
        return datetime.strptime(raw, '%a %Y-%m-%d %H:%M:%S %Z').astimezone(now.tzinfo)
    except ValueError:
        return None


def build(current, receipt, last_failure, retention, service, timer, now, retention_observed=None):
    slot = slot_at(now)
    valid_receipt = receipt_valid(receipt) and checks_passed(receipt)
    receipt_time = parse_time(receipt.get('finished')) if valid_receipt else None
    # A future-dated file is not proof that today's backup has happened.
    good_receipt = receipt if receipt_time and receipt_time <= now else None
    success_at = parse_time(good_receipt['finished']) if good_receipt else None
    covered = success_at is not None and success_at.astimezone(now.tzinfo) >= slot
    due = not covered
    result = {
        'state': 'unavailable', 'headline': 'Backup status unavailable',
        'reason': 'Local backup status is missing or stale.',
        'lastSuccess': stamp(good_receipt['finished'], now) if good_receipt else 'None recorded',
        'lastSuccessAbsolute': absolute(good_receipt['finished'], now) if good_receipt else 'None recorded',
        'lastSize': f"{good_receipt['archive_bytes'] / 1e9:.2f} GB" if good_receipt else '—',
        'dueLabel': 'Next backup due' if covered else 'Backup due since',
        'dueValue': stamp((slot + timedelta(days=1) if covered else slot).isoformat(), now) if covered else stamp(slot.isoformat(), now),
        'nextCheck': 'Unavailable', 'checksPassed': checks_passed(good_receipt) if good_receipt else False,
        'verificationLabel': 'Previous backup checks passed' if good_receipt else 'No verified receipt',
        'canStart': False, 'actionHint': 'Checks whether a backup is due; requires AC power and NAS access.',
        'serviceRunning': False, 'managerAvailable': False,
        'timerState': 'Unavailable', 'lastAttempt': 'Unknown', 'lastAttemptAbsolute': 'Unknown', 'currentActivity': '', 'lastCheckTime': '',
        'retention': 'Last reported inventory unavailable',
    }
    if not good_receipt:
        result['dueValue'] = 'Unknown'
    if isinstance(retention, dict):
        generations = retention.get('generations')
        partial = retention.get('partial_generations')
        if isinstance(generations, list) and type(partial) is int:
            when = absolute(retention_observed, now) if retention_observed else 'time unknown'
            result['retention'] = (f'Last reported {when}: {len(generations)} daily generations; '
                                   f'{partial} partial. All retained; pruning off.')
    if not service:
        result.update(state='manager', headline='Automatic checks unavailable',
                      reason='The user service manager is unavailable. Checks resume when you are logged in.')
        return result
    result['managerAvailable'] = True
    stopping = service.get('ActiveState') == 'deactivating'
    running = service.get('ActiveState') in ('activating', 'active', 'deactivating')
    result['serviceRunning'] = running
    timer = timer or {}
    timer_active = timer.get('ActiveState') == 'active'
    timer_enabled = timer.get('UnitFileState') in ('enabled', 'enabled-runtime')
    result['timerState'] = 'Active' if timer_active and timer_enabled else 'Disabled or inactive'
    next_dt = next_check(timer, now) if timer_active and timer_enabled else None
    result['nextCheck'] = stamp(next_dt.isoformat(), now) if next_dt else 'Unavailable'

    status = current.get('status') if isinstance(current, dict) else None
    reason = current.get('reason', '') if isinstance(current, dict) else ''
    reason = reason if isinstance(reason, str) else ''
    attempt_at = parse_time(current.get('time')) if isinstance(current, dict) else None
    result['lastAttempt'] = stamp(current.get('time'), now) if attempt_at else 'Unknown'
    result['lastAttemptAbsolute'] = absolute(current.get('time'), now) if attempt_at else 'Unknown'
    result['lastCheckTime'] = attempt_at.isoformat() if attempt_at else ''
    recent = attempt_at is not None and timedelta(0) <= now - attempt_at.astimezone(now.tzinfo) < timedelta(hours=3)
    if running:
        result['state'] = 'stopping' if stopping else 'running'
        result['headline'] = 'Stopping backup…' if stopping else 'Backing up…'
        phases = {'capturing': 'Capturing files', 'uploading': 'Uploading archive',
                  'retrieving and restoring samples': 'Checking download & sample restores'}
        result['reason'] = phases.get(reason, 'Backup service is running') if status == 'running' and recent else 'Backup service is running'
        result['currentActivity'] = 'Stopping' if stopping else {'capturing': 'Capturing', 'uploading': 'Uploading', 'retrieving and restoring samples': 'Checking download'}.get(reason, 'Service running')
        size = current.get('bytes') if isinstance(current, dict) else None
        if reason == 'uploading' and type(size) is int and size > 0:
            result['reason'] += f' · {size / 1e9:.2f} GB archive'
        if stopping:
            result['reason'] = 'The service is stopping. No new request can be sent yet.'
        result['actionHint'] = 'Backup in progress'
        result['verificationLabel'] = 'Previous backup checks passed' if result['checksPassed'] else 'Previous checks unconfirmed'
        return result
    if not timer_active or not timer_enabled:
        result.update(state='manager', headline='Automatic checks unavailable',
                      reason='The backup timer is disabled or inactive. No next check is scheduled.')
        return result
    if not good_receipt or not recent or status not in ('skipped', 'success', 'failed'):
        result['verificationLabel'] = 'Previous backup checks passed' if result['checksPassed'] else 'Previous checks unconfirmed'
        return result
    cancellation = current.get('cancellation') if isinstance(current, dict) else None
    cancelled = (status == 'skipped' and isinstance(cancellation, dict)
                 and cancellation.get('requested_by') == 'user'
                 and cancellation.get('uploaded') is False
                 and parse_time(cancellation.get('cancelled_at')) is not None)
    failure_time = parse_time(last_failure.get('time')) if isinstance(last_failure, dict) else None
    if not failure_time and isinstance(current, dict) and isinstance(current.get('last_failure'), dict):
        failure_time = parse_time(current['last_failure'].get('time'))
    failed = (due and failure_time is not None and
              (success_at is None or failure_time > success_at.astimezone(now.tzinfo)))
    if status == 'failed' and (success_at is None or attempt_at > success_at.astimezone(now.tzinfo)):
        failed = True
    if cancelled:
        result.update(state='cancelled', headline='Backup cancelled',
                      reason='Cancelled by user. No new backup was completed; the normal schedule remains.')
    elif failed:
        result.update(state='failure', headline='Backup needs attention',
                      reason='Last attempt failed. Retry at the next eligible check.' +
                      (' Latest check found AC power unavailable or unknown.' if status == 'skipped' and reason == 'AC power unavailable or unknown' else
                       ' Latest check could not reach Synology.' if status == 'skipped' and reason == 'NAS unreachable; retry at next timer check' else ''))
    elif due and status == 'skipped' and reason == 'AC power unavailable or unknown':
        result.update(state='power', headline='Waiting for power',
                      reason='Last check could not confirm external AC power.')
    elif due and status == 'skipped' and reason == 'NAS unreachable; retry at next timer check':
        result.update(state='nas', headline='Waiting for Synology',
                      reason='The NAS was unreachable at the last check.')
    elif due:
        result.update(state='due', headline='Backup needs attention',
                      reason='The current daily slot is due and has not completed.')
    else:
        result.update(state='complete', headline='Backup complete',
                      reason='Your daily backup is saved. The next check runs automatically.')
    if failed and status == 'failed':
        if reason.startswith('Capture exceeds ') and reason.endswith(' uncompressed safety bound'):
            result['reason'] = 'Selected files exceed the capture size limit. Review backup capacity before retrying.'
        elif reason in ('Insufficient local staging headroom', 'Less than 12 GiB local staging headroom'):
            result['reason'] = 'Not enough free disk space to stage and verify a backup.'
        elif reason.startswith('Capture rejected:') or 'Git state changed during capture' in reason or 'files changed during read' in reason:
            result['reason'] = 'Files or Git state could not be captured consistently. Retry when activity settles; see the service log if it persists.'
        elif reason == 'Archive exceeds gateway 20 GiB bound':
            result['reason'] = 'Compressed archive exceeds the NAS upload limit. Review backup capacity.'
    result['verificationLabel'] = ('Last backup checks passed' if covered else 'Previous backup checks passed') if result['checksPassed'] else 'Backup checks unconfirmed'
    result['canStart'] = due
    if covered:
        result['actionHint'] = 'Current daily backup already complete'
    return result


def legacy_main():
    now = datetime.now().astimezone()
    try:
        observed = datetime.fromtimestamp((STATE / 'retention-report.json').stat().st_mtime).astimezone().isoformat()
    except OSError:
        observed = None
    data = build(read_json('status.json'), read_json('last-success.json'),
                 read_json('last-failure.json'), read_json('retention-report.json'),
                 unit_properties('xps-nas-backup.service'),
                 unit_properties('xps-nas-backup.timer'), now, observed)
    print(json.dumps(data, ensure_ascii=False))


def borg_view(current, receipt, check, c, service, timer, now):
    # Keep saved evidence independent of later failed, skipped or checking runs.
    from backend.backup import due
    saved = receipt if isinstance(receipt, dict) and receipt.get('profile') == c['profile'] else {}
    saved_at = parse_time(saved.get('finished'))
    if not saved_at or saved_at > now: saved = {}; saved_at = None
    stats = saved.get('stats', {})
    new_bytes = stats.get('deduplicated_size') if isinstance(stats, dict) else None
    if type(new_bytes) is not int or new_bytes < 0: new_bytes = None
    checked = check if isinstance(check, dict) and check.get('profile') == c['profile'] else {}
    checked_at = parse_time(checked.get('finished'))
    passed = bool(saved_at and checked_at and saved_at <= checked_at <= now)
    current = current if isinstance(current, dict) and current.get('profile') == c['profile'] else {}
    service = service or {}; timer = timer or {}
    running = service.get('ActiveState') in ('active','activating','deactivating')
    stopping = service.get('ActiveState') == 'deactivating'
    enabled = timer.get('ActiveState') == 'active' and timer.get('UnitFileState') in ('enabled','enabled-runtime')
    is_due = due(saved, c, now)
    slot = now.replace(hour=c.get('due_hour',18),minute=0,second=0,microsecond=0)
    if now < slot: slot -= timedelta(days=1)
    next_dt = next_check(timer, now) if enabled else None
    phases = {'snapshot':'Freezing files','backup':'Saving changed data','verify':'Checking repository'}
    state = 'due' if is_due else 'complete'
    headline = 'Backup due' if is_due else 'Backup complete'
    reason = 'A backup is due. Requires configured power and repository access.' if is_due else 'Your daily backup is saved. The next check runs automatically.'
    if not service or not enabled:
        state,headline,reason = 'manager','Automatic checks unavailable','Finish setup and enable the backup timer when recovery is verified.'
    elif current.get('state') == 'failed':
        state,headline,reason = 'failure','Backup needs attention','The latest operation failed. Previous saved backups remain available; inspect the private runner logs.'
    elif is_due and current.get('reason') == 'power':
        state,headline,reason = 'power','Waiting for power','The last check could not confirm external AC power.'
    if running:
        state,headline = ('stopping','Stopping backup…') if stopping else ('running','Backup operation running…')
        reason = 'Waiting for the operation to stop.' if stopping else phases.get(current.get('reason'),'Checking service status')
    elif current.get('state') == 'running':
        state,headline,reason = 'failure','Backup needs attention','The previous operation stopped without a confirmed outcome. Inspect the runner logs and snapshot cleanup.'
    return dict(backend='borg',state=state,headline=headline,reason=reason,
        lastSuccess=stamp(saved.get('finished'),now) if saved else 'None recorded',
        lastSuccessAbsolute=absolute(saved.get('finished'),now) if saved else 'None recorded',
        lastSize=f'{new_bytes/1e9:.2f} GB' if new_bytes is not None else '—',
        dueLabel='Backup due since' if is_due else 'Next backup due',
        dueValue=stamp((slot if is_due else slot+timedelta(days=1)).isoformat(),now),
        nextCheck=stamp(next_dt.isoformat(),now) if next_dt else 'Unavailable',
        checksPassed=passed,verificationSummary='✓ Repository data check passed' if passed else 'Repository check not recorded for this backup',
        verificationTime=stamp(checked.get('finished'),now) if passed else 'Verification is separate from backup',
        verificationTimeAbsolute=absolute(checked.get('finished'),now) if passed else 'Run a full repository check after backup',
        canStart=bool(service) and enabled and is_due and not running,serviceRunning=running,managerAvailable=bool(service),
        timerState='Active' if enabled else 'Disabled or inactive',lastAttempt=stamp(current.get('time'),now),
        lastAttemptAbsolute=absolute(current.get('time'),now),lastCheckTime=current.get('time',''),
        currentActivity=phases.get(current.get('reason'),'Service running'),actionHint='No automatic deletion; inspect logs after failures.',
        retention='All archives retained. Automatic pruning and compaction are disabled.')


def main():
    candidate=Path.home()/'.config/omarchy-backup/config.json'
    if not candidate.exists():return legacy_main()
    try:
        from backend.common import config, read, STATE as borg_state
        c=config(candidate)
        service=unit_properties('omarchy-backup.service')
        try:
            with (borg_state/'runner.lock').open('r') as lock:
                try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
                except BlockingIOError:service=dict(service or {},ActiveState='active')
        except FileNotFoundError:pass
        data=borg_view(read(borg_state/'status.json',{}),read(borg_state/'last-success.json',{}),read(borg_state/'last-check.json',{}),c,
            service,unit_properties('omarchy-backup.timer'),datetime.now().astimezone())
    except Exception:
        data=dict(backend='borg',state='unavailable',headline='Backup setup needs attention',reason='Could not read the Borg configuration or local status.',canStart=False,managerAvailable=False)
    print(json.dumps(data,ensure_ascii=False))

if __name__ == '__main__':
    main()
