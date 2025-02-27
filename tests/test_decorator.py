import time
from typing import Any, Generator

import pendulum
import pytest
from starlette.testclient import TestClient

from examples.in_memory.main import app
from fastapi_cache import FastAPICache
from fastapi_cache.backends.inmemory import InMemoryBackend


@pytest.fixture(autouse=True)
def _init_cache() -> Generator[Any, Any, None]:  # pyright: ignore[reportUnusedFunction]
    FastAPICache.init(InMemoryBackend())
    yield
    FastAPICache.reset()


def test_datetime() -> None:
    with TestClient(app) as client:
        response = client.get("/datetime")
        assert response.headers.get("X-FastAPI-Cache") == "MISS"
        now = response.json().get("now")
        now_ = pendulum.now()
        assert pendulum.parse(now).to_atom_string() == now_.to_atom_string() # type: ignore[union-attr]
        response = client.get("/datetime")
        assert response.headers.get("X-FastAPI-Cache") == "HIT"
        now = response.json().get("now")
        assert pendulum.parse(now).to_atom_string() == now_.to_atom_string() # type: ignore[union-attr]
        time.sleep(3)
        response = client.get("/datetime")
        now = response.json().get("now")
        assert response.headers.get("X-FastAPI-Cache") == "MISS"
        now = pendulum.parse(now)
        assert now != now_
        assert now.to_atom_string() == pendulum.now().to_atom_string() # type: ignore[union-attr,unused-ignore]


def test_date() -> None:
    """Test path function without request or response arguments."""
    with TestClient(app) as client:
        response = client.get("/date")
        assert response.headers.get("X-FastAPI-Cache") == "MISS"
        assert pendulum.parse(response.json()) == pendulum.today()

        # do it again to test cache
        response = client.get("/date")
        assert response.headers.get("X-FastAPI-Cache") == "HIT"
        assert pendulum.parse(response.json()) == pendulum.today()

        # now test with cache disabled, as that's a separate code path
        FastAPICache._enable = False  # pyright: ignore[reportPrivateUsage]
        response = client.get("/date")
        assert "X-FastAPI-Cache" not in response.headers
        assert pendulum.parse(response.json()) == pendulum.today()
        FastAPICache._enable = True # pyright: ignore[reportPrivateUsage]


def test_sync() -> None:
    """Ensure that sync function support works."""
    with TestClient(app) as client:
        response = client.get("/sync-me")
        assert response.json() == 42


def test_cache_response_obj() -> None:
    with TestClient(app) as client:
        cache_response = client.get("cache_response_obj")
        assert cache_response.json() == {"a": 1}
        get_cache_response = client.get("cache_response_obj")
        assert get_cache_response.json() == {"a": 1}
        assert get_cache_response.headers.get("cache-control")
        assert get_cache_response.headers.get("etag")


def test_kwargs() -> None:
    with TestClient(app) as client:
        name = "Jon"
        response = client.get("/kwargs", params={"name": name})
        assert "X-FastAPI-Cache" not in response.headers
        assert response.json() == {"name": name}


def test_method() -> None:
    with TestClient(app) as client:
        response = client.get("/method")
        assert response.json() == 17


def test_pydantic_model() -> None:
    with TestClient(app) as client:
        r1 = client.get("/pydantic_instance")
        assert r1.headers.get("X-FastAPI-Cache") == "MISS"
        r2 = client.get("/pydantic_instance")
        assert r2.headers.get("X-FastAPI-Cache") == "HIT"
        assert r1.json() == r2.json()


def test_non_get() -> None:
    with TestClient(app) as client:
        response = client.put("/cached_put")
        assert "X-FastAPI-Cache" not in response.headers
        assert response.json() == {'detail': 'Method Not Allowed'}
        response = client.put("/cached_put")
        assert "X-FastAPI-Cache" not in response.headers
        assert response.json() == {'detail': 'Method Not Allowed'}


def test_alternate_injected_namespace() -> None:
    with TestClient(app) as client:
        response = client.get("/namespaced_injection")
        assert response.headers.get("X-FastAPI-Cache") == "MISS"
        assert response.json() == {"__fastapi_cache_request": 42, "__fastapi_cache_response": 17}

def test_cache_control() -> None:
    with TestClient(app) as client:
        response = client.get("/cached_put")
        assert response.json() == {"value": 1}

        # HIT
        response = client.get("/cached_put")
        assert response.json() == {"value": 1}

        # no-cache
        response = client.get("/cached_put", headers={"Cache-Control": "no-cache"})
        assert response.json() == {"value": 2}

        response = client.get("/cached_put")
        assert response.json() == {"value": 2}

        # no-store
        response = client.get("/cached_put", headers={"Cache-Control": "no-store"})
        assert response.json() == {"value": 2}

        response = client.get("/cached_put")
        assert response.json() == {"value": 2}

def test_cache_control_header() -> None:
    """Test no-cache, no-store cache control header"""
    with TestClient(app) as client:
        # forcing clear to start a clean cache
        client.get("/clear")

        # no-store, no-cache will always no use or store cache
        response = client.get("/date", headers={"Cache-Control": "no-store,no-cache"})
        assert response.headers.get("X-FastAPI-Cache") == "MISS"
        assert response.headers.get("Cache-Control") == "no-cache,no-store"
        assert response.headers.get("ETag") is None
        assert pendulum.parse(response.json()) == pendulum.today()

        # do it again to test cache without header
        response = client.get("/date")
        assert response.headers.get("X-FastAPI-Cache") == "MISS"
        assert pendulum.parse(response.json()) == pendulum.today()

        # do it again to test cache with no-store. Will not store this response but use the cache
        response = client.get("/date", headers={"Cache-Control": "no-store"})
        assert response.headers.get("X-FastAPI-Cache") == "HIT"
        assert response.headers.get("Cache-Control") == "max-age=10,no-store"
        assert pendulum.parse(response.json()) == pendulum.today()

        # do it again to test cache with no-cache. Will not store use cache but store it
        response = client.get("/date", headers={"Cache-Control": "no-cache"})
        assert response.headers.get("X-FastAPI-Cache") == "MISS"
        assert response.headers.get("Cache-Control") == "max-age=10,no-cache"
        assert pendulum.parse(response.json()) == pendulum.today()

        time.sleep(3)

        # call with no headers now to use the value store in previous step
        response = client.get("/date")
        assert response.headers.get("X-FastAPI-Cache") == "HIT"
        assert response.headers.get("Cache-Control") == "max-age=7"
        assert pendulum.parse(response.json()) == pendulum.today()
