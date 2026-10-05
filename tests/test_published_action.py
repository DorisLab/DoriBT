import importlib.util
from pathlib import Path

from doribt import Backtest


def test_issuer_action_with_independent_account_ledger(backend):
    path = Path(__file__).parents[1] / "examples" / "historical_rules.py"
    spec = importlib.util.spec_from_file_location("historical_rules_example", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    result = Backtest(module.sample(), initial_cash=20000).run(
        module.sell_on_ex_date, backend=backend
    )
    # 1,000 original shares get 500 yuan cash and 800 non-taxable reserve shares.
    # Buy: 18,500 + 5.55 commission + .19 transfer = 18,505.74.
    # Sell: 18,000 - 5.40 commission - 18 stamp - .18 transfer = 17,976.42.
    # Net tax disposal is 1,000, not the 1,800 actually sold on the credit date.
    # Tax: 1,000 * .5 * 20% = 100; paid the next input trading session.
    assert [(f.quantity, f.commission, f.stamp_duty, f.transfer_fee) for f in result.fills] == [
        (1000, 5.55, 0, 0.19),
        (-1800, 5.4, 18, 0.18),
    ]
    assert result.cash_units.tolist() == [200000000, 14942600, 199706800, 198706800]
    assert result.tax_payable_units.tolist() == [0, 0, 1000000, 0]
    assert result.equity_units[-1] == 198706800
    assert result.entitlements[0].bonus_quantity == 800
    assert result.entitlements[0].cash_units == 5000000
    assert len(result.tax_payments) == 1
    assert result.tax_payments[0].amount_units == 1000000
