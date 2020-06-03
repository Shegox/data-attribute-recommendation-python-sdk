from io import BytesIO
from unittest.mock import create_autospec, Mock, call

import pytest
import requests
from requests.structures import CaseInsensitiveDict

from sap.aibus.dar.client.util.credentials import StaticCredentialsSource
from sap.aibus.dar.client.dar_session import DARSession
from sap.aibus.dar.client.exceptions import (
    DARException,
    DARHTTPException,
    HTTPSRequired,
)
from sap.aibus.dar.client.util.http_transport import (
    HttpMethodsProtocol,
    TimeoutRetrySession,
    TimeoutPostRetrySession,
)


# TODO: test kwargs as they are API


def create_mock_session() -> HttpMethodsProtocol:
    mock_session = create_autospec(HttpMethodsProtocol, instance=True)
    mock_session.get.return_value = create_mock_response()
    return mock_session


def create_mock_response():
    mock_response = Mock(
        spec_set=["json", "status_code", "headers", "request", "text", "reason"]
    )
    mock_response.headers = CaseInsensitiveDict()
    mock_response.json.return_value = {"ping": "pong"}
    mock_response.status_code = 200
    return mock_response


class TestDARSession:
    dar_url = "https://aiservices-dar.cfapps.xxx.hana.ondemand.com/"
    credentials_source = StaticCredentialsSource("12345")

    expected_headers = {
        "Authorization": "Bearer 12345",
        "User-Agent": "DAR-SDK requests/" + requests.__version__,
        "Accept": "application/json;q=0.9,text/plain",
    }

    def test_constructor_positional_args(self):
        sess = DARSession(self.dar_url, self.credentials_source)

        self._assert_fields_initialized(sess)

    def test_constructor_keyword_args(self):
        sess = DARSession(
            base_url=self.dar_url, credentials_source=self.credentials_source
        )

        self._assert_fields_initialized(sess)

    def test_get_from_endpoint(self):
        for allowed_status_code in range(200, 300):
            # prepare
            sess = self._prepare()

            sess.http.get.return_value.status_code = allowed_status_code

            endpoint = "/data-manager/api/v3/datasetSchemas"

            # act
            sess.get_from_endpoint(endpoint)

            # assert
            self._assert(sess, "get", endpoint)

    def test_delete_from_endpoint(self):
        for allowed_status_code in range(200, 300):
            # prepare
            sess = self._prepare()

            sess.http.delete.return_value.status_code = allowed_status_code

            # act
            endpoint = (
                "/data-manager/api/v3"
                "/datasetSchemas/66e0318b-9637-43ab-84aa-a5eeec87b340"
            )

            sess.delete_from_endpoint(endpoint=endpoint)
            method = "delete"
            self._assert(sess, method, endpoint)

    def test_post_to_endpoint(self):
        for allowed_status_code in range(200, 300):
            sess = self._prepare()
            sess.http.post.return_value.status_code = allowed_status_code

            endpoint = "/data-manager/api/v3/datasetSchemas/"

            payload = {"a": 1, "b": "ok!"}

            response = sess.post_to_endpoint(endpoint=endpoint, payload=payload)

            expected_http_call = call(
                self.dar_url[:-1] + endpoint,
                headers=self.expected_headers,
                json=payload,
            )
            assert getattr(sess.http, "post").call_args_list == [expected_http_call]
            assert response == sess.http.post.return_value

    def test_post_to_endpoint_with_retry(self):
        for allowed_status_code in range(200, 300):
            sess = self._prepare()
            sess.http_post_retry.post.return_value.status_code = allowed_status_code

            endpoint = "/data-manager/api/v3/datasetSchemas/"

            payload = {"a": 1, "b": "ok!"}

            response = sess.post_to_endpoint(
                endpoint=endpoint, payload=payload, retry=True
            )
            expected_http_call = call(
                self.dar_url[:-1] + endpoint,
                headers=self.expected_headers,
                json=payload,
            )
            assert getattr(sess.http_post_retry, "post").call_args_list == [
                expected_http_call
            ]
            assert response == sess.http_post_retry.post.return_value

    def test_post_data_to_endpoint(self):
        for allowed_status_code in range(200, 300):
            sess = self._prepare()

            sess.http.post.return_value.status_code = allowed_status_code

            endpoint = (
                "/data-manager/api/v3/dataset/03c436aa-4467-42d9-8d63-e82cdb342ab4/data"
            )

            payload = BytesIO(b"CSV;data;")

            response = sess.post_data_to_endpoint(endpoint, payload)

            expected_http_call = call(
                self.dar_url[:-1] + endpoint,
                headers=self.expected_headers,
                data=payload,
            )

            assert getattr(sess.http, "post").call_args_list == [expected_http_call]
            assert response == sess.http.post.return_value

    def test_get_error_handling(self):
        sess = self._prepare()
        sess.http.get().status_code = 404

        endpoint = "/data-manager/api/v3/datasetSchemas/"

        with pytest.raises(DARException) as exc_info:
            sess.get_from_endpoint(endpoint)

        exc = exc_info.value
        assert isinstance(exc, DARHTTPException)
        assert exc.status_code == 404
        assert exc.url == self.dar_url[:-1] + endpoint
        assert exc.response == sess.http.get()

    def test_delete_error_handling(self):
        sess = self._prepare()
        sess.http.delete().status_code = 403
        endpoint = "/data-manager/api/v3/datasetSchemas/abcd"

        with pytest.raises(DARException) as exc_info:
            sess.delete_from_endpoint(endpoint)

        exc = exc_info.value
        assert isinstance(exc, DARHTTPException)
        assert exc.status_code == 403
        assert exc.url == self.dar_url[:-1] + endpoint
        assert exc.response == sess.http.delete()

    def test_post_error_handling(self):
        sess = self._prepare()
        sess.http.post().status_code = 503
        endpoint = "/data-manager/api/v3/datasetSchemas/"

        with pytest.raises(DARException) as exc_info:
            sess.post_to_endpoint(endpoint, payload={})

        exc = exc_info.value
        assert isinstance(exc, DARHTTPException)
        assert exc.status_code == 503
        assert exc.url == self.dar_url[:-1] + endpoint
        assert exc.response == sess.http.post()

    def test_post_data_to_endpoint_error_handling(self):
        sess = self._prepare()
        sess.http.post().status_code = 429
        endpoint = (
            "/data-manager/api/v3/dataset/03c436aa-4467-42d9-8d63-e82cdb342ab4/data"
        )

        with pytest.raises(DARException) as exc_info:
            sess.post_data_to_endpoint(endpoint, data_stream=BytesIO(b"test"))

        exc = exc_info.value
        assert isinstance(exc, DARHTTPException)
        assert exc.status_code == 429
        assert exc.url == self.dar_url[:-1] + endpoint
        assert exc.response == sess.http.post()

    def _assert(self, sess, method, endpoint):
        # Validate test-internal assumption
        assert self.dar_url[-1] == "/"
        expected_http_call = call(
            self.dar_url[:-1] + endpoint, headers=self.expected_headers
        )
        assert getattr(sess.http, method).call_args_list == [expected_http_call]

    def _prepare(self):
        sess = DARSession(
            base_url=self.dar_url, credentials_source=self.credentials_source
        )
        sess.http = create_mock_session()
        sess.http_post_retry = create_mock_session()
        return sess

    def _assert_fields_initialized(self, sess):
        assert isinstance(sess.http, TimeoutRetrySession)
        assert isinstance(sess.http_post_retry, TimeoutPostRetrySession)
        # Slash is stripped.
        # TODO: Also test case where slash is not provided in the first place
        assert sess.base_url == self.dar_url[:-1]
        assert sess.credentials_source.token() == "12345"


class TestHTTPSEnforced:
    def test_plain_http_is_not_allowed(self):
        dar_url = "http://aiservices-dar.cfapps.xxx.hana.ondemand.com/"
        credentials_source = StaticCredentialsSource("12345")

        with pytest.raises(HTTPSRequired) as context:
            DARSession(dar_url, credentials_source)
        expected_message = (
            "URL must use https scheme. Unencrypted connections" " are not supported."
        )
        assert str(context.value) == expected_message
