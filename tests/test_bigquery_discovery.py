"""Unit tests for BigQuery-based package discovery.

The google-cloud-bigquery library is an optional extra and may not be
installed, so these tests inject a fake ``bigquery`` module (the same surface
the real one exposes: Client, ScalarQueryParameter, QueryJobConfig) via
monkeypatch. No network or real credentials are used.
"""

from types import SimpleNamespace

import pytest

from pyf.aggregator import bigquery_discovery


class FakeQueryJob:
    def __init__(self, rows):
        self._rows = rows

    def result(self):
        return self._rows


class FakeClient:
    """Records the query/job_config it was called with and returns fixed rows."""

    def __init__(self, rows=None, project=None):
        self.project = project
        self.captured = None
        self._rows = (
            rows
            if rows is not None
            else [
                {"name": "collective.foo"},
                {"name": "plone.api"},
            ]
        )

    def query(self, query, job_config=None):
        self.captured = SimpleNamespace(query=query, job_config=job_config)
        return FakeQueryJob(self._rows)


def make_fake_bigquery(client=None):
    """A stand-in for ``google.cloud.bigquery`` with the bits we use."""
    return SimpleNamespace(
        Client=lambda project=None: client or FakeClient(project=project),
        ScalarQueryParameter=lambda name, type_, value: SimpleNamespace(
            name=name, type_=type_, value=value
        ),
        QueryJobConfig=lambda query_parameters=None: SimpleNamespace(
            query_parameters=query_parameters or []
        ),
    )


@pytest.fixture
def fake_bq(monkeypatch):
    fake = make_fake_bigquery()
    monkeypatch.setattr(bigquery_discovery, "bigquery", fake)
    return fake


class TestDiscoverPackageNames:
    def test_returns_names_from_rows(self, fake_bq):
        client = FakeClient()
        names = bigquery_discovery.discover_package_names(
            "Framework :: Plone", client=client
        )
        assert names == ["collective.foo", "plone.api"]

    def test_query_uses_starts_with_and_table(self, fake_bq):
        client = FakeClient()
        bigquery_discovery.discover_package_names(
            "Framework :: Plone", client=client, table="proj.ds.tbl"
        )
        query = client.captured.query
        assert "STARTS_WITH(c, @cls0)" in query
        assert "`proj.ds.tbl`" in query
        assert "UNNEST(classifiers)" in query
        # One classifier -> one scalar parameter bound to its value.
        params = client.captured.job_config.query_parameters
        assert len(params) == 1
        assert params[0].value == "Framework :: Plone"

    def test_string_classifier_is_coerced_to_list(self, fake_bq):
        client = FakeClient()
        bigquery_discovery.discover_package_names("Framework :: Zope", client=client)
        params = client.captured.job_config.query_parameters
        assert [p.value for p in params] == ["Framework :: Zope"]

    def test_multiple_classifiers_build_or_conditions(self, fake_bq):
        client = FakeClient()
        bigquery_discovery.discover_package_names(
            ["Framework :: Plone", "Framework :: Zope"], client=client
        )
        query = client.captured.query
        assert "STARTS_WITH(c, @cls0) OR STARTS_WITH(c, @cls1)" in query
        params = client.captured.job_config.query_parameters
        assert [p.value for p in params] == [
            "Framework :: Plone",
            "Framework :: Zope",
        ]

    def test_empty_values_are_dropped(self, fake_bq):
        client = FakeClient()
        bigquery_discovery.discover_package_names(
            [None, "", "Framework :: Plone"], client=client
        )
        params = client.captured.job_config.query_parameters
        assert [p.value for p in params] == ["Framework :: Plone"]

    def test_empty_classifiers_raises(self, fake_bq):
        with pytest.raises(ValueError, match="at least one classifier"):
            bigquery_discovery.discover_package_names([], client=FakeClient())

    def test_missing_library_raises_helpful_error(self, monkeypatch):
        """With the extra not installed and no client injected, raise a hint."""
        monkeypatch.setattr(bigquery_discovery, "bigquery", None)
        with pytest.raises(RuntimeError, match=r"bigquery.*extra"):
            bigquery_discovery.discover_package_names("Framework :: Plone")

    def test_builds_client_when_none_given(self, fake_bq):
        """When no client is injected, one is built from the (fake) library."""
        names = bigquery_discovery.discover_package_names("Framework :: Plone")
        assert names == ["collective.foo", "plone.api"]
