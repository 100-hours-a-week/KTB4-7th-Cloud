import copy
import sys
from pathlib import Path
import unittest
from test_ecs_deployment import MODULE, definition, batch_definition, DIGEST, SHA

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'deploy/ecs'))
import check_outbox_runtime as audit


def environment(td):
    return {x['name']: x['value'] for x in td['containerDefinitions'][0].get('environment', [])}


def setting(td, name, value):
    td['containerDefinitions'][0]['environment'].append({'name': name, 'value': value})


class OutboxRuntimeTests(unittest.TestCase):
    def test_adds_role_without_enabling_outbox_or_changing_existing_profiles_and_secrets(self):
        for kind, original in [('web', definition()), ('batch', batch_definition())]:
            setting(original, 'SPRING_PROFILES_ACTIVE', 'production-redis,production-pool-evict')
            before = copy.deepcopy(original)
            candidate = MODULE.prepare_definition(original, DIGEST, SHA, kind)
            env = environment(candidate)
            self.assertEqual(env['SPRING_PROFILES_ACTIVE'],
                             'production-redis,production-pool-evict,sales-outbox-' + kind)
            self.assertEqual(env['SALES_OUTBOX_DISPATCH_ENABLED'], 'false' if kind == 'web' else 'true')
            self.assertNotIn('SALES_OUTBOX_ENABLED', env)
            self.assertEqual(candidate['containerDefinitions'][0]['secrets'], before['containerDefinitions'][0]['secrets'])
            self.assertEqual(original, before)

    def test_enabled_web_and_batch_require_s3_but_keep_activation_opt_in(self):
        for kind, td in [('web', definition()), ('batch', batch_definition())]:
            setting(td, 'SALES_OUTBOX_ENABLED', 'true')
            setting(td, 'SALES_STORAGE_TYPE', 's3')
            setting(td, 'SALES_STORAGE_S3_BUCKET', 'shared-sales-bucket')
            candidate = MODULE.prepare_definition(td, DIGEST, SHA, kind)
            self.assertEqual(environment(candidate)['SALES_OUTBOX_ENABLED'], 'true')
            self.assertEqual(environment(candidate)['SALES_STORAGE_S3_BUCKET'], 'shared-sales-bucket')

    def test_rejects_local_or_unspecified_storage_before_registration(self):
        for kind, td in [('web', definition()), ('batch', batch_definition())]:
            setting(td, 'SALES_OUTBOX_ENABLED', 'true')
            for storage in ('local', ''):
                candidate = copy.deepcopy(td)
                setting(candidate, 'SALES_STORAGE_TYPE', storage)
                with self.assertRaisesRegex(MODULE.DeploymentError, 'STORAGE_TYPE'):
                    MODULE.prepare_definition(candidate, DIGEST, SHA, kind)

    def test_rejects_missing_bucket_and_preserves_secret_bucket_reference(self):
        td = definition()
        setting(td, 'SALES_OUTBOX_ENABLED', 'true')
        setting(td, 'SALES_STORAGE_TYPE', 's3')
        with self.assertRaisesRegex(MODULE.DeploymentError, 'bucket reference'):
            MODULE.prepare_definition(td, DIGEST, SHA)
        secret = {'name': 'SALES_STORAGE_S3_BUCKET', 'valueFrom': 'arn:example:shared-bucket'}
        td['containerDefinitions'][0]['secrets'].append(secret)
        candidate = MODULE.prepare_definition(td, DIGEST, SHA)
        self.assertIn(secret, candidate['containerDefinitions'][0]['secrets'])

    def test_normalizes_dispatch_role_even_if_old_revision_did_not_separate_workers(self):
        for kind, td, expected in [('web', definition(), 'false'), ('batch', batch_definition(), 'true')]:
            setting(td, 'SALES_OUTBOX_DISPATCH_ENABLED', 'true' if kind == 'web' else 'false')
            candidate = MODULE.prepare_definition(td, DIGEST, SHA, kind)
            matches = [x for x in candidate['containerDefinitions'][0]['environment']
                       if x['name'] == 'SALES_OUTBOX_DISPATCH_ENABLED']
            self.assertEqual(matches, [{'name': 'SALES_OUTBOX_DISPATCH_ENABLED', 'value': expected}])

    def test_never_overwrites_secret_profile_or_activation_controls(self):
        for name in ('SPRING_PROFILES_ACTIVE', 'SALES_OUTBOX_ENABLED', 'SALES_OUTBOX_DISPATCH_ENABLED'):
            td = definition()
            td['containerDefinitions'][0]['secrets'].append({'name': name, 'valueFrom': 'private-reference'})
            before = copy.deepcopy(td)
            with self.assertRaises(MODULE.DeploymentError) as error:
                MODULE.prepare_definition(td, DIGEST, SHA)
            self.assertNotIn('private-reference', str(error.exception))
            self.assertEqual(td, before)

    def test_rejects_conflicting_profiles_duplicate_values_and_alias_overrides(self):
        bad = []
        profile = definition(); setting(profile, 'SPRING_PROFILES_ACTIVE', 'sales-outbox-batch'); bad.append(profile)
        duplicate = definition()
        setting(duplicate, 'SALES_OUTBOX_ENABLED', 'true')
        setting(duplicate, 'SALES_OUTBOX_ENABLED', 'false'); bad.append(duplicate)
        alias = definition(); setting(alias, 'APP_SALES_OUTBOX_DISPATCH_ENABLED', 'true'); bad.append(alias)
        for td in bad:
            with self.assertRaises(MODULE.DeploymentError):
                MODULE.prepare_definition(td, DIGEST, SHA)

    def test_preparation_is_idempotent_and_rollback_validation_preserves_old_definition(self):
        td = MODULE.prepare_definition(definition(), DIGEST, SHA)
        self.assertEqual(MODULE.prepare_definition(td, DIGEST, SHA), td)
        legacy = definition(); before = copy.deepcopy(legacy)
        MODULE.validate_definition(legacy)
        self.assertEqual(legacy, before)


