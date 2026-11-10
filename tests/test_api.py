'''Tests for the FastAPI surface in regtrace.api.'''

from __future__ import annotations

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from fastapi.testclient import TestClient

from regtrace.api import create_app
from regtrace.data import DATA_DIR, dates, documents, section_key


@unittest.skipUnless((DATA_DIR / 'ecfr').is_dir(), 'pinned snapshot not present')
class ApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.client = TestClient(create_app())
        cls.dates = dates()
        cls.documents = documents()

    def test_health_counts(self) -> None:
        response = self.client.get('/health')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {'dates': 38, 'documents': 45, 'rules': 26})

    def test_sections_defaults_to_latest_and_returns_paragraphs(self) -> None:
        response = self.client.get('/sections/438.68')
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body['section'], '438.68')
        self.assertEqual(body['date'], self.dates[-1])
        self.assertEqual(body['in_force'], self.dates[-1])
        self.assertTrue(body['heading'].startswith('\u00a7 438.68'))
        self.assertTrue(body['paragraphs'])
        for paragraph in body['paragraphs']:
            self.assertEqual(set(paragraph), {'label', 'text'})
            self.assertIsInstance(paragraph['label'], str)
            self.assertIsInstance(paragraph['text'], str)

    def test_sections_uses_the_latest_snapshot_on_or_before_the_date(self) -> None:
        response = self.client.get('/sections/438.2', params={'date': '2017-01-02'})
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body['section'], '438.2')
        self.assertEqual(body['date'], '2017-01-02')
        self.assertEqual(body['in_force'], '2017-01-01')
        later = self.client.get('/sections/438.2', params={'date': '2030-01-01'}).json()
        self.assertEqual(later['in_force'], self.dates[-1])

    def test_sections_before_history_is_404(self) -> None:
        response = self.client.get('/sections/438.2', params={'date': '2016-12-31'})
        self.assertEqual(response.status_code, 404)
        self.assertIn('no eCFR data', response.json()['detail'])

    def test_sections_unknown_section_is_404(self) -> None:
        response = self.client.get('/sections/999.999')
        self.assertEqual(response.status_code, 404)
        self.assertIn('not found', response.json()['detail'])

    def test_sections_invalid_date_is_400(self) -> None:
        response = self.client.get('/sections/438.2', params={'date': '2017-1-1'})
        self.assertEqual(response.status_code, 400)
        self.assertIn('invalid date', response.json()['detail'])

    def test_changes_between_data_dates(self) -> None:
        response = self.client.get('/changes', params={'from': self.dates[0], 'to': self.dates[-1]})
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body['from'], self.dates[0])
        self.assertEqual(body['to'], self.dates[-1])
        self.assertTrue(body['changes'])
        for change in body['changes']:
            self.assertEqual(set(change), {'section', 'label', 'kind', 'old_text', 'new_text'})
        same = self.client.get('/changes', params={'from': self.dates[0], 'to': self.dates[0]})
        self.assertEqual(same.json()['changes'], [])

    def test_changes_rejects_dates_that_are_not_snapshots(self) -> None:
        response = self.client.get('/changes', params={'from': '2017-01-02', 'to': self.dates[-1]})
        self.assertEqual(response.status_code, 400)
        self.assertIn('not an eCFR snapshot date', response.json()['detail'])
        invalid = self.client.get('/changes', params={'from': 'not-a-date', 'to': self.dates[-1]})
        self.assertEqual(invalid.status_code, 400)
        self.assertIn('invalid date', invalid.json()['detail'])

    def test_documents_list_statuses(self) -> None:
        response = self.client.get('/documents')
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(len(body), len(self.documents))
        for item in body:
            self.assertEqual(
                set(item),
                {
                    'number',
                    'type',
                    'action',
                    'title',
                    'publication_date',
                    'effective_on',
                    'has_text',
                    'statuses',
                },
            )
            self.assertIsInstance(item['statuses'], dict)
        proposed = [item for item in body if item['type'] == 'Proposed Rule']
        self.assertTrue(proposed)
        for item in proposed:
            self.assertEqual(item['statuses'], {})
        rules = [item for item in body if item['type'] == 'Rule' and item['statuses']]
        self.assertTrue(rules)
        for item in rules:
            self.assertLessEqual(
                set(item['statuses']),
                {'matched', 'shifted', 'before_history', 'unmatched'},
            )
            self.assertTrue(all(value > 0 for value in item['statuses'].values()))

    def test_document_detail_matches_list_entry_and_rows(self) -> None:
        listing = self.client.get('/documents').json()
        rules = [item for item in listing if item['type'] == 'Rule' and item['statuses']]
        self.assertTrue(rules)
        rule = rules[0]
        response = self.client.get('/documents/' + rule['number'])
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body['document'], rule)
        self.assertTrue(body['instructions'])
        for instruction in body['instructions']:
            self.assertEqual(set(instruction), {'number', 'text', 'sections'})
            self.assertIsInstance(instruction['sections'], list)
        self.assertTrue(body['rows'])
        statuses = {}
        for row in body['rows']:
            self.assertEqual(set(row), {'section', 'status', 'date'})
            statuses[row['status']] = statuses.get(row['status'], 0) + 1
        self.assertEqual(statuses, rule['statuses'])

    def test_document_detail_unknown_is_404(self) -> None:
        response = self.client.get('/documents/0000-00000')
        self.assertEqual(response.status_code, 404)
        self.assertIn('not found', response.json()['detail'])

    def test_unexplained_is_sorted_and_excludes_the_base_date(self) -> None:
        response = self.client.get('/unexplained')
        self.assertEqual(response.status_code, 200)
        items = response.json()
        for item in items:
            self.assertEqual(set(item), {'section', 'date'})
            self.assertIn(item['date'], self.dates)
            self.assertNotEqual(item['date'], self.dates[0])
        keys = [(item['date'], section_key(item['section'])) for item in items]
        self.assertEqual(keys, sorted(keys))

    def test_verify_accepts_a_quote_from_the_latest_snapshot(self) -> None:
        section = self.client.get('/sections/438.68').json()
        paragraph = next(
            item
            for item in section['paragraphs']
            if len(' '.join(item['text'].split())) >= 20
        )
        quote = ' '.join(paragraph['text'].split())
        payload = {
            'section': '438.68',
            'label': paragraph['label'],
            'date': self.dates[-1],
            'quote': quote,
        }
        response = self.client.post('/verify', json=payload)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['status'], 'valid')
        words = quote.split()
        words[-1] = 'zzzz'
        payload['quote'] = ' '.join(words)
        perturbed = self.client.post('/verify', json=payload)
        self.assertEqual(perturbed.status_code, 200)
        self.assertNotEqual(perturbed.json()['status'], 'valid')

    def test_verify_too_short(self) -> None:
        response = self.client.post(
            '/verify',
            json={'section': '438.2', 'label': '(a)', 'date': self.dates[-1], 'quote': 'short'},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['status'], 'too_short')

    def test_verify_bad_body_is_422(self) -> None:
        response = self.client.post(
            '/verify',
            json={'section': '438.2', 'label': '(a)', 'date': self.dates[-1]},
        )
        self.assertEqual(response.status_code, 422)

    def test_verify_invalid_date_is_400(self) -> None:
        response = self.client.post(
            '/verify',
            json={
                'section': '438.2',
                'label': '(a)',
                'date': 'not-a-date',
                'quote': 'Providers must meet the network adequacy standards',
            },
        )
        self.assertEqual(response.status_code, 400)


class AlternateSnapshotApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.tmp = TemporaryDirectory()
        cls.data_dir = Path(cls.tmp.name)
        (cls.data_dir / 'ecfr').mkdir()
        (cls.data_dir / 'fr').mkdir()
        (cls.data_dir / 'ecfr' / 'part438-2020-01-01.xml').write_text(
            '<DIV5><DIV8 N="438.2"><HEAD>Section 438.2.</HEAD>'
            '<P>(a) This is a long enough quote for verification.</P></DIV8></DIV5>',
            encoding='utf-8',
        )
        (cls.data_dir / 'ecfr' / 'versions.json').write_text(
            json.dumps({'content_versions': [{'identifier': '438.2', 'date': '2020-01-01', 'substantive': True}]}),
            encoding='utf-8',
        )
        (cls.data_dir / 'fr' / 'documents.json').write_text(
            json.dumps(
                {
                    'results': [
                        {
                            'document_number': '2020-0001',
                            'type': 'Rule',
                            'action': 'Final rule',
                            'title': 'Managed care',
                            'publication_date': '2020-01-01',
                            'effective_on': '2020-01-01',
                        }
                    ]
                }
            ),
            encoding='utf-8',
        )
        (cls.data_dir / 'fr' / '2020-0001.xml').write_text(
            '<ROOT><REGTEXT TITLE="42" PART="438"><AMDPAR>1. Amend \u00a7 438.2.</AMDPAR></REGTEXT></ROOT>',
            encoding='utf-8',
        )
        cls.client = TestClient(create_app(cls.data_dir))

    @classmethod
    def tearDownClass(cls) -> None:
        cls.tmp.cleanup()

    def test_health_uses_the_alternate_snapshot(self) -> None:
        response = self.client.get('/health')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {'dates': 1, 'documents': 1, 'rules': 1})

    def test_document_detail_uses_the_alternate_snapshot(self) -> None:
        response = self.client.get('/documents/2020-0001')
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body['document']['number'], '2020-0001')
        self.assertEqual(body['instructions'][0]['sections'], ['438.2'])
        self.assertEqual(body['rows'], [{'section': '438.2', 'status': 'before_history', 'date': None}])

    def test_unexplained_and_verify_use_the_alternate_snapshot(self) -> None:
        unexplained = self.client.get('/unexplained')
        self.assertEqual(unexplained.status_code, 200)
        self.assertEqual(unexplained.json(), [])
        verify = self.client.post(
            '/verify',
            json={
                'section': '438.2',
                'label': '(a)',
                'date': '2020-01-01',
                'quote': 'This is a long enough quote for verification',
            },
        )
        self.assertEqual(verify.status_code, 200)
        self.assertEqual(verify.json()['status'], 'valid')

    def test_changes_missing_parameter_is_400(self) -> None:
        response = self.client.get('/changes', params={'from': '2020-01-01'})
        self.assertEqual(response.status_code, 400)
        response = self.client.get('/changes')
        self.assertEqual(response.status_code, 400)


if __name__ == '__main__':
    unittest.main()
