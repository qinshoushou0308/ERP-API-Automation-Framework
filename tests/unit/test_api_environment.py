from base.apiutil import RequestBase


class StubConfig:
    hosts = {
        "api_envi": "http://127.0.0.1:8787",
        "erp_envi": "http://127.0.0.1:9999/jshERP-boot",
    }

    def get_section_for_data(self, section, option):
        assert option == "host"
        return self.hosts[section]


def test_get_url_host_uses_mock_environment_by_default():
    request = RequestBase()
    request.conf = StubConfig()

    assert request.get_url_host({}) == "http://127.0.0.1:8787"


def test_get_url_host_uses_environment_from_yaml():
    request = RequestBase()
    request.conf = StubConfig()

    assert request.get_url_host({"environment": "erp_envi"}) == (
        "http://127.0.0.1:9999/jshERP-boot"
    )
