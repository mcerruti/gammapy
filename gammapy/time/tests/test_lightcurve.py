# Licensed under a 3-clause BSD style license - see LICENSE.rst
import datetime
import pytest
import numpy as np
from numpy.testing import assert_allclose
import astropy.units as u
from astropy.table import Column, Table
from astropy.time import Time
from gammapy.data import GTI
from gammapy.modeling.models import PowerLawSpectralModel
from gammapy.spectrum.tests.test_flux_point_estimator import (
    simulate_map_dataset,
    simulate_spectrum_dataset,
)
from gammapy.time import LightCurve, LightCurveEstimator
from gammapy.utils.testing import (
    assert_quantity_allclose,
    mpl_plot_check,
    requires_data,
    requires_dependency,
)

# time time_min time_max flux flux_err flux_ul
# 48705.1757 48705.134 48705.2174 0.57 0.29 nan
# 48732.89195 48732.8503 48732.9336 0.39 0.29 nan
# 48734.0997 48734.058 48734.1414 0.48 0.29 nan
# 48738.98535 48738.9437 48739.027 nan nan 0.97
# 48741.0259 48740.9842 48741.0676 0.34 0.29 nan


@pytest.fixture(scope="session")
def lc():
    meta = dict(TIMESYS="utc")

    table = Table(
        meta=meta,
        data=[
            Column(Time(["2010-01-01", "2010-01-03"]).mjd, "time_min"),
            Column(Time(["2010-01-03", "2010-01-10"]).mjd, "time_max"),
            Column([1e-11, 3e-11], "flux", unit="cm-2 s-1"),
            Column([0.1e-11, 0.3e-11], "flux_err", unit="cm-2 s-1"),
            Column([np.nan, 3.6e-11], "flux_ul", unit="cm-2 s-1"),
            Column([False, True], "is_ul"),
        ],
    )

    return LightCurve(table=table)


def test_lightcurve_repr(lc):
    assert repr(lc) == "LightCurve(len=2)"


def test_lightcurve_properties_time(lc):
    assert lc.time_scale == "utc"
    assert lc.time_format == "mjd"

    # Time-related attributes
    time = lc.time
    assert time.scale == "utc"
    assert time.format == "mjd"
    assert_allclose(time.mjd, [55198, 55202.5])

    assert_allclose(lc.time_min.mjd, [55197, 55199])
    assert_allclose(lc.time_max.mjd, [55199, 55206])

    # Note: I'm not sure why the time delta has this scale and format
    time_delta = lc.time_delta
    assert time_delta.scale == "tai"
    assert time_delta.format == "jd"
    assert_allclose(time_delta.jd, [2, 7])


def test_lightcurve_properties_flux(lc):
    flux = lc.table["flux"].quantity
    assert flux.unit == "cm-2 s-1"
    assert_allclose(flux.value, [1e-11, 3e-11])


# TODO: extend these tests to cover other time scales.
# In those cases, CSV should not round-trip because there
# is no header info in CSV to store the time scale!


@pytest.mark.parametrize("format", ["fits", "ascii.ecsv", "ascii.csv"])
def test_lightcurve_read_write(tmp_path, lc, format):
    lc.write(tmp_path / "tmp", format=format)
    lc = LightCurve.read(tmp_path / "tmp", format=format)

    # Check if time-related info round-trips
    time = lc.time
    assert time.scale == "utc"
    assert time.format == "mjd"
    assert_allclose(time.mjd, [55198, 55202.5])


@requires_dependency("matplotlib")
def test_lightcurve_plot(lc):
    with mpl_plot_check():
        lc.plot()


@pytest.mark.parametrize("flux_unit", ["cm-2 s-1"])
def test_lightcurve_plot_flux(lc, flux_unit):
    f, ferr = lc._get_fluxes_and_errors(flux_unit)
    assert_allclose(f, [1e-11, 3e-11])
    assert_allclose(ferr, ([0.1e-11, 0.3e-11], [0.1e-11, 0.3e-11]))


@pytest.mark.parametrize("flux_unit", ["cm-2 s-1"])
def test_lightcurve_plot_flux_ul(lc, flux_unit):
    is_ul, ful = lc._get_flux_uls(flux_unit)
    assert_allclose(is_ul, [False, True])
    assert_allclose(ful, [np.nan, 3.6e-11])


def test_lightcurve_plot_time(lc):
    t, terr = lc._get_times_and_errors("mjd")
    assert np.array_equal(t, [55198.0, 55202.5])
    assert np.array_equal(terr, [[1.0, 3.5], [1.0, 3.5]])

    t, terr = lc._get_times_and_errors("iso")
    assert np.array_equal(
        t, [datetime.datetime(2010, 1, 2), datetime.datetime(2010, 1, 6, 12)]
    )
    assert np.array_equal(
        terr,
        [
            [datetime.timedelta(1), datetime.timedelta(3.5)],
            [datetime.timedelta(1), datetime.timedelta(3.5)],
        ],
    )


