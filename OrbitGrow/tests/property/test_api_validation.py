# Feature: orbitgrow-backend, Property 20: Chat input validation rejects out-of-range messages
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..'))

import json
from hypothesis import given, settings, strategies as st
from lambdas.chat.handler import handler as chat_handler


# Property 20a: empty message returns 400
@given(message=st.just(""))
@settings(max_examples=10)
def test_empty_message_returns_400(message):
    event = {"body": json.dumps({"message": message})}
    response = chat_handler(event, None)
    assert response["statusCode"] == 400


# Property 20b: message longer than 2000 chars returns 400
@given(message=st.text(min_size=2001, max_size=3000))
@settings(max_examples=100)
def test_too_long_message_returns_400(message):
    event = {"body": json.dumps({"message": message})}
    response = chat_handler(event, None)
    assert response["statusCode"] == 400
