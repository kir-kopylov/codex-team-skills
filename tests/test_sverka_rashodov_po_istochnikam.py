"""Проверки связей и арифметики на вымышленных операциях."""

import copy
import importlib.util
import json
from pathlib import Path
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / 'plugins/team-skills/skills/sverka-rashodov-po-istochnikam'
SCRIPT = SKILL / 'scripts/check_ledger.py'
SPEC = importlib.util.spec_from_file_location('expense_checker', SCRIPT)
CHECKER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CHECKER)


def sample(name='complete'):
    return json.loads((SKILL / 'assets' / f'{name}.json').read_text())


def result(data):
    return CHECKER.validate(data)


def remaining(data):
    return result(data)['claims'][0]['remaining_amount']


def known(report):
    return report['by_currency']['KZT']['known_amount']


@pytest.mark.parametrize('path', sorted((SKILL / 'assets').glob('*.json')), ids=lambda p: p.stem)
def test_every_asset_uses_the_same_contract(path):
    output = result(json.loads(path.read_text()))
    expected = {'complete': '6000', 'unknown': None, 'cutoff-funding': '10000'}
    assert output['claims'][0]['remaining_amount'] == expected[path.stem]


def test_complete_receipt_and_bank_document_are_one_payment():
    data = sample()
    before = copy.deepcopy(data)
    output = result(data)
    assert known(output['expense_facts']) == '12000'
    assert known(output['movements_as_of']['payment']) == '12000'
    assert output['claims'][0]['remaining_amount'] == '6000'
    assert output['claims'][0]['status'] == 'calculated'
    assert data == before


def test_missing_agreement_only_blocks_the_claim():
    data = sample()
    before = result(data)
    data['claims'][0]['agreement_source_ids'] = []
    after = result(data)
    assert after['claims'][0]['remaining_amount'] is None
    assert before['expense_facts'] == after['expense_facts']
    assert before['movements_as_of'] == after['movements_as_of']


def test_proposal_does_not_change_facts_or_agreed_remaining():
    data = sample()
    before = result(data)
    data['claims'][0]['proposed_amount'] = '1'
    after = result(data)
    assert before['expense_facts'] == after['expense_facts']
    assert before['movements_as_of'] == after['movements_as_of']
    assert after['claims'][0]['remaining_amount'] == '6000'
    assert after['claims'][0]['proposed_amount'] == '1'


def test_unknown_expense_amount_is_not_zero():
    data = sample()
    data['expenses'][0]['amount'] = None
    output = result(data)
    summary = output['expense_facts']
    assert summary['by_currency']['KZT'] == {'known_amount': '0', 'amount': None, 'unknown_count': 1}
    assert summary['incomplete']
    assert output['claims'][0]['remaining_amount'] is None
    assert known(output['movements_as_of']['payment']) == '12000'


def test_unknown_expense_date_preserves_fact_but_blocks_cutoff():
    data = sample()
    data['expenses'][0]['date'] = None
    output = result(data)
    assert known(output['expense_facts']) == '12000'
    assert output['expenses_as_of']['unknown_date_ids'] == ['e1']
    assert output['expenses_as_of']['by_currency']['KZT']['amount'] is None
    assert output['claims'][0]['remaining_amount'] is None


@pytest.mark.parametrize('field', ['payer', 'payee', 'funds_owner', 'date', 'currency', 'amount'])
def test_unknown_payment_field_only_blocks_dependent_result(field):
    data = sample()
    data['movements'][0][field] = None
    output = result(data)
    assert output['claims'][0]['remaining_amount'] is None
    assert known(output['expense_facts']) == '12000'


def test_unknown_allocation_amount_blocks_claim():
    data = sample()
    data['allocations'][0]['amount'] = None
    assert remaining(data) is None


def test_unrelated_unknown_record_does_not_block_known_claim():
    data = sample()
    data['expenses'].append({'id': 'e2', 'object': None, 'date': None, 'amount': None,
                             'currency': None, 'confirmed': True, 'source_ids': ['s1']})
    output = result(data)
    assert output['claims'][0]['remaining_amount'] == '6000'
    assert output['expense_facts']['incomplete']
    assert output['expense_facts']['unknown_currency_ids'] == ['e2']


def test_unconfirmed_without_sources_is_valid_and_not_counted():
    data = sample()
    data['movements'][0]['confirmed'] = False
    data['movements'][0]['source_ids'] = []
    output = result(data)
    assert 'm1' in output['unconfirmed_ids']
    assert output['movements_as_of']['payment']['by_currency']['KZT']['amount'] is None
    assert known(output['movements_as_of']['payment']) == '0'
    assert output['movements_as_of']['payment']['incomplete']
    assert output['claims'][0]['remaining_amount'] is None