class OutboxMetadataAuditTests(unittest.TestCase):
    def pair(self, enabled='true'):
        definitions = []
        for kind, td in [('web', definition()), ('batch', batch_definition())]:
            setting(td, 'SALES_OUTBOX_ENABLED', enabled)
            setting(td, 'SALES_STORAGE_TYPE', 's3')
            setting(td, 'SALES_STORAGE_S3_BUCKET', 'same-bucket')
            td['containerDefinitions'][0]['secrets'].append({'name': 'DB_URL', 'valueFrom': 'same-db-reference'})
            definitions.append(MODULE.prepare_definition(td, DIGEST, SHA, kind))
        return definitions

    def test_equal_references_are_metadata_pass_without_claiming_network_verification(self):
        result = audit.audit_definitions(*self.pair())
        self.assertEqual(result['status'], 'METADATA_PASS')
        self.assertFalse(result['db_route_verified'])
        self.assertFalse(result['s3_access_verified'])
        self.assertNotIn('same-bucket', str(result))
        self.assertNotIn('same-db-reference', str(result))

    def test_disabled_pair_is_not_reported_as_enabled_or_operationally_verified(self):
        result = audit.audit_definitions(*self.pair('false'))
        self.assertEqual(result['status'], 'DISABLED')
        self.assertFalse(result['outbox_enabled'])

    def test_mismatched_activation_bucket_or_database_is_rejected(self):
        for mismatch in ('activation', 'bucket', 'database'):
            web, batch = self.pair()
            container = batch['containerDefinitions'][0]
            if mismatch == 'database':
                container['secrets'][-1]['valueFrom'] = 'different-secret'
            else:
                name = 'SALES_OUTBOX_ENABLED' if mismatch == 'activation' else 'SALES_STORAGE_S3_BUCKET'
                for entry in container['environment']:
                    if entry['name'] == name:
                        entry['value'] = 'false' if mismatch == 'activation' else 'different-bucket'
            with self.assertRaises(audit.DeploymentError):
                audit.audit_definitions(web, batch)

    def test_wrong_role_or_dispatch_flag_cannot_be_hidden_by_metadata_normalization(self):
        for name, value in [('SPRING_PROFILES_ACTIVE', 'sales-outbox-batch'),
                            ('SALES_OUTBOX_DISPATCH_ENABLED', 'true')]:
            web, batch = self.pair()
            for entry in web['containerDefinitions'][0]['environment']:
                if entry['name'] == name:
                    entry['value'] = value
            with self.assertRaises(audit.DeploymentError):
                audit.audit_definitions(web, batch)

    def test_same_bucket_with_different_region_or_endpoint_is_not_a_shared_storage_pass(self):
        for name, value in [('SALES_STORAGE_S3_REGION', 'us-east-1'),
                            ('SALES_STORAGE_S3_ENDPOINT', 'https://different.example'),
                            ('SALES_STORAGE_S3_PATH_STYLE_ACCESS', 'true')]:
            web, batch = self.pair()
            setting(batch, name, value)
            with self.assertRaises(audit.DeploymentError):
                audit.audit_definitions(web, batch)


if __name__ == '__main__':
    unittest.main()
