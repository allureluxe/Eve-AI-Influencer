import json

import pytest

from luna.media import ASPECTS, MediaErreur, spec_depuis_demande


def test_photo_defaut_3_4():
    spec = spec_depuis_demande(json.dumps({
        "type": "photo",
        "prompt": "A candid phone photo in Metz",
    }))
    assert spec is not None
    assert spec.aspect_ratio == "3:4"
    assert spec.duration_seconds == 10
    assert ASPECTS[spec.aspect_ratio] == "portrait_3_4"
    assert spec.publish is False


def test_video_defaut_9_16():
    spec = spec_depuis_demande(json.dumps({
        "type": "video",
        "prompt": "She walks and turns toward camera",
        "publish": True,
    }))
    assert spec is not None
    assert spec.aspect_ratio == "9:16"
    assert spec.publish is True


def test_ancienne_demande_reste_legacy():
    assert spec_depuis_demande("un post Instagram classique") is None


def test_ratio_invalide():
    with pytest.raises(MediaErreur):
        spec_depuis_demande(json.dumps({
            "type": "photo",
            "prompt": "test",
            "aspect_ratio": "7:11",
        }))


def test_prompt_obligatoire():
    with pytest.raises(MediaErreur):
        spec_depuis_demande(json.dumps({"type": "photo"}))


def test_quality_invalide():
    with pytest.raises(MediaErreur):
        spec_depuis_demande(json.dumps({
            "type": "photo",
            "prompt": "test",
            "quality": "ultra",
        }))


def test_ratios_runway_gen45():
    from luna.media import RunwayVideo
    assert RunwayVideo._ratio_api("9:16") == "720:1280"
    assert RunwayVideo._ratio_api("16:9") == "1280:720"
    assert RunwayVideo._ratio_api("3:4") == "832:1104"
    assert RunwayVideo._ratio_api("4:3") == "1104:832"
    assert RunwayVideo._ratio_api("1:1") == "960:960"
