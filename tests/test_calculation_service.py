import pytest
import numpy as np

from layer_thickness_app.services.calculation_service import CalculationService

# --- Mock Objects ---


class MockRefractiveIndexMaterial:
    """
    A mock class to replace ri.RefractiveIndexMaterial.
    This allows for control over the 'k' value it returns.
    """
    def __init__(self, shelf: str, book: str, page: str):
        self._k_value = 0.1  # Default test value
        self.raise_exception = False
        self.path = f"{shelf}/{book}/{page}"

    def get_extinction_coefficient(self, wavelength_um: float) -> float:
        """Returns a predictable k or raises an error if configured to."""
        if self.raise_exception:
            raise Exception("Mock Material Error")

        return self._k_value

    def set_k_value(self, k: float):
        """Helper to set the k value for a test."""
        self._k_value = k

    def set_raise_exception(self, raise_ex: bool):
        """Helper to make the mock raise an error."""
        self.raise_exception = raise_ex


# --- Pytest Fixtures ---


@pytest.fixture
def service() -> CalculationService:
    """
    Returns a new instance of CalculationService for each test.
    """
    return CalculationService()


@pytest.fixture
def test_images() -> dict[str, np.ndarray]:
    """
    Provides a pair of predictable BGR images.
    - Reference image: A bright, solid gray (200)
    - Material image: A darker, solid gray (100)

    cv2.cvtColor will convert a BGR (X, X, X) image to a grayscale
    image with the same value X.
    """
    # Create a 10x10 pixel, 3-channel (BGR) image with all values at 200
    ref_img = np.full((10, 10, 3), 200, dtype=np.uint8)

    # Create a 10x10 BGR image with all values at 100
    mat_img = np.full((10, 10, 3), 100, dtype=np.uint8)

    return {"ref": ref_img, "mat": mat_img}


@pytest.fixture
def mock_material_class(monkeypatch):
    """
    Fixture to replace the real 'ri.RefractiveIndexMaterial' with
    'MockRefractiveIndexMaterial' for the duration of a test.
    """
    # This mock instance will be shared by all calls to the constructor
    mock_material_instance = MockRefractiveIndexMaterial("shelf", "book", "page")

    # Mock the *constructor* to return the *single instance*,
    # allowing for configuration before the test runs.
    monkeypatch.setattr(
        "refractiveindex2.RefractiveIndexMaterial",
        lambda *args, **kwargs: mock_material_instance
    )
    return mock_material_instance


# --- Test Cases ---


def test_init(service: CalculationService):
    """Test that the service initializes correctly."""
    assert service is not None


## Test Helper Methods ##


def test_calculate_mean_pixel_value(service: CalculationService):
    """Test the grayscale conversion and mean calculation."""
    # Create a BGR image where all pixels are (150, 150, 150)
    img = np.full((20, 20, 3), 150, dtype=np.uint8)

    # cvtColor will convert (150, 150, 150) to a grayscale value of 150
    mean_val = service.calculate_mean_pixel_value(img, "test")

    assert mean_val == 150.0


def test_linearize_mean_pixel_value(service: CalculationService):
    """Test the linearization formula with known values."""
    # Test with GW = 200.0
    # lin = (((200 / 255.0) + 0.055) / 1.005) ** 2.4 = 0.6489...
    assert service.linearize_mean_pixel_value(200.0) == pytest.approx(0.64896, abs=1e-4)

    # Test with GW = 100.0
    # lin = (((100 / 255.0) + 0.055) / 1.005) ** 2.4 = 0.1431...
    assert service.linearize_mean_pixel_value(100.0) == pytest.approx(0.14318, abs=1e-4)

    # Test with GW = 255.0 (max)
    # lin = (((255 / 255.0) + 0.055) / 1.005) ** 2.4 = 1.1235...
    assert service.linearize_mean_pixel_value(255.0) == pytest.approx(1.12358, abs=1e-4)

    # Test with GW = 0.0 (min)
    # lin = (((0 / 255.0) + 0.055) / 1.005) ** 2.4 = 0.0009...
    assert service.linearize_mean_pixel_value(0.0) == pytest.approx(0.00093, abs=1e-4)


def test_berechne_alpha(service: CalculationService):
    """Test the absorption coefficient calculation."""
    # k = 0.1, lambda_um = 0.5 µm
    # lambda_cm = 0.5 * 1e-4 = 5e-5 cm
    # alpha = (4 * pi * 0.1) / 5e-5 = 25132.74...
    alpha = service.berechne_alpha(k=0.1, lambda_um=0.5)
    assert alpha == pytest.approx(25132.74, abs=1e-2)

    # Test with k=0
    alpha_zero = service.berechne_alpha(k=0, lambda_um=0.5)
    assert alpha_zero == 0.0

    # Test for invalid wavelength
    with pytest.raises(ValueError, match="Wellenlänge muss größer als 0 sein"):
        service.berechne_alpha(k=0.1, lambda_um=0)

    with pytest.raises(ValueError):
        service.berechne_alpha(k=0.1, lambda_um=-1.0)


