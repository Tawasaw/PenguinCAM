"""Named cutter restrictions must be enforced even if a client bypasses the picker."""
import io
import json
import os
import unittest

from config_validation import ConfigValidationError, validate_and_sanitize_config
from frc_cam_gui_app import app, _resolve_job_tool
from team_config import TeamConfig, parse_length
from tests.test_job_route import _square_dxf_bytes


CONFIG_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)),
                           'yaml', 'PenguinCAM-config.yaml')


class TestToolSelection(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open(CONFIG_PATH, encoding='utf-8') as handle:
            cls.config = TeamConfig.from_yaml(handle.read())

    def test_inventory_material_rules_do_not_assume_installed_collet(self):
        self.assertAlmostEqual(_resolve_job_tool(self.config, 'amana_51404', 'acetal', 0.250), 0.250)
        self.assertAlmostEqual(_resolve_job_tool(self.config, 'amana_51454', 'aluminum_tube', 0.125), 0.125)
        self.assertAlmostEqual(_resolve_job_tool(self.config, 'amana_51459', 'aluminum', 0.125), 0.125)
        for tool, material, diameter in (
            (None, 'acetal', 0.125),
            ('amana_51411', 'aluminum', 0.125),
            ('amana_51454', 'acetal', 0.125),
            ('amana_51404', 'acetal', 0.125),
        ):
            with self.subTest(tool=tool, material=material):
                with self.assertRaises(ValueError):
                    _resolve_job_tool(self.config, tool, material, diameter)

    def test_new_plastics_have_nominal_thickness_and_complete_presets(self):
        inventory = self.config.get_tool_inventory()
        allowed = inventory['amana_51411']['supported_materials']
        for material, expected_thickness in (
            ('hdpe_5865n112', 0.125),
            ('swyft_srpp_3mm', 3 / 25.4),
        ):
            with self.subTest(material=material):
                self.assertIn(material, allowed)
                self.assertNotIn(material, inventory['amana_51404']['supported_materials'])
                self.assertNotIn(material, inventory['amana_51454']['supported_materials'])
                self.assertTrue(self.config.is_material_complete(material))
                preset = self.config.get_material_preset(material)
                self.assertAlmostEqual(parse_length(preset['stock_thickness']), expected_thickness)
                self.assertAlmostEqual(_resolve_job_tool(self.config, 'amana_51411', material), 0.125)

    def test_yaml_inventory_is_valid_and_bad_allowlist_is_rejected(self):
        with open(CONFIG_PATH, encoding='utf-8') as handle:
            source = handle.read()
        parsed, _ = validate_and_sanitize_config(source)
        self.assertIn('amana_51411', parsed['machines']['stepcraft_d600']['tool_inventory'])
        bad = source.replace('supported_materials: [acetal, polycarbonate, plywood]',
                             'supported_materials: [not_a_material]', 1)
        with self.assertRaises(ConfigValidationError):
            validate_and_sanitize_config(bad)

    def test_legacy_config_keeps_manual_diameter(self):
        self.assertAlmostEqual(_resolve_job_tool(TeamConfig({}), None, 'plywood', '4mm'),
                               4 / 25.4)

    def test_job_route_rejects_incompatible_cutter(self):
        app.config['TESTING'] = True
        client = app.test_client()
        with client.session_transaction() as sess:
            sess['app_verified'] = True
            sess['upload_config_data'] = self.config._data
        job = {'material': 'aluminum', 'tool_id': 'amana_51411',
               'tool_diameter': 0.125, 'parts': [{'file_index': 0, 'name': 'plate'}]}
        response = client.post('/process-job', data={'job': json.dumps(job)},
                               content_type='multipart/form-data')
        self.assertEqual(response.status_code, 400)
        self.assertIn('not approved', response.get_json()['error'])

    def test_new_materials_generate_with_named_cutter(self):
        app.config['TESTING'] = True
        client = app.test_client()
        with client.session_transaction() as sess:
            sess['app_verified'] = True
            sess['upload_config_data'] = self.config._data
        for material, thickness in (('hdpe_5865n112', 0.125),
                                    ('swyft_srpp_3mm', 3 / 25.4)):
            with self.subTest(material=material):
                job = {'material': material, 'tool_id': 'amana_51411',
                       'tool_diameter': 0.125, 'thickness': thickness,
                       'parts': [{'file_index': 0, 'name': 'test',
                                  'place_x': 0, 'place_y': 0, 'rotation': 0}]}
                response = client.post('/process-job', data={
                    'job': json.dumps(job),
                    'file_0': (io.BytesIO(_square_dxf_bytes(1.0)), 'test.dxf'),
                }, content_type='multipart/form-data')
                self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
                self.assertTrue(response.get_json()['success'])

    def test_process_route_rejects_missing_cutter(self):
        app.config['TESTING'] = True
        client = app.test_client()
        with client.session_transaction() as sess:
            sess['app_verified'] = True
            sess['upload_config_data'] = self.config._data
        response = client.post('/process', data={
            'file': (io.BytesIO(b'not read because validation fails'), 'part.dxf'),
            'material': 'acetal', 'tool_diameter': '0.125',
        }, content_type='multipart/form-data')
        self.assertEqual(response.status_code, 400)
        self.assertIn('Select a cutter', response.get_json()['error'])
