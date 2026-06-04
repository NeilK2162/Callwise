import pytest

from callwise.domain.phone import InvalidPhoneNumber, mask_e164, normalize_e164


@pytest.mark.parametrize(
    "raw",
    ["09876543210", "+91 98765 43210", "+919876543210", "98765-43210"],
)
def test_normalize_many_shapes_to_e164(raw):
    assert normalize_e164(raw, "IN") == "+919876543210"


def test_normalize_rejects_garbage():
    with pytest.raises(InvalidPhoneNumber):
        normalize_e164("12", "IN")


def test_normalize_rejects_empty():
    with pytest.raises(InvalidPhoneNumber):
        normalize_e164("   ", "IN")


def test_mask_hides_middle():
    masked = mask_e164("+919876543210")
    assert masked.startswith("+91") and masked.endswith("3210") and "·" in masked


def test_mask_short_number_is_fully_obscured():
    assert mask_e164("+12") == "···"


def test_normalize_rejects_none():
    with pytest.raises(InvalidPhoneNumber):
        normalize_e164(None)  # type: ignore[arg-type]
