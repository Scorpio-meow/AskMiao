from app.core import config as config_module


def test_export_hf_environment_writes_only_configured_values(monkeypatch):
    fake_environ = {}
    monkeypatch.setattr(config_module.os, "environ", fake_environ)
    configured = config_module.settings.model_copy(update={
        "HF_HOME": "./data/hf_home",
        "HF_HUB_CACHE": None,
        "SENTENCE_TRANSFORMERS_HOME": None,
        "HF_HUB_OFFLINE": True,
        "HF_HUB_DISABLE_SYMLINKS_WARNING": False,
    })

    config_module.export_hf_environment(configured)

    assert fake_environ == {
        "HF_HOME": "./data/hf_home",
        "HF_HUB_OFFLINE": "1",
        "HF_HUB_DISABLE_SYMLINKS_WARNING": "0",
    }
