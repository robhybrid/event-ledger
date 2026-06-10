"""Pact provider verification: Account Service satisfies Gateway contracts."""

import pytest
from pact import Verifier

from tests.contract.conftest import (
    PACT_DIR,
    reset_account_state,
    seed_account_balance_state,
)

PACT_FILE = PACT_DIR / "event-gateway-account-service.json"


@pytest.mark.skipif(not PACT_FILE.exists(), reason="Run consumer Pact tests first")
def test_account_service_honours_gateway_contract(account_service_url):
    verifier = (
        Verifier("account-service")
        .add_transport(url=account_service_url)
        .add_source(PACT_DIR)
        .state_handler(
            {
                "": reset_account_state,
                "account has no prior transactions": reset_account_state,
                "account has a credit balance": seed_account_balance_state,
            }
        )
        .set_coloured_output(enabled=False)
    )

    verifier.verify()
    output = verifier.output(strip_ansi=True)
    assert "FAILED" not in output, output
    assert output.count("(OK)") >= 2, output