def test_not_applicable_has_no_agreement_waiting_status():
    data = sample()
    claim = data['claims'][0]
    claim.update(applicable=False, proposed_amount=None, agreed_amount=None,
                 agreement_source_ids=[], coverage_source_ids=[], payments_complete=False,
                 refunds_complete=False, reimbursements_complete=False,
                 payment_allocation_ids=[], refund_allocation_ids=[], reimbursement_allocation_ids=[])
    output = result(data)
    assert output['claims'][0]['status'] == 'not_applicable'
    assert output['claims'][0]['reasons'] == []
    assert known(output['expense_facts']) == '12000'


def test_explicit_agreed_zero_is_not_unknown():
    data = sample()
    data['claims'][0].update(agreed_amount='0', refund_allocation_ids=[], reimbursement_allocation_ids=[])
    assert remaining(data) == '0'


@pytest.mark.parametrize('flag', ['payments_complete', 'refunds_complete', 'reimbursements_complete'])
def test_incomplete_coverage_prevents_false_final_amount(flag):
    data = sample()
    data['claims'][0][flag] = False
    assert remaining(data) is None


def test_coverage_needs_its_own_source():
    data = sample()
    data['claims'][0]['coverage_source_ids'] = []
    assert remaining(data) is None


def test_funding_separate_future_reimbursement_excluded():
    output = result(sample('cutoff-funding'))
    assert known(output['movements_as_of']['funding']) == '12000'
    assert known(output['movements_as_of']['payment']) == '12000'
    assert output['movements_as_of']['reimbursement']['after_cutoff_ids'] == ['m3']
    assert output['claims'][0]['remaining_amount'] == '10000'


def test_future_expense_does_not_disappear_but_cannot_be_claimed_on_cutoff():
    data = sample()
    data['expenses'][0]['date'] = '2026-02-02'
    output = result(data)
    assert known(output['expense_facts']) == '12000'
    assert output['expenses_as_of']['after_cutoff_ids'] == ['e1']
    assert output['claims'][0]['remaining_amount'] is None


def test_duplicate_bank_key_with_new_id_is_rejected():
    data = sample()
    duplicate = copy.deepcopy(data['movements'][0])
    duplicate['id'] = 'm4'
    data['movements'].append(duplicate)
    with pytest.raises(CHECKER.LedgerError, match='transaction_key'):
        result(data)


@pytest.mark.parametrize('target,field,value', [
    ('allocations', 'movement_id', 'missing'), ('allocations', 'expense_id', 'missing'),
    ('claims', 'expense_id', 'missing'), ('expenses', 'source_ids', ['missing']),
    ('claims', 'agreement_source_ids', ['missing']),
    ('claims', 'coverage_source_ids', ['missing']),
    ('claims', 'payment_allocation_ids', ['missing']),
])
def test_missing_references_are_rejected(target, field, value):
    data = sample()
    data[target][0][field] = value
    with pytest.raises(CHECKER.LedgerError):
        result(data)


def test_allocation_sum_cannot_exceed_payment_even_with_two_expenses():
    data = sample()
    expense = copy.deepcopy(data['expenses'][0])
    expense['id'] = 'e2'
    data['expenses'].append(expense)
    allocation = copy.deepcopy(data['allocations'][0])
    allocation.update(id='a4', expense_id='e2', amount='1')
    data['allocations'].append(allocation)
    with pytest.raises(CHECKER.LedgerError, match='больше'):
        result(data)


def test_unknown_other_allocation_prevents_claiming_proven_payment_limit():
    data = sample()
    allocation = copy.deepcopy(data['allocations'][0])
    allocation.update(id='a4', amount=None, confirmed=False, source_ids=[])
    data['allocations'].append(allocation)
    output = result(data)
    assert output['claims'][0]['remaining_amount'] is None
    assert known(output['movements_as_of']['payment']) == '12000'


def test_funding_cannot_masquerade_as_expense_or_reimbursement():
    data = sample()
    data['movements'][0]['kind'] = 'funding'
    with pytest.raises(CHECKER.LedgerError, match='финансирование'):
        result(data)


def test_cross_currency_allocation_is_rejected():
    data = sample()
    data['movements'][0]['currency'] = 'USD'
    with pytest.raises(CHECKER.LedgerError, match='валюты'):
        result(data)


def test_currency_totals_are_separate():
    data = sample()
    expense = copy.deepcopy(data['expenses'][0])
    expense.update(id='e2', currency='USD', amount='3.14')
    data['expenses'].append(expense)
    output = result(data)
    assert output['expense_facts']['by_currency']['USD']['amount'] == '3.14'
    assert known(output['expense_facts']) == '12000'


