"""快速物化必须产生与公开构造器完全兼容的原始冻结记录。"""

import copy
import pickle
from dataclasses import FrozenInstanceError, asdict, fields, replace

import pytest
from test_general_runtime_review import CASES

from doribt.accounting.orders import Fill, IntentRecord, Order, Reason
from doribt.accounting.rights import CorporateEvent, EntitlementRecord
from doribt.accounting.taxes import TaxLotRecord, TaxPayment, TaxRecord

RECORDS = {
    "orders": Order,
    "intents": IntentRecord,
    "executions": Fill,
    "tax_lots": TaxLotRecord,
    "entitlements": EntitlementRecord,
    "corporate_events": CorporateEvent,
    "taxes": TaxRecord,
    "tax_payments": TaxPayment,
}


def assert_constructor_compatibility(record, expected_class):
    assert type(record) is expected_class
    names = tuple(field.name for field in fields(expected_class))
    values = {name: getattr(record, name) for name in names}
    for field in fields(expected_class):
        value = values[field.name]
        if field.type in (int, str, Reason):
            assert type(value) is field.type
        if field.type == (int | None) and value is not None:
            assert type(value) is int
    constructed = expected_class(**values)
    assert record == constructed
    assert hash(record) == hash(constructed)
    assert repr(record) == repr(constructed)
    assert asdict(record) == asdict(constructed)
    assert record.__dict__ == constructed.__dict__
    assert tuple(record.__dict__) == tuple(constructed.__dict__)
    assert record.__dict__ is not constructed.__dict__
    assert replace(record) == constructed
    assert copy.copy(record) == constructed
    assert copy.deepcopy(record) == constructed
    assert pickle.loads(pickle.dumps(record)) == constructed
    for name, descriptor in vars(expected_class).items():
        if isinstance(descriptor, property):
            assert getattr(record, name) == getattr(constructed, name)
    with pytest.raises(FrozenInstanceError):
        setattr(record, names[0], None)
    with pytest.raises(FrozenInstanceError):
        delattr(record, names[0])


@pytest.mark.parametrize(
    "scenario",
    [
        "broker_growth",
        "corporate_scheduled",
        "full_cash_weight_close_False_True",
        "persistent_scheduled",
        "legacy_snapshot",
        "final_unsized_weight",
    ],
)
def test_materialized_records_keep_public_dataclass_contract(backend, scenario):
    result, _ = CASES[scenario](backend)
    snapshots = []
    for name, expected_class in RECORDS.items():
        records = getattr(result, name)
        if records is None:
            continue
        assert type(records) is tuple
        # 各条记录必须独占字段字典，不能复用下一条记录的填充缓冲区。
        assert len({id(record.__dict__) for record in records}) == len(records)
        for record in records:
            assert_constructor_compatibility(record, expected_class)
            snapshots.append((record, copy.deepcopy(record.__dict__)))
    for record, saved in snapshots:
        assert record.__dict__ == saved


def test_private_factory_preserves_defaults_and_wrong_arity_errors():
    from datetime import date

    from doribt.accounting.records import record_factory

    values = (1, 2, 3, date(2025, 1, 2), "A", 100, 100000, 50000, 0, 0)
    factory = record_factory(Fill)
    assert factory(values) == Fill(*values)
    assert factory(values).__dict__ == Fill(*values).__dict__
    for invalid in ((), values + (None,) * 4):
        with pytest.raises(TypeError) as original:
            Fill(*invalid)
        with pytest.raises(TypeError) as actual:
            factory(invalid)
        assert str(actual.value) == str(original.value)


def test_private_factory_falls_back_for_other_dataclass_contracts():
    from dataclasses import dataclass, field

    from doribt.accounting.records import record_factory

    @dataclass(frozen=True, slots=True)
    class Checked:
        value: int
        items: list[int] = field(default_factory=list)
        derived: int = field(init=False)

        def __post_init__(self):
            if self.value < 0:
                raise ValueError("negative input")
            object.__setattr__(self, "derived", self.value * 2)

    factory = record_factory(Checked)
    first, second = factory((3,)), factory((3,))
    assert first == Checked(3) and first.derived == 6
    assert first.items is not second.items
    with pytest.raises(ValueError, match="negative input"):
        factory((-1,))


def test_private_factory_respects_custom_public_initializer(monkeypatch):
    from datetime import date

    from doribt.accounting.records import record_factory

    original = Fill.__init__
    observed = []

    def replacement(self, *args, **kwargs):
        observed.append((args, kwargs))
        original(self, *args, **kwargs)

    record_factory.cache_clear()
    monkeypatch.setattr(Fill, "__init__", replacement)
    try:
        values = (1, 2, 3, date(2025, 1, 2), "A", 100, 100000, 50000, 0, 0, None, None)
        record = record_factory(Fill)(values)
        assert observed == [(values, {})]
        assert type(record) is Fill and record.quantity == 100
    finally:
        record_factory.cache_clear()
