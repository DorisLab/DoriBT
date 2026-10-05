import pytest


@pytest.fixture(params=["python", pytest.param("numba", marks=pytest.mark.numba)])
def backend(request):
    return request.param
