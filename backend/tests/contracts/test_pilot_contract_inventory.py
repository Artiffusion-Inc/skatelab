"""Focused backend wire contracts for the pilot auth/session/process slice."""

from app.schemas import ProcessRequest, ResetPasswordRequest


def test_reset_password_wire_name_is_password() -> None:
    request = ResetPasswordRequest(token="t", password="password123")

    assert request.model_dump() == {
        "token": "t",
        "password": "password123",
    }


def test_process_person_click_is_optional_for_auto_detection() -> None:
    request = ProcessRequest(video_key="uploads/video.mp4")

    assert request.person_click is None


def test_process_person_click_keeps_integer_pixel_contract() -> None:
    request = ProcessRequest(
        video_key="uploads/video.mp4",
        person_click={"x": 10, "y": 20},
    )

    assert request.person_click is not None
    assert request.person_click.model_dump() == {"x": 10, "y": 20}