@pytest.mark.parametrize('value', [12000, 12.1, -1, '-1', '1e2', 'NaN', '', '01', True])
def test_noncanonical_amounts_are_rejected(value):
    data = sample()
    data['expenses'][0]['amount'] = value
    with pytest.raises(CHECKER.LedgerError):
        result(data)


def test_decimal_arithmetic_has_no_float_rounding():
    data = sample()
    data['expenses'][0]['amount'] = '0.3'
    for row, value in zip(data['movements'], ['0.3', '0.1', '0.1']):
        row['amount'] = value
    for row, value in zip(data['allocations'], ['0.3', '0.1', '0.1']):
        row['amount'] = value
    data['claims'][0].update(proposed_amount='0.3', agreed_amount='0.3')
    assert remaining(data) == '0.1'


@pytest.mark.parametrize('section', ['sources', 'expenses', 'movements', 'allocations', 'claims'])
def test_duplicate_id_is_rejected(section):
    data = sample()
    data[section].append(copy.deepcopy(data[section][0]))
    with pytest.raises(CHECKER.LedgerError, match='повтор ID'):
        result(data)


def test_repeated_allocation_reference_is_rejected():
    data = sample()
    data['claims'][0]['payment_allocation_ids'].append('a1')
    with pytest.raises(CHECKER.LedgerError, match='повтор ссылки'):
        result(data)


def test_reimbursement_sender_may_be_representative_using_debtor_funds():
    data = sample()
    data['movements'][2]['payer'] = 'manager'
    assert remaining(data) == '6000'
    data['movements'][2]['funds_owner'] = None
    assert remaining(data) is None


def test_partial_agreement_uses_only_explicit_refund_part():
    data = sample()
    data['claims'][0]['agreed_amount'] = '6000'
    data['allocations'][1]['amount'] = '1000'
    output = result(data)
    assert output['claims'][0]['remaining_amount'] == '1000'
    assert known(output['movements_as_of']['refund']) == '2000'


def test_already_net_agreement_does_not_automatically_subtract_old_coverage():
    data = sample()
    data['claims'][0].update(agreed_amount='6000', refund_allocation_ids=[],
                             reimbursement_allocation_ids=[])
    output = result(data)
    assert output['claims'][0]['remaining_amount'] == '6000'
    assert known(output['movements_as_of']['refund']) == '2000'
    assert known(output['movements_as_of']['reimbursement']) == '4000'


def test_overpayment_is_reported_without_authorizing_reverse_transfer():
    data = sample()
    data['claims'][0]['agreed_amount'] = '5000'
    output = result(data)['claims'][0]
    assert output['remaining_amount'] == '-1000'
    assert output['status'] == 'overpaid'


def test_missing_or_extra_field_is_rejected():
    data = sample()
    data['expenses'][0]['invented'] = 'anything'
    with pytest.raises(CHECKER.LedgerError):
        result(data)
    del data['expenses'][0]['invented']
    del data['expenses'][0]['date']
    with pytest.raises(CHECKER.LedgerError):
        result(data)


@pytest.mark.parametrize('mutator', [
    lambda d: d['claims'][0].update(agreed_amount='12001'),
    lambda d: d['allocations'][0].update(expense_id=[]),
    lambda d: d['movements'][0].update(kind=[]),
    lambda d: d['expenses'][0].update(date='2026-02-30'),
    lambda d: d['expenses'][0].update(confirmed=True, source_ids=[]),
    lambda d: d['claims'][0].update(applicable=False),
])
def test_other_corruptions_fail_cleanly(mutator):
    data = sample()
    mutator(data)
    with pytest.raises(CHECKER.LedgerError):
        result(data)


def cli(path):
    return subprocess.run([sys.executable, str(SCRIPT), str(path)], text=True,
                          capture_output=True, check=False)


def test_cli_read_only_and_structured_output(tmp_path):
    path = tmp_path / 'input.json'
    original = json.dumps(sample(), ensure_ascii=False).encode()
    path.write_bytes(original)
    output = cli(path)
    assert output.returncode == 0, output.stderr
    assert json.loads(output.stdout)['claims'][0]['remaining_amount'] == '6000'
    assert not output.stderr
    assert path.read_bytes() == original
    assert list(tmp_path.iterdir()) == [path]


@pytest.mark.parametrize('content', ['{"schema_version":1,"schema_version":1}', '{bad json', '[]'])
def test_cli_corrupt_input_fails_without_success_output(tmp_path, content):
    path = tmp_path / 'bad.json'
    path.write_text(content)
    output = cli(path)
    assert output.returncode == 2
    assert not output.stdout
    assert json.loads(output.stderr)['error']


def test_cli_requires_absolute_path():
    output = cli('relative.json')
    assert output.returncode == 2
    assert 'абсолютный' in json.loads(output.stderr)['error']