def get_spectrum_datasets():
    model = PowerLawSpectralModel()
    dataset_1 = simulate_spectrum_dataset(model=model, random_state=0)
    gti1 = GTI.create("0h", "1h", "2010-01-01T00:00:00")
    dataset_1.gti = gti1

    dataset_2 = simulate_spectrum_dataset(model, random_state=1)
    gti2 = GTI.create("1h", "2h", "2010-01-01T00:00:00")
    dataset_2.gti = gti2


    return [dataset_1, dataset_2]


@requires_data()
@requires_dependency("iminuit")
def test_lightcurve_estimator_spectrum_datasets():
    datasets = get_spectrum_datasets()

    estimator = LightCurveEstimator(datasets, norm_n_values=3)
    lightcurve = estimator.run(e_ref=10 * u.TeV, e_min=1 * u.TeV, e_max=100 * u.TeV)

    assert_allclose(lightcurve.table["time_min"], [55197.0, 55197.041667])
    assert_allclose(lightcurve.table["time_max"], [55197.041667, 55197.083333])
    assert_allclose(lightcurve.table["e_ref"], [10, 10])
    assert_allclose(lightcurve.table["e_min"], [1, 1])
    assert_allclose(lightcurve.table["e_max"], [100, 100])
    assert_allclose(lightcurve.table["ref_dnde"], [1e-14, 1e-14])
    assert_allclose(lightcurve.table["ref_flux"], [9.9e-13, 9.9e-13])
    assert_allclose(lightcurve.table["ref_eflux"], [4.60517e-12, 4.60517e-12])
    assert_allclose(lightcurve.table["ref_e2dnde"], [1e-12, 1e-12])
    assert_allclose(lightcurve.table["stat"], [23.302288, 22.457766], rtol=1e-5)
    assert_allclose(lightcurve.table["norm"], [0.988127, 0.948108], rtol=1e-5)
    assert_allclose(lightcurve.table["norm_err"], [0.043985, 0.043498], rtol=1e-4)
    assert_allclose(lightcurve.table["counts"], [2281, 2222])
    assert_allclose(lightcurve.table["norm_errp"], [0.044231, 0.04377], rtol=1e-5)
    assert_allclose(lightcurve.table["norm_errn"], [0.04374, 0.043226], rtol=1e-5)
    assert_allclose(lightcurve.table["norm_ul"], [1.077213, 1.036237], rtol=1e-5)
    assert_allclose(lightcurve.table["sqrt_ts"], [37.16802, 37.168033], rtol=1e-5)
    assert_allclose(lightcurve.table["ts"], [1381.461738, 1381.462675], rtol=1e-5)
    assert_allclose(lightcurve.table[0]["norm_scan"], [0.2, 1.0, 5.0])
    assert_allclose(
        lightcurve.table[0]["stat_scan"],
        [444.426957, 23.375417, 3945.382802],
        rtol=1e-5,
    )


def get_map_datasets():
    dataset_1 = simulate_map_dataset(random_state=0)
    gti1 = GTI.create("0 h", "1 h", "2010-01-01T00:00:00")
    dataset_1.gti = gti1

    dataset_2 = simulate_map_dataset(random_state=1)
    gti2 = GTI.create("1 h", "2 h", "2010-01-01T00:00:00")
    dataset_2.gti = gti2

    return [dataset_1, dataset_2]


@requires_data()
@requires_dependency("iminuit")
def test_lightcurve_estimator_map_datasets():
    datasets = get_map_datasets()

    estimator = LightCurveEstimator(datasets, source="source")
    steps = ["err", "counts", "ts", "norm-scan"]
    lightcurve = estimator.run(
        e_ref=10 * u.TeV, e_min=1 * u.TeV, e_max=100 * u.TeV, steps=steps
    )

    assert_allclose(lightcurve.table["time_min"], [55197.0, 55197.041667])
    assert_allclose(lightcurve.table["time_max"], [55197.041667, 55197.083333])
    assert_allclose(lightcurve.table["e_ref"], [10, 10])
    assert_allclose(lightcurve.table["e_min"], [1, 1])
    assert_allclose(lightcurve.table["e_max"], [100, 100])
    assert_allclose(lightcurve.table["ref_dnde"], [1e-13, 1e-13])
    assert_allclose(lightcurve.table["ref_flux"], [9.9e-12, 9.9e-12])
    assert_allclose(lightcurve.table["ref_eflux"], [4.60517e-11, 4.60517e-11])
    assert_allclose(lightcurve.table["ref_e2dnde"], [1e-11, 1e-11])
    assert_allclose(lightcurve.table["stat"], [-86845.74348, -90386.086642], rtol=1e-5)
    assert_allclose(lightcurve.table["norm_err"], [0.041529, 0.041785], rtol=1e-3)
    assert_allclose(lightcurve.table["counts"], [46702, 47508])
    assert_allclose(lightcurve.table["sqrt_ts"], [54.503321, 54.296488], atol=0.01)
    assert_allclose(lightcurve.table["ts"], [2970.61202, 2948.108572], atol=0.01)
