import importlib.util
import json
from datetime import datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

SOURCE = Path(__file__).resolve().parents[1] / 'status.py'
spec = importlib.util.spec_from_file_location('backup_status', SOURCE)
status = importlib.util.module_from_spec(spec)
spec.loader.exec_module(status)

NOW = datetime.fromisoformat('2026-09-23T18:17:00-07:00')
RECEIPT = {
    'generation': '20260923T222017Z-dc27288f',
    'sha256': 'a' * 64,
    'finished': '2026-09-23T15:20:45-07:00', 'archive_bytes': 1113134014,
    'NAS_digest_match': True, 'full_download_match': True, 'zstd_integrity': True,
    'samples': {'config': {'pass': True}, 'project': {'pass': True}},
}
SERVICE = {'LoadState': 'loaded', 'ActiveState': 'inactive', 'SubState': 'dead'}
TIMER = {'LoadState': 'loaded', 'ActiveState': 'active', 'UnitFileState': 'enabled',
         'NextElapseUSecRealtime': 'Wed 2026-09-23 19:15:00 PDT'}
INVENTORY = {'generations': [{}], 'partial_generations': 0}


def view(current=None, receipt=RECEIPT, failure=None, service=SERVICE, timer=TIMER, now=NOW):
    return status.build(current, receipt, failure, INVENTORY, service, timer, now)


