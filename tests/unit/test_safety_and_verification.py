import pytest
from unittest.mock import MagicMock, patch
from src.infrastructure.fpl.client import FPLClient
from src.domain.models.player import Player
from src.domain.models.transfer import Transfer
from scheduler import check_final_safety


def test_get_my_team_require_authenticated_fails_when_unauthenticated():
    client = FPLClient(bearer_token="", cookie="", dry_run=True)
    client.is_authenticated = False
    with pytest.raises(PermissionError, match="Authentication required"):
        client.get_my_team(12345, require_authenticated=True)


def test_get_my_team_does_not_fall_back_to_squad_data_json():
    client = FPLClient(bearer_token="", cookie="", dry_run=True)
    client.is_authenticated = False

    # Mock history, public entry, and picks endpoint returning 404
    mock_resp_hist = MagicMock()
    mock_resp_hist.status_code = 200
    mock_resp_hist.json.return_value = {"chips": [], "current": []}

    mock_resp_entry = MagicMock()
    mock_resp_entry.status_code = 200
    mock_resp_entry.json.return_value = {
        "current_event": 1,
        "last_deadline_bank": 10,
        "last_deadline_value": 1000
    }

    mock_resp_picks = MagicMock()
    mock_resp_picks.status_code = 404

    with patch.object(client.session, "get", side_effect=[mock_resp_hist, mock_resp_entry, mock_resp_picks]):
        data = client.get_my_team(12345, require_authenticated=False)

        assert data["is_authenticated"] is False
        assert data["is_live"] is False
        # Picks must NOT be fabricated from squad_data.json
        assert data["picks"] == []


def test_set_lineup_error_propagation_when_rejected():
    client = FPLClient(bearer_token="valid_token", dry_run=False)
    client.is_authenticated = True

    mock_resp = MagicMock()
    mock_resp.status_code = 403
    mock_resp.text = "Forbidden / CSRF failure"

    with patch.object(client.session, "post", return_value=mock_resp):
        res = client.set_lineup(12345, [{"element": 1, "position": 1}])
        assert res["status"] == "error"
        assert res["success"] is False
        assert "403" in res["error"]


def test_make_transfers_error_propagation_when_rejected():
    client = FPLClient(bearer_token="valid_token", dry_run=False)
    client.is_authenticated = True

    mock_resp = MagicMock()
    mock_resp.status_code = 401
    mock_resp.text = "Unauthorized"

    p_in = Player(id=1, name="In", full_name="Player In", position_id=3, position="MID", team_id=1, team_name="Arsenal", team_short="ARS", cost=6.0, now_cost=60)
    p_out = Player(id=2, name="Out", full_name="Player Out", position_id=3, position="MID", team_id=1, team_name="Arsenal", team_short="ARS", cost=6.0, now_cost=60)
    transfer = Transfer(player_out=p_out, player_in=p_in)

    with patch.object(client.session, "post", return_value=mock_resp):
        res = client.make_transfers(12345, [transfer], next_gw=8)
        assert res["status"] == "error"
        assert res["success"] is False
        assert "401" in res["error"]


def test_verify_live_squad_detects_mismatch():
    client = FPLClient(bearer_token="valid_token", dry_run=False)
    client.is_authenticated = True

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "picks": [
            {"element": 10, "position": 1, "is_captain": True},
            {"element": 20, "position": 2, "is_captain": False}
        ]
    }

    with patch.object(client.session, "get", return_value=mock_resp):
        # We expected player 99 to be captain, but server has player 10
        verified, details = client.verify_live_squad(12345, expected_captain_id=99)
        assert verified is False
        assert "Captain mismatch" in details["error"]

        # If expected is player 10, it matches
        verified2, details2 = client.verify_live_squad(12345, expected_captain_id=10)
        assert verified2 is True


def test_check_final_safety_alerts_and_aborts_when_unauthenticated():
    mock_repo = MagicMock()
    mock_notifier = MagicMock()

    with patch("scheduler.TelegramNotifier", return_value=mock_notifier), \
         patch("scheduler.FPLClient") as mock_client_cls:
        
        mock_gateway = MagicMock()
        mock_gateway.is_authenticated = False
        mock_client_cls.return_value = mock_gateway

        # In LIVE mode (dry_run=False), unauthenticated must trigger critical alert and abort
        check_final_safety(mock_repo, team_id=12345, dry_run=False, auto_fix=True)

        assert mock_notifier.send_message.called
        sent_text = mock_notifier.send_message.call_args[0][0]
        assert "إنذار أمان تكتيكي حرج" in sent_text
        assert "تعذر الاتصال المباشر بحسابك" in sent_text
