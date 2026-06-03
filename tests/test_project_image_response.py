import base64

from backend.app.main import project_image_response_to_bytes


def test_project_image_response_to_bytes_decodes_b64_json():
    raw = b"fake-png-bytes"
    response = {
        "b64_json": base64.b64encode(raw).decode("ascii"),
        "model": "gpt-image-2",
        "api_type": "openai_images_edits",
        "params": {"quality": "high"},
    }

    image_bytes, params = project_image_response_to_bytes(response)

    assert image_bytes == raw
    assert params == {
        "model": "gpt-image-2",
        "api_type": "openai_images_edits",
        "params": {"quality": "high"},
    }
