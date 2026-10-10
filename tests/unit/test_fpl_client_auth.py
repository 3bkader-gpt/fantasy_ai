import pytest
from src.infrastructure.fpl.client import FPLClient
from src.domain.models.player import Player
from src.domain.models.transfer import Transfer

def test_fpl_client_bearer_token_initialization():
    client = FPLClient(bearer_token="my_secret_token", dry_run=True)
    assert client.is_authenticated is True
    assert client.session.headers.get("x-api-authorization") == "Bearer my_secret_token"

def test_fpl_client_bearer_token_already_prefixed():
    client = FPLClient(bearer_token="Bearer existing_token", dry_run=True)
    assert client.is_authenticated is True
    assert client.session.headers.get("x-api-authorization") == "Bearer existing_token"

def test_fpl_client_dry_run_bypasses_network():
    client = FPLClient(bearer_token="my_token", dry_run=True)
    res = client.set_lineup(12345, [{"element": 1, "position": 1}])
    assert res.get("status") == "simulated"
    assert res.get("dry_run") is True

    p_in = Player(id=1, name="In", full_name="Player In", position_id=3, position="MID", team_id=1, team_name="Arsenal", team_short="ARS", cost=6.0, now_cost=60)
    p_out = Player(id=2, name="Out", full_name="Player Out", position_id=3, position="MID", team_id=1, team_name="Arsenal", team_short="ARS", cost=6.0, now_cost=60)
    transfer = Transfer(player_out=p_out, player_in=p_in)
    
    t_res = client.make_transfers(12345, [transfer], next_gw=7)
    assert t_res.get("status") == "simulated"
