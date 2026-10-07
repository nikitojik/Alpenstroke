import urllib.error

from scripts import egress_check


def fake_urlopen(behaviour):
    def urlopen(url, timeout):
        result = behaviour[url]
        if isinstance(result, Exception):
            raise result
        return result
    return urlopen


def setup(monkeypatch, model, outside):
    behaviour = {egress_check.MODEL_URL: model}
    behaviour.update({url: outside for url in egress_check.OUTSIDE_URLS})
    monkeypatch.setattr(egress_check.urllib.request, "urlopen", fake_urlopen(behaviour))


def test_sealed_network_passes(monkeypatch):
    setup(monkeypatch, model="ok", outside=OSError("no route"))
    assert egress_check.main() == 0


def test_http_error_outside_means_internet_is_reachable(monkeypatch):
    setup(monkeypatch, model="ok", outside=urllib.error.HTTPError("u", 404, "nf", {}, None))
    assert egress_check.main() == 1


def test_missing_model_fails(monkeypatch):
    setup(monkeypatch, model=OSError("no route"), outside=OSError("no route"))
    assert egress_check.main() == 1