def test_berechne_x(service: CalculationService):
    """Test the final thickness calculation."""
    # I = linearized material value = 0.1517
    # I1 = linearized reference value = 0.6515
    # f = alpha = 25132.74
    I_transmitted = 0.1517
    I1_initial = 0.6515
    f_alpha = 25132.74

    # x_cm = math.log(0.1517 / 0.6515) * (1 / -25132.74)
    # x_cm = math.log(0.2328) * (-3.978e-5)
    # x_cm = -1.4576 * (-3.978e-5) = 5.799e-5 cm
    # x_nm = 5.799e-5 * 1e7 = 579.9 nm
    thickness_nm = service.berechne_x(I=I_transmitted, I1=I1_initial, f=f_alpha)
    assert thickness_nm == pytest.approx(579.9, abs=0.1)

    # Test for invalid inputs
    assert service.berechne_x(I=0, I1=0.6, f=25000) is None
    assert service.berechne_x(I=0.1, I1=0, f=25000) is None
    assert service.berechne_x(I=0.1, I1=0.6, f=0) is None


## Test Main Pipeline ##


def test_calculate_thickness_success(
    service: CalculationService,
    test_images: dict,
    mock_material_class: MockRefractiveIndexMaterial
):
    """
    Test the full, 'happy path' pipeline from start to finish.
    This test combines all the individual unit test values.
    """
    # 1. Configure the mock
    mock_material_class.set_k_value(0.1)

    # 2. Define inputs
    ref_img = test_images["ref"]  # Mean will be 200.0
    mat_img = test_images["mat"]  # Mean will be 100.0
    wavelength_um = 0.5

    # 3. Run calculation
    thickness, error_msg = service.calculate_thickness(
        ref_image=ref_img,
        mat_image=mat_img,
        shelf="test_shelf",
        book="test_book",
        page="test_page",
        wavelength_um=wavelength_um
    )

    # 4. Verify results
    # Values from helper tests:
    # GW=200 -> Lin=0.64896
    # GW=100 -> Lin=0.14318
    # k=0.1, wl=0.5 -> alpha=25132.74
    # Resulting calculation:
    # x = log(0.14318 / 0.64896) * (1 / -25132.74) * 1e7 = 601.3
    assert thickness == pytest.approx(601.3, abs=0.1)
    assert error_msg is None


def test_calculate_thickness_material_error(
    service: CalculationService,
    test_images: dict,
    mock_material_class: MockRefractiveIndexMaterial
):
    """
    Test the pipeline when the 'refractiveindex2' library raises an error.
    """
    # 1. Configure the mock to fail
    mock_material_class.set_raise_exception(True)

    # 2. Run calculation
    thickness, error_msg = service.calculate_thickness(
        ref_image=test_images["ref"],
        mat_image=test_images["mat"],
        shelf="fail", book="fail", page="fail",
        wavelength_um=0.5
    )

    # 3. Verify error
    assert thickness is None
    assert error_msg is not None
    assert "Material Error" in error_msg
    assert "fail/fail/fail" in error_msg
    assert "Mock Material Error" in error_msg  # The error raised by the mock


def test_calculate_thickness_alpha_error(
    service: CalculationService,
    test_images: dict,
    mock_material_class: MockRefractiveIndexMaterial
):
    """
    Test the pipeline when berechne_alpha fails (e.g., wavelength = 0).
    """
    # 1. Configure mock (it will not be the source of failure)
    mock_material_class.set_k_value(0.1)

    # 2. Run calculation with invalid wavelength
    thickness, error_msg = service.calculate_thickness(
        ref_image=test_images["ref"],
        mat_image=test_images["mat"],
        shelf="test", book="test", page="test",
        wavelength_um=0.0  # invalid value
    )

    # 3. Verify error
    assert thickness is None
    assert error_msg is not None
    assert "Math Error" in error_msg
    assert "Wellenlänge muss größer als 0 sein" in error_msg


def test_calculate_thickness_division_error(
    service: CalculationService,
    test_images: dict,
    mock_material_class: MockRefractiveIndexMaterial
):
    """
    Test the pipeline when berechne_x fails (e.g., k=0 -> alpha=0).
    """
    # 1. Configure mock to return k=0
    mock_material_class.set_k_value(0.0)

    # 2. Run calculation
    thickness, error_msg = service.calculate_thickness(
        ref_image=test_images["ref"],
        mat_image=test_images["mat"],
        shelf="test", book="test", page="test",
        wavelength_um=0.5
    )

    # 3. Verify error
    # k=0 -> alpha=0 -> berechne_x gets f=0 -> returns None
    assert thickness is None
    assert error_msg is not None
    assert "Calculation Error" in error_msg
    assert "Division by zero" in error_msg