class BackupStatusTests(unittest.TestCase):
    def test_capacity_failure_is_actionable_without_private_detail(self):
        result = view({'status':'failed','reason':'Capture exceeds 64 GiB uncompressed safety bound','time':NOW.isoformat()})
        self.assertIn('capture size limit',result['reason'])
        self.assertTrue(result['canStart'])

    def test_covered_slot_and_next_check_are_separate(self):
        now = NOW.replace(hour=16)
        result = view({'status': 'skipped', 'reason': 'already covered current daily slot',
                       'time': '2026-09-23T16:15:00-07:00'}, now=now)
        self.assertEqual(result['state'], 'complete')
        self.assertEqual(result['dueValue'], 'Today, 18:00')
        self.assertEqual(result['nextCheck'], 'Today, 19:15')
        self.assertFalse(result['canStart'])
        self.assertTrue(result['checksPassed'])

    def test_due_slot_after_18_enables_only_due_check(self):
        result = view({'status': 'success', 'reason': 'passed',
                       'time': '2026-09-23T15:20:45-07:00'})
        self.assertEqual(result['state'], 'due')
        self.assertEqual('Backup due since', result['dueLabel'])
        self.assertEqual('Today, 18:00', result['dueValue'])
        self.assertTrue(result['canStart'])

    def test_running_phase_is_indeterminate_and_prior_success(self):
        running = dict(SERVICE, ActiveState='activating', SubState='start')
        result = view({'status': 'running', 'reason': 'uploading', 'bytes': 1113134014,
                       'time': '2026-09-23T18:16:00-07:00'}, service=running)
        self.assertEqual(result['state'], 'running')
        self.assertIn('Uploading archive', result['reason'])
        self.assertEqual(result['lastSuccess'], 'Today, 15:20')
        self.assertFalse(result['canStart'])

    def test_stale_running_record_is_unavailable_after_service_exits(self):
        result = view({'status': 'running', 'reason': 'capturing',
                       'time': '2026-09-23T18:16:00-07:00'})
        self.assertEqual(result['state'], 'unavailable')
        self.assertFalse(result['canStart'])

    def test_active_service_wins_when_timer_lookup_fails(self):
        result = view({'status': 'running', 'reason': 'capturing',
                       'time': NOW.isoformat()}, service=dict(SERVICE, ActiveState='activating'), timer=None)
        self.assertEqual(result['state'], 'running')
        self.assertFalse(result['canStart'])
        self.assertEqual(result['nextCheck'], 'Unavailable')

    def test_stopping_disables_start_and_preserves_prior_receipt(self):
        result = view({'status': 'running', 'reason': 'capturing', 'time': NOW.isoformat()},
                      service=dict(SERVICE, ActiveState='deactivating'))
        self.assertEqual(result['state'], 'stopping')
        self.assertTrue(result['serviceRunning'])
        self.assertFalse(result['canStart'])
        self.assertEqual(result['lastSuccess'], 'Today, 15:20')

    def test_explicit_cancellation_does_not_masquerade_as_success_or_failure(self):
        result = view({'status': 'skipped', 'time': NOW.isoformat(),
                       'cancellation': {'requested_by': 'user', 'uploaded': False,
                                        'cancelled_at': NOW.isoformat()}},
                      failure={'time': NOW.isoformat()})
        self.assertEqual(result['state'], 'cancelled')
        self.assertEqual(result['lastSuccess'], 'Today, 15:20')
        self.assertTrue(result['canStart'])
        self.assertEqual(result['lastCheckTime'], NOW.isoformat())

    def test_persistent_failure_survives_later_skip(self):
        current = {'status': 'skipped', 'reason': 'AC power unavailable or unknown',
                   'time': '2026-09-23T18:15:00-07:00'}
        result = view(current, failure={'time': '2026-09-23T18:05:00-07:00'})
        self.assertEqual(result['state'], 'failure')
        self.assertIn('AC power', result['reason'])
        self.assertEqual(result['lastSuccess'], 'Today, 15:20')
        newer = dict(RECEIPT, finished='2026-09-23T18:10:00-07:00')
        self.assertEqual(view(current, receipt=newer,
                              failure={'time': '2026-09-23T18:05:00-07:00'})['state'], 'complete')

    def test_power_and_nas_skips_are_not_success(self):
        for reason, expected in [('AC power unavailable or unknown', 'power'),
                                 ('NAS unreachable; retry at next timer check', 'nas')]:
            result = view({'status': 'skipped', 'reason': reason,
                           'time': '2026-09-23T18:15:00-07:00'})
            self.assertEqual(result['state'], expected)
            self.assertTrue(result['canStart'])

    def test_missing_manager_and_disabled_timer_have_no_next_check(self):
        current = {'status': 'skipped', 'reason': 'already covered current daily slot',
                   'time': '2026-09-23T18:15:00-07:00'}
        self.assertEqual(view(current, service=None)['state'], 'manager')
        disabled = dict(TIMER, ActiveState='inactive', UnitFileState='disabled')
        result = view(current, timer=disabled)
        self.assertEqual(result['state'], 'manager')
        self.assertEqual(result['nextCheck'], 'Unavailable')
        self.assertFalse(result['canStart'])

    def test_partial_receipt_cannot_cover_slot_or_claim_checks(self):
        bad = dict(RECEIPT, finished='2026-09-23T18:10:00-07:00',
                   samples={'project': {'pass': True}})
        result = view({'status': 'success', 'time': '2026-09-23T18:10:00-07:00'}, receipt=bad)
        self.assertFalse(result['checksPassed'])
        self.assertNotEqual(result['state'], 'complete')
        self.assertEqual(result['lastSuccess'], 'None recorded')
        self.assertEqual(result['lastSize'], '—')
        self.assertFalse(result['canStart'])

    def test_future_receipt_is_not_success(self):
        future = dict(RECEIPT, finished='2026-09-23T18:30:00-07:00')
        result = view({'status': 'success', 'time': '2026-09-23T18:16:00-07:00'},
                      receipt=future)
        self.assertEqual(result['state'], 'unavailable')
        self.assertEqual(result['lastSuccess'], 'None recorded')
        self.assertFalse(result['canStart'])

    def test_corrupt_and_oversize_json_rejected(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'status.json').write_text('{bad')
            self.assertIsNone(status.read_json('status.json', root))
            (root / 'status.json').write_text(json.dumps(['not an object']))
            self.assertIsNone(status.read_json('status.json', root))
            (root / 'status.json').write_text('x' * (status.MAX_JSON + 1))
            self.assertIsNone(status.read_json('status.json', root))

    def test_invalid_reason_does_not_crash_and_stale_data_is_unavailable(self):
        result = view({'status': 'skipped', 'reason': ['unexpected'],
                       'time': '2026-09-23T12:00:00-07:00'})
        self.assertEqual(result['state'], 'unavailable')

    def test_daily_slot_before_18_is_yesterday(self):
        self.assertEqual(status.slot_at(NOW.replace(hour=10)).day, 22)


if __name__ == '__main__':
    unittest.main()
