import os
import re
from datetime import UTC, datetime
from unittest import mock

import pytest
import requests
import requests_mock
from requests import Session

import test.data as fixtures
from octo_track.models import ElectricityConsumption
from octo_track.octopus import Octopus


class TestOctopus:
    @pytest.fixture
    def mock_adapter(self):
        return requests_mock.Adapter()

    @pytest.fixture
    def instance(self, mock_adapter):
        with mock.patch.dict(os.environ, {"OCTOPUS_API_KEY": "mock_api_key"}):
            o = Octopus(mpan="mock_e_mpan", sn="mock_e_sn")
            o.mount("https://", mock_adapter)
            return o

    # ── init / session ────────────────────────────────────────────────────────

    def test_init_reads_api_key_from_env(self, instance):
        assert instance.api_key == "mock_api_key"
        assert instance.electricity_mpan == "mock_e_mpan"
        assert instance.electricity_sn == "mock_e_sn"

    def test_init_accepts_explicit_mpan_sn(self, mock_adapter):
        with mock.patch.dict(os.environ, {"OCTOPUS_API_KEY": "mock_api_key"}):
            o = Octopus(mpan="explicit_mpan", sn="explicit_sn")
        assert o.electricity_mpan == "explicit_mpan"
        assert o.electricity_sn == "explicit_sn"

    def test_session_auth_uses_api_key_as_username(self, instance):
        assert isinstance(instance, Session)
        assert instance.auth.username == "mock_api_key"
        assert instance.auth.password == ""

    def test_repr(self, instance):
        assert "mock_e_mpan" in repr(instance)
        assert "mock_e_sn" in repr(instance)

    # ── _request_timestamp hook ───────────────────────────────────────────────

    def test_request_timestamp_parsed_from_date_header(self, instance):
        now = datetime.now(UTC)
        headers = requests.structures.CaseInsensitiveDict()
        headers["date"] = now.strftime("%a, %d %b %Y %H:%M:%S %Z")

        adapter = requests_mock.Adapter()
        adapter.register_uri("GET", "mock://test.local", headers=headers)
        instance.mount("mock://", adapter)

        resp = instance.get("mock://test.local")
        assert resp.request_timestamp == now.replace(microsecond=0)

    def test_request_timestamp_falls_back_on_missing_header(self, instance):
        adapter = requests_mock.Adapter()
        adapter.register_uri("GET", "mock://test.local")
        instance.mount("mock://", adapter)

        resp = instance.get("mock://test.local")
        assert hasattr(resp, "request_timestamp")
        assert isinstance(resp.request_timestamp, datetime)

    # ── _request ─────────────────────────────────────────────────────────────

    def test_request_builds_correct_url(self, instance):
        with mock.patch("requests.Session.request") as mock_req:
            mock_req.return_value = mock.Mock(raise_for_status=mock.Mock())
            instance._request("GET", "some-endpoint")
            url = mock_req.call_args[0][1]
            assert url == "https://api.octopus.energy/v1/some-endpoint"

    def test_request_raises_http_error(self, instance, mock_adapter):
        mock_adapter.register_uri("GET", re.compile(r".*"), status_code=401)
        with mock.patch.object(instance, "hooks", {}):
            with pytest.raises(requests.exceptions.HTTPError):
                instance._request("GET", "any-endpoint")

    def test_request_requires_endpoint(self, instance):
        with pytest.raises(TypeError):
            instance._request("GET")

    # ── account ───────────────────────────────────────────────────────────────

    def test_account_returns_parsed_json(self, instance, mock_adapter):
        expected = fixtures.load("account.json")
        mock_adapter.register_uri(
            "GET",
            re.compile(r"/v1/accounts/A-00000000/?$"),
            json=expected,
        )
        with mock.patch.object(instance, "hooks", {}):
            result = instance.account("A-00000000")
        assert result == expected
        assert result["number"] == "A-00000000"
        assert len(result["properties"]) == 1

    # ── consumption ──────────────────────────────────────────────────────────

    def test_consumption_defaults_period_from_to_epoch(self, instance):
        page = fixtures.load("consumption_page_1.json")
        page_no_next = {**page, "next": None}
        with mock.patch.object(Session, "request") as mock_req:
            mock_resp = mock.Mock()
            mock_resp.json.return_value = page_no_next
            mock_req.return_value = mock_resp
            instance.consumption()
            params = mock_req.call_args[1].get("params", {})
            assert params["period_from"] == "1970-01-01T00:00:00Z"

    def test_consumption_paginates_across_two_pages(self, instance, mock_adapter):
        page1 = fixtures.load("consumption_page_1.json")
        page2 = fixtures.load("consumption_page_2.json")
        mock_adapter.register_uri(
            "GET",
            re.compile(r"/.*\/consumption/?(\?.*)?$"),
            [{"json": page1}, {"json": page2}],
        )
        with mock.patch.object(instance, "hooks", {}):
            results = instance.consumption()

        assert mock_adapter.call_count == 2
        assert "page=" not in mock_adapter.request_history[0].query
        assert "page=2" in mock_adapter.request_history[1].query

        all_results = page1["results"] + page2["results"]
        expected = [ElectricityConsumption.from_dict({"mpan": instance.electricity_mpan, "meter_sn": instance.electricity_sn, **r}) for r in all_results]
        assert results == expected

    def test_consumption_with_explicit_url(self, instance, mock_adapter):
        page2 = fixtures.load("consumption_page_2.json")
        mock_adapter.register_uri(
            "GET",
            re.compile(r"/.*\/consumption/?(\?.*)?$"),
            json=page2,
        )
        url = "https://api.octopus.energy/v1/electricity-meter-points/mock_e_mpan/meters/mock_e_sn/consumption/?page=2"
        with (
            mock.patch.object(instance, "hooks", {}),
            mock.patch.object(Session, "request", wraps=instance.request) as spy,
        ):
            results = instance.consumption(url=url)

        spy.assert_called_once()
        assert len(results) == len(page2["results"])

    def test_consumption_calls_on_page_callback(self, instance, mock_adapter):
        page1 = fixtures.load("consumption_page_1.json")
        page2 = fixtures.load("consumption_page_2.json")
        mock_adapter.register_uri(
            "GET",
            re.compile(r"/.*\/consumption/?(\?.*)?$"),
            [{"json": page1}, {"json": page2}],
        )
        pages_received = []
        with mock.patch.object(instance, "hooks", {}):
            instance.consumption(on_page=pages_received.append)

        assert len(pages_received) == 2
        assert len(pages_received[0]) == len(page1["results"])
        assert len(pages_received[1]) == len(page2["results"])

    def test_consumption_returns_electricity_consumption_instances(self, instance, mock_adapter):
        page = fixtures.load("consumption_page_1.json")
        mock_adapter.register_uri(
            "GET",
            re.compile(r"/.*\/consumption/?(\?.*)?$"),
            json={**page, "next": None},
        )
        with mock.patch.object(instance, "hooks", {}):
            results = instance.consumption()

        assert all(isinstance(r, ElectricityConsumption) for r in results)
        assert all(r.mpan == "mock_e_mpan" for r in results)
        assert all(r.meter_sn == "mock_e_sn" for r in results)

    # ── standard_unit_rates ───────────────────────────────────────────────────

    def test_standard_unit_rates_paginates(self, instance, mock_adapter):
        page1 = fixtures.load("unit_rates_page_1.json")
        page2 = fixtures.load("unit_rates_page_2.json")
        mock_adapter.register_uri(
            "GET",
            re.compile(r"/v1/products/.*/standard-unit-rates/?(\?.*)?$"),
            [{"json": page1}, {"json": page2}],
        )
        with mock.patch.object(instance, "hooks", {}):
            rates = instance.standard_unit_rates(
                product_code="AGILE-24-10-01",
                tariff_code="E-1R-AGILE-24-10-01-A",
            )

        all_results = page1["results"] + page2["results"]
        assert len(rates) == len(all_results)
        assert rates[0]["value_inc_vat"] == page1["results"][0]["value_inc_vat"]
        assert rates[-1]["value_inc_vat"] == page2["results"][-1]["value_inc_vat"]

    def test_standard_unit_rates_passes_period_params(self, instance, mock_adapter):
        page = fixtures.load("unit_rates_page_1.json")
        mock_adapter.register_uri(
            "GET",
            re.compile(r"/v1/products/.*/standard-unit-rates/?(\?.*)?$"),
            json={**page, "next": None},
        )
        with mock.patch.object(instance, "hooks", {}):
            instance.standard_unit_rates(
                product_code="AGILE-24-10-01",
                tariff_code="E-1R-AGILE-24-10-01-A",
                period_from="2024-01-01T00:00:00Z",
                period_to="2024-02-01T00:00:00Z",
            )

        url = mock_adapter.request_history[0].url
        assert "period_from=2024-01-01T00%3A00%3A00Z" in url
        assert "period_to=2024-02-01T00%3A00%3A00Z" in url

    # ── standing_charges ─────────────────────────────────────────────────────

    def test_standing_charges_paginates(self, instance, mock_adapter):
        page1 = fixtures.load("standing_charges_page_1.json")
        page2 = fixtures.load("standing_charges_page_2.json")
        mock_adapter.register_uri(
            "GET",
            re.compile(r"/v1/products/.*/standing-charges/?(\?.*)?$"),
            [{"json": page1}, {"json": page2}],
        )
        with mock.patch.object(instance, "hooks", {}):
            charges = instance.standing_charges(
                product_code="AGILE-24-10-01",
                tariff_code="E-1R-AGILE-24-10-01-A",
            )

        all_results = page1["results"] + page2["results"]
        assert len(charges) == len(all_results)
        assert charges[0]["value_inc_vat"] == page1["results"][0]["value_inc_vat"]
        assert charges[-1]["value_inc_vat"] == page2["results"][-1]["value_inc_vat"]

    # ── GraphQL methods ───────────────────────────────────────────────────────

    def test_kraken_token_posts_to_gql_url(self, instance):
        token_fixture = fixtures.load("graphql_token.json")
        with mock.patch("octo_track.octopus.requests.post") as mock_post:
            mock_post.return_value = mock.Mock(
                json=mock.Mock(return_value=token_fixture),
                raise_for_status=mock.Mock(),
            )
            token = instance._kraken_token()

        mock_post.assert_called_once_with(Octopus.GQL_URL, json=mock.ANY)
        assert token == token_fixture["data"]["obtainKrakenToken"]["token"]

    def test_kraken_token_embeds_api_key_in_mutation(self, instance):
        token_fixture = fixtures.load("graphql_token.json")
        with mock.patch("octo_track.octopus.requests.post") as mock_post:
            mock_post.return_value = mock.Mock(
                json=mock.Mock(return_value=token_fixture),
                raise_for_status=mock.Mock(),
            )
            instance._kraken_token()

        query_sent = mock_post.call_args[1]["json"]["query"]
        assert "mock_api_key" in query_sent
        assert "obtainKrakenToken" in query_sent

    def test_account_number_from_api_key_returns_number(self, instance):
        token_fixture = fixtures.load("graphql_token.json")
        accounts_fixture = fixtures.load("graphql_accounts.json")
        mock_token = mock.Mock(json=mock.Mock(return_value=token_fixture), raise_for_status=mock.Mock())
        mock_accounts = mock.Mock(json=mock.Mock(return_value=accounts_fixture), raise_for_status=mock.Mock())

        with mock.patch("octo_track.octopus.requests.post", side_effect=[mock_token, mock_accounts]) as mock_post:
            number = instance.account_number_from_api_key()

        assert number == accounts_fixture["data"]["viewer"]["accounts"][0]["number"]
        assert mock_post.call_count == 2

    def test_account_number_from_api_key_passes_token_as_auth_header(self, instance):
        token_fixture = fixtures.load("graphql_token.json")
        accounts_fixture = fixtures.load("graphql_accounts.json")
        kraken_token = token_fixture["data"]["obtainKrakenToken"]["token"]

        mock_token = mock.Mock(json=mock.Mock(return_value=token_fixture), raise_for_status=mock.Mock())
        mock_accounts = mock.Mock(json=mock.Mock(return_value=accounts_fixture), raise_for_status=mock.Mock())

        with mock.patch("octo_track.octopus.requests.post", side_effect=[mock_token, mock_accounts]) as mock_post:
            instance.account_number_from_api_key()

        second_call_kwargs = mock_post.call_args_list[1][1]
        assert second_call_kwargs["headers"]["Authorization"] == kraken_token
