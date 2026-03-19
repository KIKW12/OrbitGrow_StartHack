import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..'))

import json
from unittest.mock import patch, MagicMock


# run-sol returns HTTP 200 with correct response shape
def test_run_sol_returns_200_shape():
    with patch("lambdas.run_sol.handler.dynamodb") as mock_ddb, \
         patch("lambdas.run_sol.handler.lambda_client") as mock_lambda, \
         patch("lambdas.run_sol.handler.OrchestratorAgent") as mock_orch, \
         patch("lambdas.run_sol.handler.MCPClient") as mock_mcp:

        mock_table = MagicMock()
        mock_ddb.Table.return_value = mock_table
        mock_table.scan.return_value = {"Items": []}

        mock_mcp_instance = MagicMock()
        mock_mcp.return_value = mock_mcp_instance
        mock_mcp_instance.query.return_value = {
            "kb_fallback": False,
            "nutritional_profiles": {},
            "base_yields_per_m2": {},
            "harvest_cycles_sol": {},
            "optimal_bands": {},
            "stress_multipliers": {},
        }

        mock_orch_instance = MagicMock()
        mock_orch.return_value = mock_orch_instance
        mock_orch_instance.run.return_value = {
            "nutrition_report": {
                "coverage_score": 75.0,
                "crew_health_statuses": [],
                "crew_health_emergency": False,
            },
            "crew_health_statuses": [],
            "crew_health_emergency": False,
        }

        from lambdas.run_sol.handler import handler
        response = handler({}, None)

    assert response["statusCode"] == 200
    body = json.loads(response["body"])
    assert "mission_state" in body
    assert "environment_state" in body
    assert "nutrition_ledger" in body
    assert "sol_reports" in body


# run-sol returns HTTP 500 on DynamoDB failure
def test_run_sol_returns_500_on_dynamodb_failure():
    with patch("lambdas.run_sol.handler.dynamodb") as mock_ddb:
        mock_ddb.Table.side_effect = Exception("DynamoDB connection failed")
        from lambdas.run_sol.handler import handler
        response = handler({}, None)
    assert response["statusCode"] == 500
    body = json.loads(response["body"])
    assert "message" in body
    assert "sol" in body


# chat returns HTTP 503 on agent timeout
def test_chat_returns_503_on_timeout():
    with patch("lambdas.chat.handler.dynamodb") as mock_ddb, \
         patch("lambdas.chat.handler.OrchestratorAgent") as mock_orch:

        mock_table = MagicMock()
        mock_ddb.Table.return_value = mock_table
        mock_table.scan.return_value = {"Items": []}

        mock_orch_instance = MagicMock()
        mock_orch.return_value = mock_orch_instance

        with patch("threading.Thread") as mock_thread_cls:
            mock_thread = MagicMock()
            mock_thread_cls.return_value = mock_thread
            mock_thread.is_alive.return_value = True  # simulate timeout

            event = {"body": json.dumps({"message": "What is the mission status?"})}
            from lambdas.chat.handler import handler
            response = handler(event, None)

    assert response["statusCode"] == 503


# WebSocket connect stores connection_id
def test_ws_connect_stores_connection_id():
    with patch("lambdas.ws_connect.handler.dynamodb") as mock_ddb:
        mock_table = MagicMock()
        mock_ddb.Table.return_value = mock_table

        from lambdas.ws_connect.handler import handler
        event = {"requestContext": {"connectionId": "test-conn-123"}}
        response = handler(event, None)

    assert response["statusCode"] == 200
    mock_table.put_item.assert_called_once()
    call_args = mock_table.put_item.call_args[1]["Item"]
    assert call_args["connection_id"] == "test-conn-123"


# WebSocket disconnect removes connection_id
def test_ws_disconnect_removes_connection_id():
    with patch("lambdas.ws_disconnect.handler.dynamodb") as mock_ddb:
        mock_table = MagicMock()
        mock_ddb.Table.return_value = mock_table

        from lambdas.ws_disconnect.handler import handler
        event = {"requestContext": {"connectionId": "test-conn-123"}}
        response = handler(event, None)

    assert response["statusCode"] == 200
    mock_table.delete_item.assert_called_once_with(Key={"connection_id": "test-conn-123"})


# Stale connection cleaned up during broadcast
def test_ws_broadcast_cleans_stale_connections():
    from botocore.exceptions import ClientError
    import lambdas.ws_broadcast.handler as ws_broadcast_module

    with patch("lambdas.ws_broadcast.handler.dynamodb") as mock_ddb, \
         patch("lambdas.ws_broadcast.handler.boto3") as mock_boto3, \
         patch.object(ws_broadcast_module, "WEBSOCKET_API_ENDPOINT",
                      "https://test.execute-api.us-east-2.amazonaws.com/prod"):

        mock_table = MagicMock()
        mock_ddb.Table.return_value = mock_table
        mock_table.scan.return_value = {"Items": [{"connection_id": "stale-conn"}]}

        mock_apigw = MagicMock()
        mock_boto3.client.return_value = mock_apigw

        error_response = {"Error": {"Code": "GoneException", "Message": "Gone"}}
        mock_apigw.post_to_connection.side_effect = ClientError(error_response, "PostToConnection")

        from lambdas.ws_broadcast.handler import handler
        response = handler({"crises_active": []}, None)

        mock_table.delete_item.assert_called_once_with(Key={"connection_id": "stale-conn"})
    assert response["statusCode"] == 200
