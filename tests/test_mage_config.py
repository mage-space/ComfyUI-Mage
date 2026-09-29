import pytest

from mage_config import build_config, load_api_key, option_inputs, parse_extra_config


def test_api_key_prefers_the_environment(tmp_path):
    config = tmp_path / "config.ini"
    config.write_text("[mage]\napi_key = mage_sk_file\n")

    assert load_api_key({"MAGE_API_KEY": " mage_sk_env "}, config) == "mage_sk_env"
    assert load_api_key({}, config) == "mage_sk_file"


def test_api_key_is_none_without_a_source(tmp_path):
    empty = tmp_path / "config.ini"
    empty.write_text("[mage]\napi_key =\n")

    assert load_api_key({}, tmp_path / "missing.ini") is None
    assert load_api_key({"MAGE_API_KEY": "  "}, empty) is None


def test_option_inputs_follow_the_reference_in_the_given_order():
    inputs = option_inputs("mango", ["resolution", "aspect_ratio", "no_such_field"])

    assert list(inputs) == ["resolution", "aspect_ratio"]
    tokens, meta = inputs["aspect_ratio"]
    assert meta["default"] in tokens
    assert "16:9" in tokens


def test_references_fill_image_then_additional_images():
    config = build_config("mango", prompt="p", seed=3, options={"resolution": "2K"}, references=["u1", "u2", "u3"])

    assert config == {
        "prompt": "p",
        "seed": 3,
        "resolution": "2K",
        "image": "u1",
        "additional_images": ["u2", "u3"],
    }


def test_frames_and_video_go_in_the_documented_fields():
    config = build_config("lemon", prompt="p", seed=0, first_frame="f", last_frame="l")
    assert (config["first_image"], config["last_image"]) == ("f", "l")

    assert build_config("cherry", prompt="p", seed=0, video="v")["videos"] == ["v"]


def test_roles_an_architecture_lacks_are_refused():
    with pytest.raises(ValueError, match="video"):
        build_config("mango", prompt="p", seed=0, video="v")
    with pytest.raises(ValueError, match="first frame"):
        build_config("mango", prompt="p", seed=0, first_frame="f")


def test_extra_config_overrides_widgets():
    config = build_config("mango", prompt="p", seed=0, options={"resolution": "2K"}, extra={"resolution": "4K", "novel": 1})

    assert config["resolution"] == "4K"
    assert config["novel"] == 1


@pytest.mark.parametrize("text", ["", "  ", "{}"])
def test_empty_extra_config(text):
    assert parse_extra_config(text) == {}


@pytest.mark.parametrize("text", ["{not json", "[1, 2]"])
def test_bad_extra_config_is_refused(text):
    with pytest.raises(ValueError, match="extra_config"):
        parse_extra_config(text)
