"""
Copyright 2019 Goldman Sachs.
Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

  http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing,
software distributed under the License is distributed on an
"AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
KIND, either express or implied.  See the License for the
specific language governing permissions and limitations
under the License.
"""

import datetime
import datetime as dt
from typing import Union

import pandas as pd
import pytest
from numpy.testing import assert_allclose
from pandas.testing import assert_series_equal
from pytz import timezone
from testfixtures import Replacer
from testfixtures.mock import Mock

import gs_quant.timeseries.measures as tm
import gs_quant.timeseries.measures_rates as tm_rates
from gs_quant.api.gs.assets import GsTemporalXRef, GsAssetApi, GsIdType, IdList, GsAsset
from gs_quant.api.gs.data import GsDataApi, MarketDataResponseFrame
from gs_quant.data.core import DataContext
from gs_quant.data.dataset import Dataset
from gs_quant.data.fields import Fields
from gs_quant.errors import MqError, MqValueError
from gs_quant.markets.securities import AssetClass, Cross, Index, Currency, SecurityMaster, Stock
from gs_quant.session import GsSession, Environment
from gs_quant.target.common import XRef, PricingLocation, Currency as CurrEnum
from gs_quant.test.timeseries.utils import mock_request
from gs_quant.timeseries.measures import BenchmarkType
from gs_quant.api.gs.data import QueryType

_index = [pd.Timestamp('2019-01-01')]
_test_datasets = ('TEST_DATASET',)


def mock_empty_market_data_response():
    df = MarketDataResponseFrame()
    df.dataset_ids = ()
    return df


def map_identifiers_default_mocker(input_type: Union[GsIdType, str],
                                   output_type: Union[GsIdType, str],
                                   ids: IdList,
                                   as_of: dt.datetime = None,
                                   multimap: bool = False,
                                   limit: int = None,
                                   **kwargs
                                   ) -> dict:
    if "USD-LIBOR-BBA" in ids:
        return {"USD-LIBOR-BBA": "MAPDB7QNB2TZVQ0E"}
    elif "EUR-EURIBOR-TELERATE" in ids:
        return {"EUR-EURIBOR-TELERATE": "MAJNQPFGN1EBDHAE"}
    elif "GBP-LIBOR-BBA" in ids:
        return {"GBP-LIBOR-BBA": "MAFYB8Z4R1377A19"}
    elif "JPY-LIBOR-BBA" in ids:
        return {"JPY-LIBOR-BBA": "MABMVE27EM8YZK33"}
    elif "EUR OIS" in ids:
        return {"EUR OIS": "MARFAGXDQRWM07Y2"}


def map_identifiers_swap_rate_mocker(input_type: Union[GsIdType, str],
                                     output_type: Union[GsIdType, str],
                                     ids: IdList,
                                     as_of: dt.datetime = None,
                                     multimap: bool = False,
                                     limit: int = None,
                                     **kwargs
                                     ) -> dict:
    if "USD-3m" in ids:
        return {"USD-3m": "MAAXGV0GZTW4GFNC"}
    elif "EUR-6m" in ids:
        return {"EUR-6m": "MA5WM2QWRVMYKDK0"}
    elif "KRW" in ids:
        return {"KRW": 'MAJ6SEQH3GT0GA2Z'}


def map_identifiers_inflation_mocker(input_type: Union[GsIdType, str],
                                     output_type: Union[GsIdType, str],
                                     ids: IdList,
                                     as_of: dt.datetime = None,
                                     multimap: bool = False,
                                     limit: int = None,
                                     **kwargs
                                     ) -> dict:
    if "CPI-UKRPI" in ids:
        return {"CPI-UKRPI": "MAQ7ND0MBP2AVVQW"}
    elif "CPI-CPXTEMU" in ids:
        return {"CPI-CPXTEMU": "MAK1FHKH5P5GJSHH"}


def map_identifiers_cross_basis_mocker(input_type: Union[GsIdType, str],
                                       output_type: Union[GsIdType, str],
                                       ids: IdList,
                                       as_of: dt.datetime = None,
                                       multimap: bool = False,
                                       limit: int = None,
                                       **kwargs
                                       ) -> dict:
    if "USD-3m/JPY-3m" in ids:
        return {"USD-3m/JPY-3m": "MA99N6C1KF9078NM"}
    elif "EUR-3m/USD-3m" in ids:
        return {"EUR-3m/USD-3m": "MAXPKTXW2D4X6MFQ"}
    elif "GBP-3m/USD-3m" in ids:
        return {"GBP-3m/USD-3m": "MA8BZHQV3W32V63B"}


def get_data_policy_rate_expectation_mocker(
        start: Union[dt.date, dt.datetime] = None,
        end: Union[dt.date, dt.datetime] = None,
        as_of: dt.datetime = None,
        since: dt.datetime = None,
        fields: Union[str, Fields] = None,
        asset_id_type: str = None,
        **kwargs) -> pd.DataFrame:
    if 'meetingNumber' in kwargs:
        if kwargs['meetingNumber'] == 0:
            return mock_meeting_spot()
    elif 'meeting_date' in kwargs:
        if kwargs['meeting_date'] == dt.date(2019, 10, 24):
            return mock_meeting_spot()
    return mock_meeting_expectation()


def test_parse_meeting_date(mocker):
    assert tm.parse_meeting_date(5) == ''
    assert tm.parse_meeting_date('') == ''
    assert tm.parse_meeting_date('test') == ''
    assert tm.parse_meeting_date('2019-09-01') == dt.date(2019, 9, 1)


def test_currency_to_default_benchmark_rate(mocker):
    mocker.patch.object(GsSession.__class__, 'default_value',
                        return_value=GsSession.get(Environment.QA, 'client_id', 'secret'))
    mocker.patch.object(GsSession.current, '_get', side_effect=mock_request)
    mocker.patch.object(GsAssetApi, 'map_identifiers', side_effect=map_identifiers_default_mocker)

    asset_id_list = ["MAZ7RWC904JYHYPS", "MAJNQPFGN1EBDHAE", "MA66CZBQJST05XKG", "MAK1FHKH5P5GJSHH", "MA4J1YB8XZP2BPT8",
                     "MA4B66MW5E27U8P32SB"]
    correct_mapping = ["MAPDB7QNB2TZVQ0E", "MAJNQPFGN1EBDHAE", "MAFYB8Z4R1377A19", "MABMVE27EM8YZK33",
                       "MA4J1YB8XZP2BPT8", "MA4B66MW5E27U8P32SB"]
    with tm.PricingContext(dt.date.today()):
        for i in range(len(asset_id_list)):
            correct_id = tm.currency_to_default_benchmark_rate(asset_id_list[i])
            assert correct_id == correct_mapping[i]


def test_currency_to_default_swap_rate_asset(mocker):
    mocker.patch.object(GsSession.__class__, 'default_value',
                        return_value=GsSession.get(Environment.QA, 'client_id', 'secret'))
    mocker.patch.object(GsSession.current, '_get', side_effect=mock_request)
    mocker.patch.object(GsAssetApi, 'map_identifiers', side_effect=map_identifiers_swap_rate_mocker)

    asset_id_list = ['MAZ7RWC904JYHYPS', 'MAJNQPFGN1EBDHAE', 'MAJ6SEQH3GT0GA2Z']
    correct_mapping = ['MAAXGV0GZTW4GFNC', 'MA5WM2QWRVMYKDK0', 'MAJ6SEQH3GT0GA2Z']
    with tm.PricingContext(dt.date.today()):
        for i in range(len(asset_id_list)):
            correct_id = tm.currency_to_default_swap_rate_asset(asset_id_list[i])
            assert correct_id == correct_mapping[i]


def test_currency_to_inflation_benchmark_rate(mocker):
    mocker.patch.object(GsSession.__class__, 'default_value',
                        return_value=GsSession.get(Environment.QA, 'client_id', 'secret'))
    mocker.patch.object(GsSession.current, '_get', side_effect=mock_request)
    mocker.patch.object(GsAssetApi, 'map_identifiers', side_effect=map_identifiers_inflation_mocker)

    asset_id_list = ["MA66CZBQJST05XKG", "MAK1FHKH5P5GJSHH", "MA4J1YB8XZP2BPT8"]
    correct_mapping = ["MAQ7ND0MBP2AVVQW", "MAK1FHKH5P5GJSHH", "MA4J1YB8XZP2BPT8"]
    with tm.PricingContext(dt.date.today()):
        for i in range(len(asset_id_list)):
            correct_id = tm.currency_to_inflation_benchmark_rate(asset_id_list[i])
            assert correct_id == correct_mapping[i]

        # Test that the same id is returned when a TypeError is raised
        mocker.patch.object(GsAssetApi, 'map_identifiers', side_effect=TypeError('Test'))
        assert tm.currency_to_inflation_benchmark_rate('MA66CZBQJST05XKG') == 'MA66CZBQJST05XKG'


def test_cross_to_basis(mocker):
    mocker.patch.object(GsSession.__class__, 'default_value',
                        return_value=GsSession.get(Environment.QA, 'client_id', 'secret'))
    mocker.patch.object(GsSession.current, '_get', side_effect=mock_request)
    mocker.patch.object(GsAssetApi, 'map_identifiers', side_effect=map_identifiers_cross_basis_mocker)

    asset_id_list = ["MAYJPCVVF2RWXCES", "MA4B66MW5E27U8P32SB", "nobbid"]
    correct_mapping = ["MA99N6C1KF9078NM", "MA4B66MW5E27U8P32SB", "nobbid"]
    with tm.PricingContext(dt.date.today()):
        for i in range(len(asset_id_list)):
            correct_id = tm.cross_to_basis(asset_id_list[i])
            assert correct_id == correct_mapping[i]

        # Test that the same id is returned when a TypeError is raised
        mocker.patch.object(GsAssetApi, 'map_identifiers', side_effect=TypeError('Test'))
        assert tm.cross_to_basis('MAYJPCVVF2RWXCES') == 'MAYJPCVVF2RWXCES'


def test_currency_to_mdapi_swap_rate_asset(mocker):
    replace = Replacer()
    mocker.patch.object(GsSession.__class__, 'current',
                        return_value=GsSession.get(Environment.QA, 'client_id', 'secret'))
    mocker.patch.object(GsSession.current, '_get', side_effect=mock_request)
    mocker.patch.object(SecurityMaster, 'get_asset', side_effect=mock_request)
    bbid_mock = replace('gs_quant.timeseries.measures.Asset.get_identifier', Mock())
    with tm.PricingContext(dt.date.today()):
        asset = Currency('MA890', 'NOK')
        bbid_mock.return_value = 'NOK'
        assert 'MA890' == tm_rates._currency_to_mdapi_swap_rate_asset(asset)
        asset = Currency('MAZ7RWC904JYHYPS', 'USD')
        bbid_mock.return_value = 'USD'
        correct_id = tm_rates._currency_to_mdapi_swap_rate_asset(asset)
        assert 'MAFRSWPAF5QPNTP2' == correct_id
        bbid_mock.return_value = 'CHF'
        correct_id = tm_rates._currency_to_mdapi_swap_rate_asset(asset)
        assert 'MAW25BGQJH9P6DPT' == correct_id
        bbid_mock.return_value = 'EUR'
        correct_id = tm_rates._currency_to_mdapi_swap_rate_asset(asset)
        assert 'MAA9MVX15AJNQCVG' == correct_id
        bbid_mock.return_value = 'GBP'
        correct_id = tm_rates._currency_to_mdapi_swap_rate_asset(asset)
        assert 'MA6QCAP9B7ABS9HA' == correct_id
        bbid_mock.return_value = 'JPY'
        correct_id = tm_rates._currency_to_mdapi_swap_rate_asset(asset)
        assert 'MAEE219J5ZP0ZKRK' == correct_id
        bbid_mock.return_value = 'SEK'
        correct_id = tm_rates._currency_to_mdapi_swap_rate_asset(asset)
        assert 'MAETMVTPNP3199A5' == correct_id

    replace.restore()


def test_currency_to_mdapi_basis_swap_rate_asset(mocker):
    replace = Replacer()
    mocker.patch.object(GsSession.__class__, 'current',
                        return_value=GsSession.get(Environment.QA, 'client_id', 'secret'))
    mocker.patch.object(GsSession.current, '_get', side_effect=mock_request)
    mocker.patch.object(SecurityMaster, 'get_asset', side_effect=mock_request)
    bbid_mock = replace('gs_quant.timeseries.measures.Asset.get_identifier', Mock())
    with tm.PricingContext(dt.date.today()):
        asset = Currency('MA890', 'NOK')
        bbid_mock.return_value = 'NOK'
        assert 'MA890' == tm_rates._currency_to_mdapi_basis_swap_rate_asset(asset)
        asset = Currency('MAZ7RWC904JYHYPS', 'USD')
        bbid_mock.return_value = 'USD'
        correct_id = tm_rates._currency_to_mdapi_basis_swap_rate_asset(asset)
        assert 'MAQB1PGEJFCET3GG' == correct_id
        bbid_mock.return_value = 'EUR'
        correct_id = tm_rates._currency_to_mdapi_basis_swap_rate_asset(asset)
        assert 'MAGRG2VT11GQ2RQ9' == correct_id
        bbid_mock.return_value = 'GBP'
        correct_id = tm_rates._currency_to_mdapi_basis_swap_rate_asset(asset)
        assert 'MAHCYNB3V75JC5Q8' == correct_id
        bbid_mock.return_value = 'JPY'
        correct_id = tm_rates._currency_to_mdapi_basis_swap_rate_asset(asset)
        assert 'MAXVRBEZCJVH0C4V' == correct_id
    replace.restore()


def test_check_clearing_house(mocker):
    assert tm_rates._ClearingHouse.CME == tm_rates._check_clearing_house(tm_rates._ClearingHouse.CME)
    assert tm_rates._ClearingHouse.LCH == tm_rates._check_clearing_house(None)
    invalid_ch = ['NYSE']
    for ch in invalid_ch:
        with pytest.raises(MqError):
            tm_rates._check_clearing_house(ch)


def test_cross_stored_direction_for_fx_vol(mocker):
    mocker.patch.object(GsSession.__class__, 'default_value',
                        return_value=GsSession.get(Environment.QA, 'client_id', 'secret'))
    mocker.patch.object(GsSession.current, '_get', side_effect=mock_request)
    mocker.patch.object(GsSession.current, '_post', side_effect=mock_request)
    asset_id_list = ["MAYJPCVVF2RWXCES", "MATGYV0J9MPX534Z"]
    correct_mapping = ["MATGYV0J9MPX534Z", "MATGYV0J9MPX534Z"]
    with tm.PricingContext(dt.date.today()):
        for i in range(len(asset_id_list)):
            correct_id = tm.cross_stored_direction_for_fx_vol(asset_id_list[i])
            assert correct_id == correct_mapping[i]


def test_cross_to_usd_based_cross_for_fx_forecast(mocker):
    mocker.patch.object(GsSession.__class__, 'default_value',
                        return_value=GsSession.get(Environment.QA, 'client_id', 'secret'))
    mocker.patch.object(GsSession.current, '_get', side_effect=mock_request)
    mocker.patch.object(GsSession.current, '_post', side_effect=mock_request)
    asset_id_list = ["MAYJPCVVF2RWXCES", "MATGYV0J9MPX534Z"]
    correct_mapping = ["MATGYV0J9MPX534Z", "MATGYV0J9MPX534Z"]
    with tm.PricingContext(dt.date.today()):
        for i in range(len(asset_id_list)):
            correct_id = tm.cross_to_usd_based_cross(asset_id_list[i])
            assert correct_id == correct_mapping[i]


def test_cross_to_used_based_cross(mocker):
    mocker.patch.object(GsSession.__class__, 'default_value',
                        return_value=GsSession.get(Environment.QA, 'client_id', 'secret'))
    mocker.patch.object(GsSession.current, '_get', side_effect=mock_request)
    mocker.patch.object(GsSession.current, '_post', side_effect=mock_request)
    mocker.patch.object(SecurityMaster, 'get_asset', side_effect=TypeError('unsupported'))

    replace = Replacer()
    bbid_mock = replace('gs_quant.timeseries.measures.Asset.get_identifier', Mock())
    bbid_mock.return_value = 'HELLO'

    assert 'FUN' == tm.cross_to_usd_based_cross(Cross('FUN', 'EURUSD'))
    replace.restore()


def test_cross_stored_direction(mocker):
    mocker.patch.object(GsSession.__class__, 'default_value',
                        return_value=GsSession.get(Environment.QA, 'client_id', 'secret'))
    mocker.patch.object(GsSession.current, '_get', side_effect=mock_request)
    mocker.patch.object(GsSession.current, '_post', side_effect=mock_request)
    mocker.patch.object(SecurityMaster, 'get_asset', side_effect=TypeError('unsupported'))

    replace = Replacer()
    bbid_mock = replace('gs_quant.timeseries.measures.Asset.get_identifier', Mock())
    bbid_mock.return_value = 'HELLO'

    assert 'FUN' == tm.cross_stored_direction_for_fx_vol(Cross('FUN', 'EURUSD'))
    replace.restore()


def test_convert_asset_for_mdapi_swap_rates():
    mock_asset_1 = GsAsset(asset_class='Rate', id='MAW25BGQJH9P6DPT', type_='Swap', name='Test_asset')
    mock_asset_2 = GsAsset(asset_class='Rate', id='MAA9MVX15AJNQCVG', type_='Swap', name='Test_asset')

    replace = Replacer()
    assets = replace('gs_quant.timeseries.measures.GsAssetApi.get_many_assets', Mock())
    assets.return_value = [mock_asset_1]
    assert 'MAW25BGQJH9P6DPT' == tm_rates._convert_asset_for_mdapi_swap_rates()
    replace.restore()

    assets = replace('gs_quant.timeseries.measures.GsAssetApi.get_many_assets', Mock())
    assets.return_value = [mock_asset_1, mock_asset_2]
    with pytest.raises(MqValueError):
        tm_rates._convert_asset_for_mdapi_swap_rates()
    replace.restore()

    assets = replace('gs_quant.timeseries.measures.GsAssetApi.get_many_assets', Mock())
    assets.return_value = []
    with pytest.raises(MqValueError):
        tm_rates._convert_asset_for_mdapi_swap_rates()
    replace.restore()


def test_get_swap_leg_defaults(mocker):
    result_dict = dict(currency=CurrEnum.JPY, benchmark_type='JPY-LIBOR-BBA', floating_rate_tenor='6m',
                       pricing_location=PricingLocation.TKO)
    defaults = tm_rates._get_swap_leg_defaults(CurrEnum.JPY)
    assert result_dict == defaults

    result_dict = dict(currency=CurrEnum.USD, benchmark_type='USD-LIBOR-BBA', floating_rate_tenor='3m',
                       pricing_location=PricingLocation.NYC)
    defaults = tm_rates._get_swap_leg_defaults(CurrEnum.USD)
    assert result_dict == defaults

    result_dict = dict(currency=CurrEnum.EUR, benchmark_type='EUR-EURIBOR-Telerate', floating_rate_tenor='6m',
                       pricing_location=PricingLocation.LDN)
    defaults = tm_rates._get_swap_leg_defaults(CurrEnum.EUR)
    assert result_dict == defaults

    result_dict = dict(currency=CurrEnum.SEK, benchmark_type='SEK-STIBOR-SIDE', floating_rate_tenor='6m',
                       pricing_location=PricingLocation.LDN)
    defaults = tm_rates._get_swap_leg_defaults(CurrEnum.SEK)
    assert result_dict == defaults


def test_check_forward_tenor():
    valid_tenors = [datetime.date(2020, 1, 1), '1y', 'imm2', 'frb2', '1m', '0b']
    for tenor in valid_tenors:
        assert tenor == tm_rates.check_forward_tenor(tenor)

    invalid_tenors = ['5yr', 'imm5', 'frb0']
    for tenor in invalid_tenors:
        with pytest.raises(MqError):
            tm_rates.check_forward_tenor(tenor)


def mock_commod(_cls, _q):
    d = {
        'price': [30, 30, 30, 30, 35.929686, 35.636039, 27.307498, 23.23177, 19.020833, 18.827291, 17.823749, 17.393958,
                  17.824999, 20.307603, 24.311249, 25.160103, 25.245728, 25.736873, 28.425206, 28.779789, 30.519996,
                  34.896348, 33.966973, 33.95489, 33.686348, 34.840307, 32.674163, 30.261665, 30, 30, 30]
    }
    df = MarketDataResponseFrame(data=d, index=pd.date_range('2019-05-01', periods=31, freq='H', tz=timezone('UTC')))
    df.dataset_ids = _test_datasets
    return df


def mock_forward_price(_cls, _q):
    d = {
        'forwardPrice': [
            22.0039,
            24.8436,
            24.8436,
            11.9882,
            14.0188,
            11.6311,
            18.9234,
            21.3654,
            21.3654,
        ],
        'quantityBucket': [
            "PEAK",
            "PEAK",
            "PEAK",
            "7X8",
            "7X8",
            "7X8",
            "2X16H",
            "2X16H",
            "2X16H",

        ],
        'contract': [
            "J20",
            "K20",
            "M20",
            "J20",
            "K20",
            "M20",
            "J20",
            "K20",
            "M20",
        ]

    }
    df = MarketDataResponseFrame(data=d, index=pd.to_datetime([datetime.date(2019, 1, 2)] * 9))
    df.dataset_ids = _test_datasets
    return df


def mock_fair_price(_cls, _q):
    d = {
        'fairPrice': [
            2.880,
            2.844,
            2.726,
        ],
        'contract': [
            "F21",
            "G21",
            "H21",
        ]}
    df = MarketDataResponseFrame(data=d, index=pd.to_datetime([datetime.date(2019, 1, 2)] * 3))
    df.dataset_ids = _test_datasets
    return df


def mock_implied_volatility(_cls, _q):
    d = {
        'impliedVolatility': [
            2.880,
            2.844,
            2.726,
        ],
        'contract': [
            "F21",
            "G21",
            "H21",
        ]}
    df = MarketDataResponseFrame(data=d, index=pd.to_datetime([datetime.date(2019, 1, 2)] * 3))
    df.dataset_ids = _test_datasets
    return df


def mock_missing_bucket_forward_price(_cls, _q):
    d = {
        'forwardPrice': [
            22.0039,
            24.8436,
            24.8436,
            11.9882,
            14.0188,
            18.9234,
            21.3654,
            21.3654,
        ],
        'quantityBucket': [
            "PEAK",
            "PEAK",
            "PEAK",
            "7X8",
            "7X8",
            "2X16H",
            "2X16H",
            "2X16H",

        ],
        'contract': [
            "J20",
            "K20",
            "M20",
            "J20",
            "K20",
            "J20",
            "K20",
            "M20",
        ]

    }
    return pd.DataFrame(data=d, index=pd.to_datetime([datetime.date(2019, 1, 2)] * 8))


def mock_fx(_cls, _q):
    d = {
        'strikeReference': ['delta', 'spot', 'forward'],
        'relativeStrike': [25, 100, 100],
        'impliedVolatility': [5, 1, 2],
        'forecast': [1.1, 1.1, 1.1]
    }
    df = MarketDataResponseFrame(data=d, index=_index * 3)
    df.dataset_ids = _test_datasets
    return df


def mock_fx_delta(_cls, _q):
    d = {
        'relativeStrike': [25, -25, 0],
        'impliedVolatility': [1, 5, 2],
        'forecast': [1.1, 1.1, 1.1]
    }
    df = MarketDataResponseFrame(data=d, index=_index * 3)
    df.dataset_ids = _test_datasets
    return df


def mock_fx_empty(_cls, _q):
    d = {
        'strikeReference': [],
        'relativeStrike': [],
        'impliedVolatility': []
    }
    df = MarketDataResponseFrame(data=d, index=[])
    df.dataset_ids = _test_datasets
    return df


def mock_fx_switch(_cls, _q, _n):
    replace = Replacer()
    replace('gs_quant.timeseries.measures.GsDataApi.get_market_data', mock_fx_empty)
    replace.restore()
    return Cross('MA1889', 'ABC/XYZ')


def mock_curr(_cls, _q):
    d = {
        'swapAnnuity': [1, 2, 3],
        'swapRate': [1, 2, 3],
        'basisSwapRate': [1, 2, 3],
        'swaptionVol': [1, 2, 3],
        'atmFwdRate': [1, 2, 3],
        'midcurveVol': [1, 2, 3],
        'capFloorVol': [1, 2, 3],
        'spreadOptionVol': [1, 2, 3],
        'inflationSwapRate': [1, 2, 3],
        'midcurveAtmFwdRate': [1, 2, 3],
        'capFloorAtmFwdRate': [1, 2, 3],
        'spreadOptionAtmFwdRate': [1, 2, 3]
    }
    df = MarketDataResponseFrame(data=d, index=_index * 3)
    df.dataset_ids = _test_datasets
    return df


def mock_cross(_cls, _q):
    d = {
        'basis': [1, 2, 3],
    }
    df = MarketDataResponseFrame(data=d, index=_index * 3)
    df.dataset_ids = _test_datasets
    return df


def mock_eq(_cls, _q):
    d = {
        'relativeStrike': [0.75, 0.25, 0.5],
        'impliedVolatility': [5, 1, 2],
        'impliedCorrelation': [5, 1, 2],
        'averageImpliedVolatility': [5, 1, 2],
        'averageImpliedVariance': [5, 1, 2],
        'impliedVolatilityByDeltaStrike': [5, 1, 2],
        'fundamentalMetric': [5, 1, 2]
    }
    df = MarketDataResponseFrame(data=d, index=_index * 3)
    df.dataset_ids = _test_datasets
    return df


def mock_eq_norm(_cls, _q):
    d = {
        'relativeStrike': [-4.0, 4.0, 0],
        'impliedVolatility': [5, 1, 2]
    }
    df = MarketDataResponseFrame(data=d, index=_index * 3)
    df.dataset_ids = _test_datasets
    return df


def mock_eq_spot(_cls, _q):
    d = {
        'relativeStrike': [0.75, 1.25, 1.0],
        'impliedVolatility': [5, 1, 2]
    }
    df = MarketDataResponseFrame(data=d, index=_index * 3)
    df.dataset_ids = _test_datasets
    return df


def mock_inc(_cls, _q):
    d = {
        'relativeStrike': [0.25, 0.75],
        'impliedVolatility': [5, 1]
    }
    df = MarketDataResponseFrame(data=d, index=_index * 2)
    df.dataset_ids = _test_datasets
    return df


def mock_meeting_expectation():
    data_dict = MarketDataResponseFrame({'date': [dt.date(2019, 12, 6)],
                                         'assetId': ['MARFAGXDQRWM07Y2'],
                                         'location': ['NYC'],
                                         'rateType': ['Meeting Forward'],
                                         'startingDate': [dt.date(2020, 1, 29)],
                                         'endingDate': [dt.date(2020, 1, 29)],
                                         'meetingNumber': [2],
                                         'valuationDate': [dt.date(2019, 12, 6)],
                                         'meetingDate': [dt.date(2020, 1, 23)],
                                         'value': [-0.004550907771]
                                         })
    data_dict.dataset_ids = _test_datasets
    return data_dict


def mock_meeting_spot():
    data_dict = MarketDataResponseFrame({'date': [dt.date(2019, 12, 6)],
                                         'assetId': ['MARFAGXDQRWM07Y2'],
                                         'location': ['NYC'],
                                         'rateType': ['Meeting Forward'],
                                         'startingDate': [dt.date(2019, 10, 30)],
                                         'endingDate': [dt.date(2019, 12, 18)],
                                         'meetingNumber': [0],
                                         'valuationDate': [dt.date(2019, 12, 6)],
                                         'meetingDate': [dt.date(2019, 10, 24)],
                                         'value': [-0.004522570525]
                                         })
    data_dict.dataset_ids = _test_datasets
    return data_dict


def mock_meeting_absolute():
    data_dict = MarketDataResponseFrame({'date': [datetime.date(2019, 12, 6), datetime.date(2019, 12, 6)],
                                         'assetId': ['MARFAGXDQRWM07Y2', 'MARFAGXDQRWM07Y2'],
                                         'location': ['NYC', 'NYC'],
                                         'rateType': ['Meeting Forward', 'Meeting Forward'],
                                         'startingDate': [datetime.date(2019, 10, 30), datetime.date(2020, 1, 29)],
                                         'endingDate': [datetime.date(2019, 10, 30), datetime.date(2020, 1, 29)],
                                         'meetingNumber': [0, 2],
                                         'valuationDate': [datetime.date(2019, 12, 6), datetime.date(2019, 12, 6)],
                                         'meetingDate': [datetime.date(2019, 10, 24), datetime.date(2020, 1, 23)],
                                         'value': [-0.004522570525, -0.004550907771]
                                         })
    data_dict.dataset_ids = _test_datasets
    return data_dict


def mock_ois_spot():
    data_dict = MarketDataResponseFrame({'date': [datetime.date(2019, 12, 6)],
                                         'assetId': ['MARFAGXDQRWM07Y2'],
                                         'location': ['NYC'],
                                         'rateType': ['Spot'],
                                         'startingDate': [datetime.date(2019, 12, 6)],
                                         'endingDate': [datetime.date(2019, 12, 7)],
                                         'meetingNumber': [-1],
                                         'valuationDate': [datetime.date(2019, 12, 6)],
                                         'meetingDate': [datetime.date(2019, 12, 6)],
                                         'value': [-0.00455]
                                         })
    data_dict.dataset_ids = _test_datasets
    return data_dict


def mock_esg(_cls, _q):
    d = {
        'esNumericScore': [2, 4, 6],
        "esNumericPercentile": [81.2, 75.4, 65.7],
        "esPolicyScore": [2, 4, 6],
        "esPolicyPercentile": [81.2, 75.4, 65.7],
        "esScore": [2, 4, 6],
        "esPercentile": [81.2, 75.4, 65.7],
        "gScore": [2, 4, 6],
        "gPercentile": [81.2, 75.4, 65.7],
        "esMomentumScore": [2, 4, 6],
        "esMomentumPercentile": [81.2, 75.4, 65.7],
        "gRegionalScore": [2, 4, 6],
        "gRegionalPercentile": [81.2, 75.4, 65.7],
        "esDisclosurePercentage": [49.2, 55.7, 98.4]
    }
    df = MarketDataResponseFrame(data=d, index=_index * 3)
    df.dataset_ids = _test_datasets
    return df


def test_skew():
    replace = Replacer()

    mock_spx = Index('MA890', AssetClass.Equity, 'SPX')
    replace('gs_quant.timeseries.measures.GsDataApi.get_market_data', mock_eq)
    actual = tm.skew(mock_spx, '1m', tm.SkewReference.DELTA, 25)
    assert_series_equal(pd.Series([2.0], index=_index, name='impliedVolatility'), pd.Series(actual))
    assert actual.dataset_ids == _test_datasets

    replace('gs_quant.timeseries.measures.GsDataApi.get_market_data', mock_eq_norm)
    actual = tm.skew(mock_spx, '1m', tm.SkewReference.NORMALIZED, 4)
    assert_series_equal(pd.Series([2.0], index=_index, name='impliedVolatility'), pd.Series(actual))
    assert actual.dataset_ids == _test_datasets

    replace('gs_quant.timeseries.measures.GsDataApi.get_market_data', mock_eq_spot)
    actual = tm.skew(mock_spx, '1m', tm.SkewReference.SPOT, 25)
    assert_series_equal(pd.Series([2.0], index=_index, name='impliedVolatility'), pd.Series(actual))
    assert actual.dataset_ids == _test_datasets

    mock = replace('gs_quant.timeseries.measures.GsDataApi.get_market_data', Mock())
    mock.return_value = mock_empty_market_data_response()
    actual = tm.skew(mock_spx, '1m', tm.SkewReference.SPOT, 25)
    assert actual.empty

    replace('gs_quant.timeseries.measures.GsDataApi.get_market_data', mock_inc)
    with pytest.raises(MqError):
        tm.skew(mock_spx, '1m', tm.SkewReference.DELTA, 25)
    replace.restore()

    with pytest.raises(MqError):
        tm.skew(mock_spx, '1m', None, 25)

    with pytest.raises(MqError):
        tm.skew(mock_spx, '1m', tm.SkewReference.SPOT, 25, real_time=True)


def test_skew_fx():
    replace = Replacer()
    cross = Cross('MAA0NE9QX2ABETG6', 'USD/EUR')
    xrefs = replace('gs_quant.timeseries.measures.GsAssetApi.get_asset_xrefs', Mock())
    xrefs.return_value = [GsTemporalXRef(dt.date(2019, 1, 1), dt.date(2952, 12, 31), XRef(bbid='EURUSD', ))]
    replace('gs_quant.markets.securities.SecurityMaster.get_asset', Mock()).return_value = cross
    replace('gs_quant.timeseries.measures.GsDataApi.get_market_data', mock_fx_delta)
    mock = cross

    actual = tm.skew(mock, '1m', tm.SkewReference.DELTA, 25)
    assert_series_equal(pd.Series([2.0], index=_index, name='impliedVolatility'), pd.Series(actual))
    assert actual.dataset_ids == _test_datasets
    with pytest.raises(MqError):
        tm.skew(mock, '1m', tm.SkewReference.DELTA, 25, real_time=True)
    with pytest.raises(MqError):
        tm.skew(mock, '1m', tm.SkewReference.SPOT, 25)
    with pytest.raises(MqError):
        tm.skew(mock, '1m', tm.SkewReference.FORWARD, 25)
    with pytest.raises(MqError):
        tm.skew(mock, '1m', tm.SkewReference.NORMALIZED, 25)
    with pytest.raises(MqError):
        tm.skew(mock, '1m', None, 25)

    replace.restore()


def test_vol():
    replace = Replacer()
    mock_spx = Index('MA890', AssetClass.Equity, 'SPX')
    replace('gs_quant.timeseries.measures.GsDataApi.get_market_data', mock_eq)
    actual = tm.implied_volatility(mock_spx, '1m', tm.VolReference.DELTA_CALL, 25)
    assert_series_equal(pd.Series([5, 1, 2], index=_index * 3, name='impliedVolatility'), pd.Series(actual))
    assert actual.dataset_ids == _test_datasets
    actual = tm.implied_volatility(mock_spx, '1m', tm.VolReference.DELTA_PUT, 75)
    assert_series_equal(pd.Series([5, 1, 2], index=_index * 3, name='impliedVolatility'), pd.Series(actual))
    assert actual.dataset_ids == _test_datasets
    with pytest.raises(MqError):
        tm.implied_volatility(mock_spx, '1m', tm.VolReference.DELTA_NEUTRAL)
    replace.restore()


def test_vol_fx():
    replace = Replacer()

    mock = Cross('MAA0NE9QX2ABETG6', 'USD/EUR')
    xrefs = replace('gs_quant.timeseries.measures.GsAssetApi.get_asset_xrefs', Mock())
    xrefs.return_value = [GsTemporalXRef(dt.date(2019, 1, 1), dt.date(2952, 12, 31), XRef(bbid='EURUSD', ))]
    replace('gs_quant.markets.securities.SecurityMaster.get_asset', Mock()).return_value = mock

    # for different delta strikes
    replace('gs_quant.timeseries.measures.GsDataApi.get_market_data', mock_fx)
    actual = tm.implied_volatility(mock, '1m', tm.VolReference.DELTA_CALL, 25)
    assert_series_equal(pd.Series([5, 1, 2], index=_index * 3, name='impliedVolatility'), pd.Series(actual))
    assert actual.dataset_ids == _test_datasets
    actual = tm.implied_volatility(mock, '1m', tm.VolReference.DELTA_PUT, 25)
    assert_series_equal(pd.Series([5, 1, 2], index=_index * 3, name='impliedVolatility'), pd.Series(actual))
    assert actual.dataset_ids == _test_datasets
    actual = tm.implied_volatility(mock, '1m', tm.VolReference.DELTA_NEUTRAL)
    assert_series_equal(pd.Series([5, 1, 2], index=_index * 3, name='impliedVolatility'), pd.Series(actual))
    assert actual.dataset_ids == _test_datasets
    actual = tm.implied_volatility(mock, '1m', tm.VolReference.FORWARD, 100)
    assert_series_equal(pd.Series([5, 1, 2], index=_index * 3, name='impliedVolatility'), pd.Series(actual))
    assert actual.dataset_ids == _test_datasets
    actual = tm.implied_volatility(mock, '1m', tm.VolReference.SPOT, 100)
    assert_series_equal(pd.Series([5, 1, 2], index=_index * 3, name='impliedVolatility'), pd.Series(actual))
    assert actual.dataset_ids == _test_datasets

    # NORMALIZED not supported
    with pytest.raises(MqError):
        tm.implied_volatility(mock, '1m', tm.VolReference.DELTA_CALL)
    with pytest.raises(MqError):
        tm.implied_volatility(mock, '1m', tm.VolReference.NORMALIZED, 25)
    with pytest.raises(MqError):
        tm.implied_volatility(mock, '1m', tm.VolReference.SPOT, 25)
    with pytest.raises(MqError):
        tm.implied_volatility(mock, '1m', tm.VolReference.FORWARD, 25)
    replace.restore()


def test_vol_forecast():
    replace = Replacer()
    mock = Cross('MAA0NE9QX2ABETG6', 'USD/EUR')
    xrefs = replace('gs_quant.timeseries.measures.GsAssetApi.get_asset_xrefs', Mock())
    xrefs.return_value = [GsTemporalXRef(dt.date(2019, 1, 1), dt.date(2952, 12, 31), XRef(bbid='EURUSD', ))]
    replace('gs_quant.markets.securities.SecurityMaster.get_asset', Mock()).return_value = mock
    replace('gs_quant.timeseries.measures.GsDataApi.get_market_data', mock_fx)

    actual = tm.forecast(mock, '1y')
    assert_series_equal(pd.Series([1.1, 1.1, 1.1], index=_index * 3, name='forecast'), pd.Series(actual))
    assert actual.dataset_ids == _test_datasets
    actual = tm.forecast(mock, '3m')
    assert_series_equal(pd.Series([1.1, 1.1, 1.1], index=_index * 3, name='forecast'), pd.Series(actual))
    assert actual.dataset_ids == _test_datasets
    with pytest.raises(NotImplementedError):
        tm.forecast(mock, '1y', real_time=True)
    replace.restore()


def test_vol_forecast_inverse():
    replace = Replacer()
    get_cross = replace('gs_quant.timeseries.measures.cross_to_usd_based_cross', Mock())
    get_cross.return_value = "MATGYV0J9MPX534Z"
    replace('gs_quant.timeseries.measures.GsDataApi.get_market_data', mock_fx)

    mock = Cross("MAYJPCVVF2RWXCES", 'USD/JPY')
    actual = tm.forecast(mock, '3m')
    assert_series_equal(pd.Series([1 / 1.1, 1 / 1.1, 1 / 1.1], index=_index * 3, name='forecast'), pd.Series(actual))
    assert actual.dataset_ids == _test_datasets
    replace.restore()


def test_vol_smile():
    replace = Replacer()
    mock_spx = Index('MA890', AssetClass.Equity, 'SPX')
    replace('gs_quant.timeseries.measures.GsDataApi.get_market_data', mock_eq)
    actual = tm.vol_smile(mock_spx, '1m', tm.VolSmileReference.FORWARD, '5d')
    assert_series_equal(pd.Series([5, 1, 2], index=[0.75, 0.25, 0.5]), pd.Series(actual))
    assert actual.dataset_ids == _test_datasets
    actual = tm.vol_smile(mock_spx, '1m', tm.VolSmileReference.SPOT, '5d')
    assert_series_equal(pd.Series([5, 1, 2], index=[0.75, 0.25, 0.5]), pd.Series(actual))
    assert actual.dataset_ids == _test_datasets

    market_mock = replace('gs_quant.timeseries.measures.GsDataApi.get_market_data', Mock())
    market_mock.return_value = mock_empty_market_data_response()
    actual = tm.vol_smile(mock_spx, '1m', tm.VolSmileReference.SPOT, '1d')
    assert actual.empty
    assert actual.dataset_ids == ()
    market_mock.assert_called_once()
    with pytest.raises(NotImplementedError):
        tm.vol_smile(mock_spx, '1m', tm.VolSmileReference.SPOT, '1d', real_time=True)
    replace.restore()


def test_impl_corr():
    replace = Replacer()
    mock_spx = Index('MA890', AssetClass.Equity, 'SPX')
    replace('gs_quant.timeseries.measures.GsDataApi.get_market_data', mock_eq)
    actual = tm.implied_correlation(mock_spx, '1m', tm.EdrDataReference.DELTA_CALL, 25)
    assert_series_equal(pd.Series([5, 1, 2], index=_index * 3, name='impliedCorrelation'), pd.Series(actual))
    assert actual.dataset_ids == _test_datasets
    actual = tm.implied_correlation(mock_spx, '1m', tm.EdrDataReference.DELTA_PUT, 75)
    assert_series_equal(pd.Series([5, 1, 2], index=_index * 3, name='impliedCorrelation'), pd.Series(actual))
    assert actual.dataset_ids == _test_datasets
    with pytest.raises(NotImplementedError):
        tm.implied_correlation(..., '1m', tm.EdrDataReference.DELTA_PUT, 75, real_time=True)
    replace.restore()


def test_cds_implied_vol():
    replace = Replacer()
    mock_cds = Index('MA890', AssetClass.Equity, 'CDS')
    replace('gs_quant.timeseries.measures.GsDataApi.get_market_data', mock_eq)
    actual = tm.cds_implied_volatility(mock_cds, '1m', '5y', tm.CdsVolReference.DELTA_CALL, 10)
    assert_series_equal(pd.Series([5, 1, 2], index=_index * 3, name='impliedVolatilityByDeltaStrike'),
                        pd.Series(actual))
    assert actual.dataset_ids == _test_datasets
    actual = tm.cds_implied_volatility(mock_cds, '1m', '5y', tm.CdsVolReference.FORWARD, 100)
    assert_series_equal(pd.Series([5, 1, 2], index=_index * 3, name='impliedVolatilityByDeltaStrike'),
                        pd.Series(actual))
    assert actual.dataset_ids == _test_datasets
    with pytest.raises(NotImplementedError):
        tm.cds_implied_volatility(..., '1m', '5y', tm.CdsVolReference.DELTA_PUT, 75, real_time=True)
    replace.restore()


def test_avg_impl_vol():
    replace = Replacer()
    mock_spx = Index('MA890', AssetClass.Equity, 'SPX')
    replace('gs_quant.timeseries.measures.GsDataApi.get_market_data', mock_eq)
    actual = tm.average_implied_volatility(mock_spx, '1m', tm.EdrDataReference.DELTA_CALL, 25)
    assert_series_equal(pd.Series([5, 1, 2], index=_index * 3, name='averageImpliedVolatility'), pd.Series(actual))
    assert actual.dataset_ids == _test_datasets
    actual = tm.average_implied_volatility(mock_spx, '1m', tm.EdrDataReference.DELTA_PUT, 75)
    assert_series_equal(pd.Series([5, 1, 2], index=_index * 3, name='averageImpliedVolatility'), pd.Series(actual))
    assert actual.dataset_ids == _test_datasets
    with pytest.raises(NotImplementedError):
        tm.average_implied_volatility(..., '1m', tm.EdrDataReference.DELTA_PUT, 75, real_time=True)
    replace.restore()


def test_avg_impl_var():
    replace = Replacer()
    mock_spx = Index('MA890', AssetClass.Equity, 'SPX')
    replace('gs_quant.timeseries.measures.GsDataApi.get_market_data', mock_eq)
    actual = tm.average_implied_variance(mock_spx, '1m', tm.EdrDataReference.DELTA_CALL, 25)
    assert_series_equal(pd.Series([5, 1, 2], index=_index * 3, name='averageImpliedVariance'), pd.Series(actual))
    actual = tm.average_implied_variance(mock_spx, '1m', tm.EdrDataReference.DELTA_PUT, 75)
    assert actual.dataset_ids == _test_datasets
    assert_series_equal(pd.Series([5, 1, 2], index=_index * 3, name='averageImpliedVariance'), pd.Series(actual))
    assert actual.dataset_ids == _test_datasets
    with pytest.raises(NotImplementedError):
        tm.average_implied_variance(..., '1m', tm.EdrDataReference.DELTA_PUT, 75, real_time=True)
    replace.restore()


def test_basis_swap_spread(mocker):
    replace = Replacer()
    args = dict(swap_tenor='10y', spread_benchmark_type=None, spread_tenor=None,
                reference_benchmark_type=None, reference_tenor=None, forward_tenor='0b', real_time=False)

    mock_nok = Currency('MA891', 'NOK')
    xrefs = replace('gs_quant.timeseries.measures.Asset.get_identifier', Mock())
    xrefs.return_value = 'NOK'
    args['asset'] = mock_nok
    with pytest.raises(NotImplementedError):
        tm_rates.basis_swap_spread(**args)

    mock_usd = Currency('MAZ7RWC904JYHYPS', 'USD')
    args['asset'] = mock_usd
    xrefs = replace('gs_quant.timeseries.measures.Asset.get_identifier', Mock())
    xrefs.return_value = 'USD'
    with pytest.raises(NotImplementedError):
        tm_rates.basis_swap_spread(..., '1y', real_time=True)

    args['swap_tenor'] = '5yr'
    with pytest.raises(MqValueError):
        tm_rates.basis_swap_spread(**args)
    args['swap_tenor'] = '6y'

    args['spread_tenor'] = '5yr'
    with pytest.raises(MqValueError):
        tm_rates.basis_swap_spread(**args)
    args['spread_tenor'] = '3m'

    args['reference_tenor'] = '5yr'
    with pytest.raises(MqValueError):
        tm_rates.basis_swap_spread(**args)
    args['reference_tenor'] = '6m'

    args['forward_tenor'] = '5yr'
    with pytest.raises(MqValueError):
        tm_rates.basis_swap_spread(**args)
    args['forward_tenor'] = None

    args['spread_benchmark_type'] = BenchmarkType.STIBOR
    with pytest.raises(MqValueError):
        tm_rates.basis_swap_spread(**args)
    args['spread_benchmark_type'] = BenchmarkType.LIBOR

    args['reference_benchmark_type'] = BenchmarkType.STIBOR
    with pytest.raises(MqValueError):
        tm_rates.basis_swap_spread(**args)
    args['reference_benchmark_type'] = BenchmarkType.LIBOR

    xrefs = replace('gs_quant.timeseries.measures.Asset.get_identifier', Mock())
    xrefs.return_value = 'USD'
    identifiers = replace('gs_quant.timeseries.measures_rates._convert_asset_for_mdapi_swap_rates', Mock())
    identifiers.return_value = {'MAQB1PGEJFCET3GG'}
    mocker.patch.object(GsDataApi, 'get_market_data', return_value=mock_curr(None, None))
    actual = tm_rates.basis_swap_spread(**args)
    expected = tm.ExtendedSeries([1, 2, 3], index=_index * 3, name='basisSwapRate')
    expected.dataset_ids = _test_datasets
    assert_series_equal(expected, actual)
    assert actual.dataset_ids == expected.dataset_ids
    replace.restore()


def test_swap_rate(mocker):
    replace = Replacer()
    args = dict(swap_tenor='10y', benchmark_type=None, floating_rate_tenor=None, forward_tenor='0b', real_time=False)

    mock_nok = Currency('MA891', 'NOK')
    xrefs = replace('gs_quant.timeseries.measures.Asset.get_identifier', Mock())
    xrefs.return_value = 'NOK'
    args['asset'] = mock_nok
    with pytest.raises(NotImplementedError):
        tm_rates.swap_rate(**args)

    mock_usd = Currency('MAZ7RWC904JYHYPS', 'USD')
    args['asset'] = mock_usd
    xrefs = replace('gs_quant.timeseries.measures.Asset.get_identifier', Mock())
    xrefs.return_value = 'USD'
    with pytest.raises(NotImplementedError):
        tm_rates.swap_rate(..., '1y', real_time=True)

    args['swap_tenor'] = '5yr'
    with pytest.raises(MqValueError):
        tm_rates.swap_rate(**args)
    args['swap_tenor'] = '10y'

    args['floating_rate_tenor'] = '5yr'
    with pytest.raises(MqValueError):
        tm_rates.swap_rate(**args)
    args['floating_rate_tenor'] = '3m'

    args['forward_tenor'] = '5yr'
    with pytest.raises(MqValueError):
        tm_rates.swap_rate(**args)
    args['forward_tenor'] = None

    args['benchmark_type'] = BenchmarkType.STIBOR
    with pytest.raises(MqValueError):
        tm_rates.swap_rate(**args)
    args['benchmark_type'] = BenchmarkType.LIBOR

    xrefs = replace('gs_quant.timeseries.measures.Asset.get_identifier', Mock())
    xrefs.return_value = 'USD'
    identifiers = replace('gs_quant.timeseries.measures_rates._convert_asset_for_mdapi_swap_rates', Mock())
    identifiers.return_value = {'MAZ7RWC904JYHYPS'}
    mocker.patch.object(GsDataApi, 'get_market_data', return_value=mock_curr(None, None))
    actual = tm_rates.swap_rate(**args)
    expected = tm.ExtendedSeries([1, 2, 3], index=_index * 3, name='swapRate')
    expected.dataset_ids = _test_datasets
    assert_series_equal(expected, actual)
    assert actual.dataset_ids == _test_datasets
    replace.restore()


def test_swap_annuity(mocker):
    replace = Replacer()
    args = dict(swap_tenor='10y', benchmark_type=None, floating_rate_tenor=None, forward_tenor='0b', real_time=False)

    mock_nok = Currency('MA891', 'NOK')
    xrefs = replace('gs_quant.timeseries.measures.Asset.get_identifier', Mock())
    xrefs.return_value = 'NOK'
    args['asset'] = mock_nok
    with pytest.raises(NotImplementedError):
        tm_rates.swap_annuity(**args)

    mock_usd = Currency('MAZ7RWC904JYHYPS', 'USD')
    args['asset'] = mock_usd
    xrefs = replace('gs_quant.timeseries.measures.Asset.get_identifier', Mock())
    xrefs.return_value = 'USD'
    with pytest.raises(NotImplementedError):
        tm_rates.swap_annuity(..., '1y', real_time=True)

    args['swap_tenor'] = '5yr'
    with pytest.raises(MqValueError):
        tm_rates.swap_annuity(**args)
    args['swap_tenor'] = '10y'

    args['floating_rate_tenor'] = '5yr'
    with pytest.raises(MqValueError):
        tm_rates.swap_annuity(**args)
    args['floating_rate_tenor'] = '1y'

    args['forward_tenor'] = '5yr'
    with pytest.raises(MqValueError):
        tm_rates.swap_annuity(**args)
    args['forward_tenor'] = None

    args['benchmark_type'] = BenchmarkType.STIBOR
    with pytest.raises(MqValueError):
        tm_rates.swap_annuity(**args)
    args['benchmark_type'] = BenchmarkType.SOFR

    xrefs = replace('gs_quant.timeseries.measures.Asset.get_identifier', Mock())
    xrefs.return_value = 'USD'
    identifiers = replace('gs_quant.timeseries.measures_rates._convert_asset_for_mdapi_swap_rates', Mock())
    identifiers.return_value = {'MAZ7RWC904JYHYPS'}
    mocker.patch.object(GsDataApi, 'get_market_data', return_value=mock_curr(None, None))
    actual = tm_rates.swap_annuity(**args)
    expected = abs(tm.ExtendedSeries([1.0, 2.0, 3.0], index=_index * 3, name='swapAnnuity') * 1e4 / 1e8)
    expected.dataset_ids = _test_datasets
    assert_series_equal(expected, actual)
    assert actual.dataset_ids == expected.dataset_ids
    replace.restore()


def test_swap_term_structure(mocker):
    replace = Replacer()
    args = dict(benchmark_type=None, floating_rate_tenor=None, forward_tenor='0b', real_time=False)

    mock_nok = Currency('MA891', 'NOK')
    xrefs = replace('gs_quant.timeseries.measures.Asset.get_identifier', Mock())
    xrefs.return_value = 'NOK'
    args['asset'] = mock_nok
    with pytest.raises(NotImplementedError):
        tm_rates.swap_term_structure(**args)

    mock_usd = Currency('MAZ7RWC904JYHYPS', 'USD')
    args['asset'] = mock_usd
    xrefs = replace('gs_quant.timeseries.measures.Asset.get_identifier', Mock())
    xrefs.return_value = 'USD'
    with pytest.raises(NotImplementedError):
        tm_rates.swap_term_structure(..., '1y', real_time=True)

    args['floating_rate_tenor'] = '5yr'
    with pytest.raises(MqValueError):
        tm_rates.swap_term_structure(**args)
    args['floating_rate_tenor'] = '3m'

    args['forward_tenor'] = '5yr'
    with pytest.raises(MqValueError):
        tm_rates.swap_term_structure(**args)
    args['forward_tenor'] = None

    args['benchmark_type'] = BenchmarkType.STIBOR
    with pytest.raises(MqValueError):
        tm_rates.swap_term_structure(**args)
    args['benchmark_type'] = BenchmarkType.LIBOR

    bd_mock = replace('gs_quant.data.dataset.Dataset.get_data', Mock())
    bd_mock.return_value = pd.DataFrame(data=dict(date="2020-04-10", exchange="NYC", description="Good Friday"),
                                        index=[pd.Timestamp('2020-04-10')])
    args['pricing_date'] = datetime.date(2020, 4, 10)
    with pytest.raises(MqValueError):
        tm_rates.swap_term_structure(**args)
    args['pricing_date'] = None

    xrefs = replace('gs_quant.timeseries.measures.Asset.get_identifier', Mock())
    xrefs.return_value = 'USD'
    identifiers_empty = replace('gs_quant.timeseries.measures.GsAssetApi.get_many_assets', Mock())
    identifiers_empty.return_value = {}
    with pytest.raises(MqValueError):
        tm_rates.swap_term_structure(**args)

    identifiers = replace('gs_quant.timeseries.measures.GsAssetApi.get_many_assets', Mock())
    mock_asset = Currency('USD', name='USD')
    mock_asset.id = 'MAEMPCXQG3T716EX'
    mock_asset.exchange = 'OTC'
    identifiers.return_value = [mock_asset]

    d = {
        'terminationTenor': ['1y', '2y', '3y', '4y'], 'swapRate': [1, 2, 3, 4],
        'assetId': ['MAEMPCXQG3T716EX', 'MAFRSWPAF5QPNTP2', 'MA88BXZ3TCTXTFW1', 'MAC4KAG9B9ZAZHFT']
    }

    pricing_date_mock = replace('gs_quant.timeseries.measures_rates._range_from_pricing_date', Mock())
    pricing_date_mock.return_value = [datetime.date(2019, 1, 1), datetime.date(2019, 1, 1)]
    bd_mock.return_value = pd.DataFrame()
    market_data_mock = replace('gs_quant.timeseries.measures_rates._market_data_timed', Mock())

    market_data_mock.return_value = pd.DataFrame()
    df = pd.DataFrame(data=d, index=_index * 4)
    assert tm_rates.swap_term_structure(**args).empty

    market_data_mock.return_value = df
    with DataContext('2019-01-01', '2025-01-01'):
        actual = tm_rates.swap_term_structure(**args)
    actual.dataset_ids = _test_datasets
    expected = tm.ExtendedSeries([1, 2, 3, 4], index=pd.to_datetime(['2020-01-01', '2021-01-01', '2021-12-31',
                                                                     '2022-12-30']))
    expected.dataset_ids = _test_datasets
    assert_series_equal(expected, actual, check_names=False)
    assert actual.dataset_ids == expected.dataset_ids
    replace.restore()


def test_basis_swap_term_structure(mocker):
    replace = Replacer()
    range_mock = replace('gs_quant.timeseries.measures_rates._range_from_pricing_date', Mock())
    range_mock.return_value = [datetime.date(2019, 1, 1), datetime.date(2019, 1, 1)]

    args = dict(spread_benchmark_type=None, spread_tenor=None,
                reference_benchmark_type=None, reference_tenor=None, forward_tenor='0b', real_time=False)

    mock_nok = Currency('MA891', 'NOK')
    xrefs = replace('gs_quant.timeseries.measures.Asset.get_identifier', Mock())
    xrefs.return_value = 'NOK'
    args['asset'] = mock_nok
    with pytest.raises(NotImplementedError):
        tm_rates.basis_swap_term_structure(**args)

    mock_usd = Currency('MAZ7RWC904JYHYPS', 'USD')
    args['asset'] = mock_usd
    xrefs = replace('gs_quant.timeseries.measures.Asset.get_identifier', Mock())
    xrefs.return_value = 'USD'
    with pytest.raises(NotImplementedError):
        tm_rates.basis_swap_term_structure(..., '1y', real_time=True)

    args['spread_tenor'] = '5yr'
    with pytest.raises(MqValueError):
        tm_rates.basis_swap_term_structure(**args)
    args['spread_tenor'] = '3m'

    args['reference_tenor'] = '5yr'
    with pytest.raises(MqValueError):
        tm_rates.basis_swap_term_structure(**args)
    args['reference_tenor'] = '6m'

    args['forward_tenor'] = '5yr'
    with pytest.raises(MqValueError):
        tm_rates.basis_swap_term_structure(**args)
    args['forward_tenor'] = None

    args['spread_benchmark_type'] = BenchmarkType.STIBOR
    with pytest.raises(MqValueError):
        tm_rates.basis_swap_term_structure(**args)
    args['spread_benchmark_type'] = BenchmarkType.LIBOR

    args['reference_benchmark_type'] = BenchmarkType.STIBOR
    with pytest.raises(MqValueError):
        tm_rates.basis_swap_term_structure(**args)
    args['reference_benchmark_type'] = BenchmarkType.LIBOR

    bd_mock = replace('gs_quant.data.dataset.Dataset.get_data', Mock())
    bd_mock.return_value = pd.DataFrame(data=dict(date="2020-04-10", exchange="NYC", description="Good Friday"),
                                        index=[pd.Timestamp('2020-04-10')])
    args['pricing_date'] = datetime.date(2020, 4, 10)
    with pytest.raises(MqValueError):
        tm_rates.basis_swap_term_structure(**args)
    args['pricing_date'] = None

    xrefs = replace('gs_quant.timeseries.measures.Asset.get_identifier', Mock())
    xrefs.return_value = 'USD'
    identifiers_empty = replace('gs_quant.timeseries.measures.GsAssetApi.get_many_assets', Mock())
    identifiers_empty.return_value = {}
    with pytest.raises(MqValueError):
        tm_rates.basis_swap_term_structure(**args)

    identifiers = replace('gs_quant.timeseries.measures.GsAssetApi.get_many_assets', Mock())
    mock_asset = Currency('USD', name='USD')
    mock_asset.id = 'MAEMPCXQG3T716EX'
    mock_asset.exchange = 'OTC'
    identifiers.return_value = [mock_asset]

    d = {
        'terminationTenor': ['1y', '2y', '3y', '4y'], 'basisSwapRate': [1, 2, 3, 4],
        'assetId': ['MAEMPCXQG3T716EX', 'MAFRSWPAF5QPNTP2', 'MA88BXZ3TCTXTFW1', 'MAC4KAG9B9ZAZHFT']
    }

    pricing_date_mock = replace('gs_quant.timeseries.measures_rates._range_from_pricing_date', Mock())
    pricing_date_mock.return_value = [datetime.date(2019, 1, 1), datetime.date(2019, 1, 1)]
    bd_mock.return_value = pd.DataFrame()
    market_data_mock = replace('gs_quant.timeseries.measures_rates._market_data_timed', Mock())

    market_data_mock.return_value = pd.DataFrame()
    assert tm_rates.basis_swap_term_structure(**args).empty

    df = pd.DataFrame(data=d, index=_index * 4)
    market_data_mock.return_value = df
    with DataContext('2019-01-01', '2025-01-01'):
        actual = tm_rates.basis_swap_term_structure(**args)
    actual.dataset_ids = _test_datasets
    expected = tm.ExtendedSeries([1, 2, 3, 4], index=pd.to_datetime(['2020-01-01', '2021-01-01', '2021-12-31',
                                                                     '2022-12-30']))
    expected.dataset_ids = _test_datasets
    assert_series_equal(expected, actual, check_names=False)
    assert actual.dataset_ids == expected.dataset_ids
    replace.restore()


def test_swaption_vol():
    replace = Replacer()
    mock_usd = Currency('MA890', 'USD')
    xrefs = replace('gs_quant.timeseries.measures.GsAssetApi.get_asset_xrefs', Mock())
    xrefs.return_value = [GsTemporalXRef(dt.date(2019, 1, 1), dt.date(2952, 12, 31), XRef(bbid='USD', ))]
    identifiers = replace('gs_quant.timeseries.measures.GsAssetApi.map_identifiers', Mock())
    identifiers.return_value = {'USD-LIBOR-BBA': 'MA123'}
    replace('gs_quant.timeseries.measures.GsDataApi.get_market_data', mock_curr)
    actual = tm.swaption_vol(mock_usd, '3m', '1y', 0)
    assert_series_equal(pd.Series([1, 2, 3], index=_index * 3, name='swaptionVol'), pd.Series(actual))
    assert actual.dataset_ids == _test_datasets
    actual = tm.swaption_vol(mock_usd, '3m', '1y', 50)
    assert_series_equal(pd.Series([1, 2, 3], index=_index * 3, name='swaptionVol'), pd.Series(actual))
    assert actual.dataset_ids == _test_datasets
    actual = tm.swaption_vol(mock_usd, '3m', '1y', -50)
    assert_series_equal(pd.Series([1, 2, 3], index=_index * 3, name='swaptionVol'), pd.Series(actual))
    assert actual.dataset_ids == _test_datasets
    with pytest.raises(NotImplementedError):
        tm.swaption_vol(..., '3m', '1y', 50, real_time=True)
    replace.restore()


def test_swaption_vol_term():
    with pytest.raises(NotImplementedError):
        tm.swaption_vol_term(..., '1y', 0, real_time=True)

    replace = Replacer()
    replace('gs_quant.timeseries.measures.convert_asset_for_rates_data_set', Mock()).return_value = 'MA31BT4WD1SVNYA0'

    d = {
        'expiry': ['1m', '6m', '1y'],
        'swaptionVol': [1, 2, 3]
    }
    df = MarketDataResponseFrame(data=d, index=_index * 3)
    df.dataset_ids = _test_datasets
    market_data_mock = replace('gs_quant.timeseries.measures._market_data_timed', Mock())
    market_data_mock.return_value = df

    with DataContext('2019-01-01', '2025-01-01'):
        actual = tm.swaption_vol_term(Currency('MA123', 'EUR'), '5y', 0)
    expected = pd.Series([1, 2, 3], index=pd.to_datetime(['2019-02-01', '2019-07-01', '2020-01-01']))
    assert_series_equal(expected, pd.Series(actual), check_names=False)
    assert actual.dataset_ids == _test_datasets

    market_data_mock.return_value = mock_empty_market_data_response()
    actual = tm.swaption_vol_term(Currency('MA123', 'EUR'), '5y', 0)
    assert actual.empty
    assert actual.dataset_ids == ()
    replace.restore()


def test_swaption_atm_fwd_rate():
    replace = Replacer()
    mock_usd = Currency('MA890', 'USD')
    xrefs = replace('gs_quant.timeseries.measures.GsAssetApi.get_asset_xrefs', Mock())
    xrefs.return_value = [GsTemporalXRef(dt.date(2019, 1, 1), dt.date(2952, 12, 31), XRef(bbid='USD', ))]
    identifiers = replace('gs_quant.timeseries.measures.GsAssetApi.map_identifiers', Mock())
    identifiers.return_value = {'USD-LIBOR-BBA': 'MA123'}
    replace('gs_quant.timeseries.measures.GsDataApi.get_market_data', mock_curr)
    actual = tm.swaption_atm_fwd_rate(mock_usd, '3m', '1y')
    assert_series_equal(pd.Series([1, 2, 3], index=_index * 3, name='atmFwdRate'), pd.Series(actual))
    assert actual.dataset_ids == _test_datasets
    with pytest.raises(NotImplementedError):
        tm.swaption_atm_fwd_rate(..., '3m', '1y', real_time=True)
    replace.restore()


def test_midcurve_vol():
    replace = Replacer()
    mock_usd = Currency('MA890', 'USD')
    xrefs = replace('gs_quant.timeseries.measures.GsAssetApi.get_asset_xrefs', Mock())
    xrefs.return_value = [GsTemporalXRef(dt.date(2019, 1, 1), dt.date(2952, 12, 31), XRef(bbid='USD', ))]
    identifiers = replace('gs_quant.timeseries.measures.GsAssetApi.map_identifiers', Mock())
    identifiers.return_value = {'USD-LIBOR-BBA': 'MA123'}
    replace('gs_quant.timeseries.measures.GsDataApi.get_market_data', mock_curr)
    actual = tm.midcurve_vol(mock_usd, '3m', '1y', '1y', 50)
    assert_series_equal(pd.Series([1, 2, 3], index=_index * 3, name='midcurveVol'), pd.Series(actual))
    assert actual.dataset_ids == _test_datasets
    with pytest.raises(NotImplementedError):
        tm.midcurve_vol(..., '3m', '1y', '1y', 50, real_time=True)
    replace.restore()


def test_midcurve_atm_fwd_rate():
    replace = Replacer()
    mock_usd = Currency('MA890', 'USD')
    xrefs = replace('gs_quant.timeseries.measures.GsAssetApi.get_asset_xrefs', Mock())
    xrefs.return_value = [GsTemporalXRef(dt.date(2019, 1, 1), dt.date(2952, 12, 31), XRef(bbid='USD', ))]
    identifiers = replace('gs_quant.timeseries.measures.GsAssetApi.map_identifiers', Mock())
    identifiers.return_value = {'USD-LIBOR-BBA': 'MA123'}
    replace('gs_quant.timeseries.measures.GsDataApi.get_market_data', mock_curr)
    actual = tm.midcurve_atm_fwd_rate(mock_usd, '3m', '1y', '1y')
    assert_series_equal(pd.Series([1, 2, 3], index=_index * 3, name='midcurveAtmFwdRate'), pd.Series(actual))
    assert actual.dataset_ids == _test_datasets
    with pytest.raises(NotImplementedError):
        tm.midcurve_atm_fwd_rate(..., '3m', '1y', '1y', real_time=True)
    replace.restore()


def test_cap_floor_vol():
    replace = Replacer()
    mock_usd = Currency('MA890', 'USD')
    xrefs = replace('gs_quant.timeseries.measures.GsAssetApi.get_asset_xrefs', Mock())
    xrefs.return_value = [GsTemporalXRef(dt.date(2019, 1, 1), dt.date(2952, 12, 31), XRef(bbid='USD', ))]
    identifiers = replace('gs_quant.timeseries.measures.GsAssetApi.map_identifiers', Mock())
    identifiers.return_value = {'USD-LIBOR-BBA': 'MA123'}
    replace('gs_quant.timeseries.measures.GsDataApi.get_market_data', mock_curr)
    actual = tm.cap_floor_vol(mock_usd, '5y', 50)
    assert_series_equal(pd.Series([1, 2, 3], index=_index * 3, name='capFloorVol'), pd.Series(actual))
    assert actual.dataset_ids == _test_datasets
    with pytest.raises(NotImplementedError):
        tm.cap_floor_vol(..., '5y', 50, real_time=True)
    replace.restore()


def test_cap_floor_atm_fwd_rate():
    replace = Replacer()
    mock_usd = Currency('MA890', 'USD')
    xrefs = replace('gs_quant.timeseries.measures.GsAssetApi.get_asset_xrefs', Mock())
    xrefs.return_value = [GsTemporalXRef(dt.date(2019, 1, 1), dt.date(2952, 12, 31), XRef(bbid='USD', ))]
    identifiers = replace('gs_quant.timeseries.measures.GsAssetApi.map_identifiers', Mock())
    identifiers.return_value = {'USD-LIBOR-BBA': 'MA123'}
    replace('gs_quant.timeseries.measures.GsDataApi.get_market_data', mock_curr)
    actual = tm.cap_floor_atm_fwd_rate(mock_usd, '5y')
    assert_series_equal(pd.Series([1, 2, 3], index=_index * 3, name='capFloorAtmFwdRate'), pd.Series(actual))
    assert actual.dataset_ids == _test_datasets
    with pytest.raises(NotImplementedError):
        tm.cap_floor_atm_fwd_rate(..., '5y', real_time=True)
    replace.restore()


def test_spread_option_vol():
    replace = Replacer()
    mock_usd = Currency('MA890', 'USD')
    xrefs = replace('gs_quant.timeseries.measures.GsAssetApi.get_asset_xrefs', Mock())
    xrefs.return_value = [GsTemporalXRef(dt.date(2019, 1, 1), dt.date(2952, 12, 31), XRef(bbid='USD', ))]
    identifiers = replace('gs_quant.timeseries.measures.GsAssetApi.map_identifiers', Mock())
    identifiers.return_value = {'USD-LIBOR-BBA': 'MA123'}
    replace('gs_quant.timeseries.measures.GsDataApi.get_market_data', mock_curr)
    actual = tm.spread_option_vol(mock_usd, '3m', '10y', '5y', 50)
    assert_series_equal(pd.Series([1, 2, 3], index=_index * 3, name='spreadOptionVol'), pd.Series(actual))
    assert actual.dataset_ids == _test_datasets
    with pytest.raises(NotImplementedError):
        tm.spread_option_vol(..., '3m', '10y', '5y', 50, real_time=True)
    replace.restore()


def test_spread_option_atm_fwd_rate():
    replace = Replacer()
    mock_usd = Currency('MA890', 'USD')
    xrefs = replace('gs_quant.timeseries.measures.GsAssetApi.get_asset_xrefs', Mock())
    xrefs.return_value = [GsTemporalXRef(dt.date(2019, 1, 1), dt.date(2952, 12, 31), XRef(bbid='USD', ))]
    identifiers = replace('gs_quant.timeseries.measures.GsAssetApi.map_identifiers', Mock())
    identifiers.return_value = {'USD-LIBOR-BBA': 'MA123'}
    replace('gs_quant.timeseries.measures.GsDataApi.get_market_data', mock_curr)
    actual = tm.spread_option_atm_fwd_rate(mock_usd, '3m', '10y', '5y')
    assert_series_equal(pd.Series([1, 2, 3], index=_index * 3, name='spreadOptionAtmFwdRate'), pd.Series(actual))
    assert actual.dataset_ids == _test_datasets
    with pytest.raises(NotImplementedError):
        tm.spread_option_atm_fwd_rate(..., '3m', '10y', '5y', real_time=True)
    replace.restore()


def test_zc_inflation_swap_rate():
    replace = Replacer()
    mock_gbp = Currency('MA890', 'GBP')
    xrefs = replace('gs_quant.timeseries.measures.GsAssetApi.get_asset_xrefs', Mock())
    xrefs.return_value = [GsTemporalXRef(dt.date(2019, 1, 1), dt.date(2952, 12, 31), XRef(bbid='GBP', ))]
    identifiers = replace('gs_quant.timeseries.measures.GsAssetApi.map_identifiers', Mock())
    identifiers.return_value = {'CPI-UKRPI': 'MA123'}
    replace('gs_quant.timeseries.measures.GsDataApi.get_market_data', mock_curr)
    actual = tm.zc_inflation_swap_rate(mock_gbp, '1y')
    assert_series_equal(pd.Series([1, 2, 3], index=_index * 3, name='inflationSwapRate'), pd.Series(actual))
    assert actual.dataset_ids == _test_datasets
    with pytest.raises(NotImplementedError):
        tm.zc_inflation_swap_rate(..., '1y', real_time=True)
    replace.restore()


def test_basis():
    replace = Replacer()
    mock_jpyusd = Cross('MA890', 'USD/JPY')
    xrefs = replace('gs_quant.timeseries.measures.GsAssetApi.get_asset_xrefs', Mock())
    xrefs.return_value = [GsTemporalXRef(dt.date(2019, 1, 1), dt.date(2952, 12, 31), XRef(bbid='JPYUSD', ))]
    identifiers = replace('gs_quant.timeseries.measures.GsAssetApi.map_identifiers', Mock())
    identifiers.return_value = {'USD-3m/JPY-3m': 'MA123'}
    replace('gs_quant.timeseries.measures.GsDataApi.get_market_data', mock_cross)
    actual = tm.basis(mock_jpyusd, '1y')
    assert_series_equal(pd.Series([1, 2, 3], index=_index * 3, name='basis'), pd.Series(actual))
    assert actual.dataset_ids == _test_datasets
    with pytest.raises(NotImplementedError):
        tm.basis(..., '1y', real_time=True)
    replace.restore()


def test_td():
    cases = {'3d': pd.DateOffset(days=3), '9w': pd.DateOffset(weeks=9), '2m': pd.DateOffset(months=2),
             '10y': pd.DateOffset(years=10)}
    for k, v in cases.items():
        actual = tm._to_offset(k)
        assert v == actual, f'expected {v}, got actual {actual}'

    with pytest.raises(ValueError):
        tm._to_offset('5z')


def test_pricing_range():
    import datetime

    given = datetime.date(2019, 4, 20)
    s, e = tm._range_from_pricing_date('NYSE', given)
    assert s == e == given

    class MockDate(datetime.date):
        @classmethod
        def today(cls):
            return cls(2019, 5, 25)

    # mock
    replace = Replacer()
    cbd = replace('gs_quant.timeseries.measures._get_custom_bd', Mock())
    cbd.return_value = pd.tseries.offsets.BusinessDay()
    today = replace('gs_quant.timeseries.measures.pd.Timestamp.today', Mock())
    today.return_value = pd.Timestamp(2019, 5, 25)
    gold = datetime.date
    datetime.date = MockDate

    # cases
    s, e = tm._range_from_pricing_date('ANY')
    assert s == pd.Timestamp(2019, 5, 24)
    assert e == pd.Timestamp(2019, 5, 24)

    s, e = tm._range_from_pricing_date('ANY', '3m')
    assert s == pd.Timestamp(2019, 2, 22)
    assert e == pd.Timestamp(2019, 2, 24)

    s, e = tm._range_from_pricing_date('ANY', '3b')
    assert s == e == pd.Timestamp(2019, 5, 22)

    # restore
    datetime.date = gold
    replace.restore()


def test_var_swap_tenors():
    session = GsSession.get(Environment.DEV, token='faux')

    replace = Replacer()
    get_mock = replace('gs_quant.session.GsSession._get', Mock())
    get_mock.return_value = {
        'data': [
            {
                'dataField': 'varSwap',
                'filteredFields': [
                    {
                        'field': 'tenor',
                        'values': ['abc', 'xyc']
                    }
                ]
            }
        ]
    }

    with session:
        actual = tm._var_swap_tenors(Index('MAXXX', AssetClass.Equity, 'XXX'))
    assert actual == ['abc', 'xyc']

    get_mock.return_value = {
        'data': []
    }
    with pytest.raises(MqError):
        with session:
            tm._var_swap_tenors(Index('MAXXX', AssetClass.Equity, 'XXX'))
    replace.restore()


def test_tenor_to_month():
    with pytest.raises(MqError):
        tm._tenor_to_month('1d')
    with pytest.raises(MqError):
        tm._tenor_to_month('2w')
    assert tm._tenor_to_month('3m') == 3
    assert tm._tenor_to_month('4y') == 48


def test_month_to_tenor():
    assert tm._month_to_tenor(36) == '3y'
    assert tm._month_to_tenor(18) == '18m'


def test_var_swap():
    idx = pd.date_range(start="2019-01-01", periods=4, freq="D")
    data = {
        'varSwap': [1, 2, 3, 4]
    }
    out = MarketDataResponseFrame(data=data, index=idx)
    out.dataset_ids = _test_datasets

    replace = Replacer()
    market_mock = replace('gs_quant.timeseries.measures.GsDataApi.get_market_data', Mock())
    market_mock.return_value = out

    expected = pd.Series([1, 2, 3, 4], name='varSwap', index=idx)
    actual = tm.var_swap(Index('MA123', AssetClass.Equity, '123'), '1m')
    assert_series_equal(expected, pd.Series(actual))
    assert actual.dataset_ids == _test_datasets
    market_mock.assert_called_once()

    market_mock.reset_mock()
    market_mock.return_value = mock_empty_market_data_response()
    actual = tm.var_swap(Index('MA123', AssetClass.Equity, '123'), '1m')
    assert actual.empty
    replace.restore()


def test_var_swap_fwd():
    # bad input
    with pytest.raises(MqError):
        tm.var_swap(Index('MA123', AssetClass.Equity, '123'), '1m', 500)

    # regular
    idx = pd.date_range(start="2019-01-01", periods=4, freq="D")
    d1 = {
        'varSwap': [1, 2, 3, 4],
        'tenor': ['1y'] * 4
    }
    d2 = {
        'varSwap': [1.5, 2.5, 3.5, 4.5],
        'tenor': ['13m'] * 4
    }
    df1 = MarketDataResponseFrame(data=d1, index=idx)
    df2 = MarketDataResponseFrame(data=d2, index=idx)
    out = pd.concat([df1, df2])
    out.dataset_ids = _test_datasets

    replace = Replacer()
    market_mock = replace('gs_quant.timeseries.measures.GsDataApi.get_market_data', Mock())
    market_mock.return_value = out

    tenors_mock = replace('gs_quant.timeseries.measures._var_swap_tenors', Mock())
    tenors_mock.return_value = ['1m', '1y', '13m']

    expected = pd.Series([7.5, 8.5, 9.5, 10.5], name='varSwap', index=idx)
    actual = tm.var_swap(Index('MA123', AssetClass.Equity, '123'), '1m', '1y')
    assert_series_equal(expected, pd.Series(actual))
    assert actual.dataset_ids == _test_datasets
    market_mock.assert_called_once()

    # no data
    market_mock.return_value = mock_empty_market_data_response()
    actual = tm.var_swap(Index('MA123', AssetClass.Equity, '123'), '1m', '1y')
    assert actual.empty
    assert actual.dataset_ids == ()

    # no data for a tenor
    out = MarketDataResponseFrame(data=d1, index=idx)
    out.dataset_ids = _test_datasets
    market_mock.return_value = out
    actual = tm.var_swap(Index('MA123', AssetClass.Equity, '123'), '1m', '1y')
    assert actual.empty
    assert actual.dataset_ids == ()

    # no such tenors
    tenors_mock.return_value = []
    actual = tm.var_swap(Index('MA123', AssetClass.Equity, '123'), '1m', '1y')
    assert actual.empty
    assert actual.dataset_ids == ()

    # finish
    replace.restore()


def _var_term_typical():
    assert DataContext.current_is_set
    data = {
        'tenor': ['1w', '2w', '1y', '2y'],
        'varSwap': [1, 2, 3, 4]
    }
    out = MarketDataResponseFrame(data=data, index=pd.DatetimeIndex(['2018-01-01'] * 4))
    out.dataset_ids = _test_datasets

    replace = Replacer()
    market_mock = replace('gs_quant.timeseries.measures.GsDataApi.get_market_data', Mock())
    market_mock.return_value = out

    actual = tm.var_term(Index('MA123', AssetClass.Equity, '123'))
    idx = pd.DatetimeIndex(['2018-01-08', '2018-01-15', '2019-01-01', '2020-01-01'], name='varSwap')
    expected = pd.Series([1, 2, 3, 4], name='varSwap', index=idx)
    expected = expected.loc[DataContext.current.start_date: DataContext.current.end_date]

    if expected.empty:
        assert actual.empty
    else:
        assert_series_equal(expected, pd.Series(actual), check_names=False)
        assert actual.dataset_ids == _test_datasets
    market_mock.assert_called_once()

    replace.restore()
    return actual


def _var_term_empty():
    replace = Replacer()
    market_mock = replace('gs_quant.timeseries.measures.GsDataApi.get_market_data', Mock())
    market_mock.return_value = mock_empty_market_data_response()

    actual = tm.var_term(Index('MAXYZ', AssetClass.Equity, 'XYZ'))
    assert actual.empty
    assert actual.dataset_ids == ()
    market_mock.assert_called_once()
    replace.restore()


def _var_term_fwd():
    idx = pd.date_range('2018-01-01', periods=2, freq='D')

    def mock_var_swap(_asset, tenor, _forward_start_date, **_kwargs):
        if tenor == '1m':
            series = tm.ExtendedSeries([1, 2], idx, name='varSwap')
            series.dataset_ids = _test_datasets
        elif tenor == '2m':
            series = tm.ExtendedSeries([3, 4], idx, name='varSwap')
            series.dataset_ids = _test_datasets
        else:
            series = tm.ExtendedSeries()
            series.dataset_ids = ()
        return series

    replace = Replacer()
    market_mock = replace('gs_quant.timeseries.measures.var_swap', Mock())
    market_mock.side_effect = mock_var_swap
    tenors_mock = replace('gs_quant.timeseries.measures._var_swap_tenors', Mock())
    tenors_mock.return_value = ['1m', '2m', '3m']

    actual = tm.var_term(Index('MA123', AssetClass.Equity, '123'), forward_start_date='1m')
    idx = pd.DatetimeIndex(['2018-02-02', '2018-03-02'], name='varSwap')
    expected = pd.Series([2, 4], name='varSwap', index=idx)
    expected = expected.loc[DataContext.current.start_date: DataContext.current.end_date]

    if expected.empty:
        assert actual.empty
    else:
        assert_series_equal(expected, pd.Series(actual), check_names=False)
        assert actual.dataset_ids == _test_datasets
    market_mock.assert_called()

    replace.restore()
    return actual


def test_var_term():
    with DataContext('2018-01-01', '2019-01-01'):
        _var_term_typical()
        _var_term_empty()
        _var_term_fwd()
    with DataContext('2019-01-01', '2019-07-04'):
        _var_term_fwd()
    with DataContext('2018-01-16', '2018-12-31'):
        out = _var_term_typical()
        assert out.empty
        assert out.dataset_ids == _test_datasets
    with pytest.raises(MqError):
        tm.var_term(..., pricing_date=300)


def _vol_term_typical(reference, value):
    assert DataContext.current_is_set
    data = {
        'tenor': ['1w', '2w', '1y', '2y'],
        'impliedVolatility': [1, 2, 3, 4]
    }
    out = MarketDataResponseFrame(data=data, index=pd.DatetimeIndex(['2018-01-01'] * 4))
    out.dataset_ids = _test_datasets

    replace = Replacer()
    market_mock = replace('gs_quant.timeseries.measures.GsDataApi.get_market_data', Mock())
    market_mock.return_value = out

    actual = tm.vol_term(Index('MA123', AssetClass.Equity, '123'), reference, value)
    idx = pd.DatetimeIndex(['2018-01-08', '2018-01-15', '2019-01-01', '2020-01-01'], name='expirationDate')
    expected = pd.Series([1, 2, 3, 4], name='impliedVolatility', index=idx)
    expected = expected.loc[DataContext.current.start_date: DataContext.current.end_date]

    if expected.empty:
        assert actual.empty
    else:
        assert_series_equal(expected, pd.Series(actual))
        assert actual.dataset_ids == _test_datasets
    market_mock.assert_called_once()

    replace.restore()
    return actual


def _vol_term_empty():
    replace = Replacer()
    market_mock = replace('gs_quant.timeseries.measures.GsDataApi.get_market_data', Mock())
    market_mock.return_value = MarketDataResponseFrame()

    actual = tm.vol_term(Index('MAXYZ', AssetClass.Equity, 'XYZ'), tm.VolReference.DELTA_CALL, 777)
    assert actual.empty
    assert actual.dataset_ids == ()
    market_mock.assert_called_once()
    replace.restore()


def test_vol_term():
    with DataContext('2018-01-01', '2019-01-01'):
        _vol_term_typical(tm.VolReference.SPOT, 100)
        _vol_term_typical(tm.VolReference.NORMALIZED, 4)
        _vol_term_typical(tm.VolReference.DELTA_PUT, 50)
        _vol_term_empty()
    with DataContext('2018-01-16', '2018-12-31'):
        out = _vol_term_typical(tm.VolReference.SPOT, 100)
        assert out.empty
        assert out.dataset_ids == _test_datasets
    with pytest.raises(NotImplementedError):
        tm.vol_term(..., tm.VolReference.SPOT, 100, real_time=True)
    with pytest.raises(MqError):
        tm.vol_term(Index('MA123', AssetClass.Equity, '123'), tm.VolReference.DELTA_NEUTRAL, 0)


def _vol_term_fx(reference, value):
    assert DataContext.current_is_set
    data = {
        'tenor': ['1w', '2w', '1y', '2y'],
        'impliedVolatility': [1, 2, 3, 4]
    }
    out = MarketDataResponseFrame(data=data, index=pd.DatetimeIndex(['2018-01-01'] * 4))
    out.dataset_ids = _test_datasets

    replace = Replacer()
    market_mock = replace('gs_quant.timeseries.measures.GsDataApi.get_market_data', Mock())
    market_mock.return_value = out
    cross_mock = replace('gs_quant.timeseries.measures.cross_stored_direction_for_fx_vol', Mock())
    cross_mock.return_value = 'EURUSD'

    actual = tm.vol_term(Cross('ABCDE', 'EURUSD'), reference, value)
    idx = pd.DatetimeIndex(['2018-01-08', '2018-01-15', '2019-01-01', '2020-01-01'], name='expirationDate')
    expected = pd.Series([1, 2, 3, 4], name='impliedVolatility', index=idx)
    expected = expected.loc[DataContext.current.start_date: DataContext.current.end_date]

    if expected.empty:
        assert actual.empty
    else:
        assert_series_equal(expected, pd.Series(actual))
        assert actual.dataset_ids == _test_datasets
    market_mock.assert_called_once()

    replace.restore()
    return actual


def test_vol_term_fx():
    with pytest.raises(MqError):
        tm.vol_term(Cross('MABLUE', 'BLUE'), tm.VolReference.SPOT, 50)
    with pytest.raises(MqError):
        tm.vol_term(Cross('MABLUE', 'BLUE'), tm.VolReference.NORMALIZED, 1)
    with pytest.raises(MqError):
        tm.vol_term(Cross('MABLUE', 'BLUE'), tm.VolReference.DELTA_NEUTRAL, 1)
    with DataContext('2018-01-01', '2019-01-01'):
        _vol_term_fx(tm.VolReference.DELTA_CALL, 50)
    with DataContext('2018-01-01', '2019-01-01'):
        _vol_term_fx(tm.VolReference.DELTA_PUT, 50)


def _fwd_term_typical():
    assert DataContext.current_is_set
    data = {
        'tenor': ['1w', '2w', '1y', '2y'],
        'forward': [1, 2, 3, 4]
    }
    out = MarketDataResponseFrame(data=data, index=pd.DatetimeIndex(['2018-01-01'] * 4))
    out.dataset_ids = _test_datasets

    replace = Replacer()
    market_mock = replace('gs_quant.timeseries.measures.GsDataApi.get_market_data', Mock())
    market_mock.return_value = out

    actual = tm.fwd_term(Index('MA123', AssetClass.Equity, '123'))
    idx = pd.DatetimeIndex(['2018-01-08', '2018-01-15', '2019-01-01', '2020-01-01'], name='expirationDate')
    expected = pd.Series([1, 2, 3, 4], name='forward', index=idx)
    expected = expected.loc[DataContext.current.start_date: DataContext.current.end_date]

    if expected.empty:
        assert actual.empty
    else:
        assert_series_equal(expected, pd.Series(actual))
        assert actual.dataset_ids == _test_datasets
    market_mock.assert_called_once()
    replace.restore()
    return actual


def _fwd_term_empty():
    replace = Replacer()
    market_mock = replace('gs_quant.timeseries.measures.GsDataApi.get_market_data', Mock())
    market_mock.return_value = mock_empty_market_data_response()

    actual = tm.fwd_term(Index('MAXYZ', AssetClass.Equity, 'XYZ'))
    assert actual.empty
    assert actual.dataset_ids == ()
    market_mock.assert_called_once()
    replace.restore()


def test_fwd_term():
    with DataContext('2018-01-01', '2019-01-01'):
        _fwd_term_typical()
        _fwd_term_empty()
    with DataContext('2018-01-16', '2018-12-31'):
        out = _fwd_term_typical()
        assert out.empty
        assert out.dataset_ids == _test_datasets
    with pytest.raises(NotImplementedError):
        tm.fwd_term(..., real_time=True)


def test_bucketize_price():
    target = {
        '7x24': [27.323461],
        'offpeak': [26.004816],
        'peak': [27.982783],
        '7x8': [26.004816],
        '2x16h': [],
        'monthly': [],
        'CAISO 7x24': [26.953743375],
        'CAISO peak': [30.153727375],
        'MISO 7x24': [27.076390749999998],
        'MISO offpeak': [25.263605624999997],
    }

    replace = Replacer()
    replace('gs_quant.timeseries.measures.GsDataApi.get_market_data', mock_commod)
    mock_pjm = Index('MA001', AssetClass.Commod, 'PJM')
    mock_caiso = Index('MA002', AssetClass.Commod, 'CAISO')
    mock_miso = Index('MA003', AssetClass.Commod, 'MISO')

    with DataContext(datetime.date(2019, 5, 1), datetime.date(2019, 5, 1)):
        bbid_mock = replace('gs_quant.timeseries.measures.Asset.get_identifier', Mock())
        bbid_mock.return_value = 'MISO'

        actual = tm.bucketize_price(mock_miso, 'LMP', bucket='7x24')
        assert_series_equal(pd.Series(target['MISO 7x24'],
                                      index=[datetime.date(2019, 5, 1)],
                                      name='price'),
                            pd.Series(actual))

        actual = tm.bucketize_price(mock_miso, 'LMP', bucket='offpeak')
        assert_series_equal(pd.Series(target['MISO offpeak'],
                                      index=[datetime.date(2019, 5, 1)],
                                      name='price'),
                            pd.Series(actual))

        bbid_mock.return_value = 'CAISO'

        actual = tm.bucketize_price(mock_caiso, 'LMP', bucket='7x24')
        assert_series_equal(pd.Series(target['CAISO 7x24'],
                                      index=[datetime.date(2019, 5, 1)],
                                      name='price'),
                            pd.Series(actual))

        actual = tm.bucketize_price(mock_caiso, 'LMP', bucket='peak')
        assert_series_equal(pd.Series(target['CAISO peak'],
                                      index=[datetime.date(2019, 5, 1)],
                                      name='price'),
                            pd.Series(actual))

        bbid_mock.return_value = 'PJM'

        actual = tm.bucketize_price(mock_pjm, 'LMP', bucket='7x24')
        assert_series_equal(pd.Series(target['7x24'],
                                      index=[datetime.date(2019, 5, 1)],
                                      name='price'),
                            pd.Series(actual))

        actual = tm.bucketize_price(mock_pjm, 'LMP', bucket='offpeak')
        assert_series_equal(pd.Series(target['offpeak'],
                                      index=[datetime.date(2019, 5, 1)],
                                      name='price'),
                            pd.Series(actual))

        actual = tm.bucketize_price(mock_pjm, 'LMP', bucket='peak')
        assert_series_equal(pd.Series(target['peak'],
                                      index=[datetime.date(2019, 5, 1)],
                                      name='price'),
                            pd.Series(actual))

        actual = tm.bucketize_price(mock_pjm, 'LMP', bucket='7x8')
        assert_series_equal(pd.Series(target['7x8'],
                                      index=[datetime.date(2019, 5, 1)],
                                      name='price'),
                            pd.Series(actual))

        actual = tm.bucketize_price(mock_pjm, 'LMP', bucket='2x16h')
        assert_series_equal(pd.Series(target['2x16h'],
                                      index=[],
                                      name='price'),
                            pd.Series(actual))

        actual = tm.bucketize_price(mock_pjm, 'LMP', granularity='m', bucket='7X24')
        assert_series_equal(pd.Series(target['monthly'],
                                      index=[],
                                      name='price'),
                            pd.Series(actual))

        with pytest.raises(ValueError):
            tm.bucketize_price(mock_pjm, 'LMP', bucket='7X24', real_time=True)

        with pytest.raises(ValueError):
            tm.bucketize_price(mock_pjm, 'LMP', bucket='weekday')

        with pytest.raises(ValueError):
            tm.bucketize_price(mock_caiso, 'LMP', bucket='weekday')

        with pytest.raises(ValueError):
            tm.bucketize_price(mock_pjm, 'LMP', granularity='yearly')

    replace.restore()


def test_forward_price():
    target = {
        '7x24': [19.46101],
        'peak': [23.86745],
        'J20 7x24': [18.11768888888889],
        'J20-K20 7x24': [19.283921311475414],
        'J20-K20 offpeak': [15.82870707070707],
        'J20-K20 7x8': [13.020144262295084],
    }
    replace = Replacer()
    replace('gs_quant.timeseries.measures.GsDataApi.get_market_data', mock_forward_price)
    mock_spp = Index('MA001', AssetClass.Commod, 'SPP')

    with DataContext(datetime.date(2019, 1, 2), datetime.date(2019, 1, 2)):
        bbid_mock = replace('gs_quant.timeseries.measures.Asset.get_identifier', Mock())
        bbid_mock.return_value = 'SPP'

        # Should return empty series as mark for '7x8' bucket is missing
        actual = tm.forward_price(mock_spp,
                                  price_method='LMP',
                                  contract_range='2Q20',
                                  bucket='7x24'
                                  )
        assert_series_equal(pd.Series(target['7x24'],
                                      index=[datetime.date(2019, 1, 2)],
                                      name='price'),
                            pd.Series(actual))

        actual = tm.forward_price(mock_spp,
                                  price_method='LMP',
                                  contract_range='J20',
                                  bucket='7x24'
                                  )
        assert_series_equal(pd.Series(target['J20 7x24'],
                                      index=[datetime.date(2019, 1, 2)],
                                      name='price'),
                            pd.Series(actual))

        actual = tm.forward_price(mock_spp,
                                  price_method='LMP',
                                  contract_range='2Q20',
                                  bucket='PEAK'
                                  )
        assert_series_equal(pd.Series(target['peak'],
                                      index=[datetime.date(2019, 1, 2)],
                                      name='price'),
                            pd.Series(actual))

        actual = tm.forward_price(mock_spp,
                                  price_method='LMP',
                                  contract_range='J20-K20',
                                  bucket='7x24'
                                  )
        assert_series_equal(pd.Series(target['J20-K20 7x24'],
                                      index=[datetime.date(2019, 1, 2)],
                                      name='price'),
                            pd.Series(actual))

        actual = tm.forward_price(mock_spp,
                                  price_method='LMP',
                                  contract_range='J20-K20',
                                  bucket='offpeak'
                                  )
        assert_series_equal(pd.Series(target['J20-K20 offpeak'],
                                      index=[datetime.date(2019, 1, 2)],
                                      name='price'),
                            pd.Series(actual))

        actual = tm.forward_price(mock_spp,
                                  price_method='LMP',
                                  contract_range='J20-K20',
                                  bucket='7x8'
                                  )
        assert_series_equal(pd.Series(target['J20-K20 7x8'],
                                      index=[datetime.date(2019, 1, 2)],
                                      name='price'),
                            pd.Series(actual))

        actual = tm.forward_price(mock_spp,
                                  price_method='lmp',
                                  contract_range='2Q20',
                                  bucket='7x24'
                                  )
        assert_series_equal(pd.Series(target['7x24'],
                                      index=[datetime.date(2019, 1, 2)],
                                      name='price'),
                            pd.Series(actual))

        with pytest.raises(ValueError):
            tm.forward_price(mock_spp,
                             price_method='LMP',
                             contract_range='5Q20',
                             bucket='PEAK'
                             )

        with pytest.raises(ValueError):
            tm.forward_price(mock_spp,
                             price_method='LMP',
                             contract_range='Invalid',
                             bucket='PEAK'
                             )

        with pytest.raises(ValueError):
            tm.forward_price(mock_spp,
                             price_method='LMP',
                             contract_range='3H20',
                             bucket='7x24'
                             )

        with pytest.raises(ValueError):
            tm.forward_price(mock_spp,
                             price_method='LMP',
                             contract_range='F20-I20',
                             bucket='7x24'
                             )

        with pytest.raises(ValueError):
            tm.forward_price(mock_spp,
                             price_method='LMP',
                             contract_range='2H20',
                             bucket='7x24',
                             real_time=True
                             )

        replace.restore()

        replace = Replacer()
        replace('gs_quant.timeseries.measures.GsDataApi.get_market_data', mock_missing_bucket_forward_price)
        bbid_mock = replace('gs_quant.timeseries.measures.Asset.get_identifier', Mock())
        bbid_mock.return_value = 'SPP'

        actual = tm.forward_price(mock_spp,
                                  price_method='LMP',
                                  contract_range='2Q20',
                                  bucket='7x24'
                                  )

        assert_series_equal(pd.Series(), pd.Series(actual), check_names=False)

        actual = tm.forward_price(mock_spp,
                                  price_method='LMP',
                                  contract_range='2Q20',
                                  bucket='PEAK'
                                  )
        assert_series_equal(pd.Series(target['peak'],
                                      index=[datetime.date(2019, 1, 2)],
                                      name='price'),
                            pd.Series(actual))

        actual = tm.forward_price(mock_spp,
                                  price_method='LMP',
                                  contract_range='J20-K20',
                                  bucket='7x24'
                                  )
        assert_series_equal(pd.Series(target['J20-K20 7x24'],
                                      index=[datetime.date(2019, 1, 2)],
                                      name='price'),
                            pd.Series(actual))

        replace.restore()


def test_get_iso_data():
    tz_map = {'MISO': 'US/Central', 'CAISO': 'US/Pacific'}
    for key in tz_map:
        assert (tm._get_iso_data(key)[0] == tz_map[key])


def test_string_to_date_interval():
    assert (tm._string_to_date_interval("K20")['start_date'] == datetime.date(2020, 5, 1))
    assert (tm._string_to_date_interval("K20")['end_date'] == datetime.date(2020, 5, 31))

    assert (tm._string_to_date_interval("k20")['start_date'] == datetime.date(2020, 5, 1))
    assert (tm._string_to_date_interval("k20")['end_date'] == datetime.date(2020, 5, 31))

    assert (tm._string_to_date_interval("Cal22")['start_date'] == datetime.date(2022, 1, 1))
    assert (tm._string_to_date_interval("Cal22")['end_date'] == datetime.date(2022, 12, 31))

    assert (tm._string_to_date_interval("Cal2012")['start_date'] == datetime.date(2012, 1, 1))
    assert (tm._string_to_date_interval("Cal2012")['end_date'] == datetime.date(2012, 12, 31))

    assert (tm._string_to_date_interval("Cal53")['start_date'] == datetime.date(1953, 1, 1))
    assert (tm._string_to_date_interval("Cal53")['end_date'] == datetime.date(1953, 12, 31))

    assert (tm._string_to_date_interval("2010")['start_date'] == datetime.date(2010, 1, 1))
    assert (tm._string_to_date_interval("2010")['end_date'] == datetime.date(2010, 12, 31))

    assert (tm._string_to_date_interval("3Q20")['start_date'] == datetime.date(2020, 7, 1))
    assert (tm._string_to_date_interval("3Q20")['end_date'] == datetime.date(2020, 9, 30))

    assert (tm._string_to_date_interval("2h2021")['start_date'] == datetime.date(2021, 7, 1))
    assert (tm._string_to_date_interval("2h2021")['end_date'] == datetime.date(2021, 12, 31))

    assert (tm._string_to_date_interval("3q20")['start_date'] == datetime.date(2020, 7, 1))
    assert (tm._string_to_date_interval("3q20")['end_date'] == datetime.date(2020, 9, 30))

    assert (tm._string_to_date_interval("2H2021")['start_date'] == datetime.date(2021, 7, 1))
    assert (tm._string_to_date_interval("2H2021")['end_date'] == datetime.date(2021, 12, 31))

    assert (tm._string_to_date_interval("Mar2021")['start_date'] == datetime.date(2021, 3, 1))
    assert (tm._string_to_date_interval("Mar2021")['end_date'] == datetime.date(2021, 3, 31))

    assert (tm._string_to_date_interval("March2021")['start_date'] == datetime.date(2021, 3, 1))
    assert (tm._string_to_date_interval("March2021")['end_date'] == datetime.date(2021, 3, 31))

    assert (tm._string_to_date_interval("5Q20") == "Invalid Quarter")

    assert (tm._string_to_date_interval("HH2021") == "Invalid num")

    assert (tm._string_to_date_interval("3H2021") == "Invalid Half Year")

    assert (tm._string_to_date_interval("Cal2a") == "Invalid year")
    assert (tm._string_to_date_interval("Marc201") == "Invalid date code")

    assert (tm._string_to_date_interval("M1a2021") == "Invalid date code")

    assert (tm._string_to_date_interval("Marcha2021") == "Invalid date code")

    assert (tm._string_to_date_interval("I20") == "Invalid month")

    assert (tm._string_to_date_interval("20") == "Unknown date code")


def test_implied_volatility():
    target = {
        'F21': [2.880],
        'F21-H21': [2.815756],
    }
    replace = Replacer()
    replace('gs_quant.timeseries.measures.GsDataApi.get_market_data', mock_implied_volatility)
    mock = Index('MA001', AssetClass.Commod, 'Option NG Exchange')

    with DataContext(datetime.date(2019, 1, 2), datetime.date(2019, 1, 2)):
        actual = tm.implied_volatility(mock,
                                       tenor='F21-H21')
        assert_series_equal(pd.Series(target['F21-H21'],
                                      index=[datetime.date(2019, 1, 2)],
                                      name='price'),
                            pd.Series(actual))
    replace.restore()


def test_fair_price():
    target = {
        'F21': [2.880],
        'F21-H21': [2.815756],
    }
    replace = Replacer()
    replace('gs_quant.timeseries.measures.GsDataApi.get_market_data', mock_fair_price)
    mock = Index('MA001', AssetClass.Commod, 'Swap NG Exchange')

    with DataContext(datetime.date(2019, 1, 2), datetime.date(2019, 1, 2)):
        actual = tm.fair_price(mock,
                               tenor='F21')
        assert_series_equal(pd.Series(target['F21'],
                                      index=[datetime.date(2019, 1, 2)],
                                      name='price'),
                            pd.Series(actual))
    replace.restore()


def test_weighted_average_valuation_curve_for_calendar_strip():
    target = {
        'F21': [2.880],
        'F21-H21': [2.815756],
    }
    replace = Replacer()
    replace('gs_quant.timeseries.measures.GsDataApi.get_market_data', mock_fair_price)
    mock = Index('MA001', AssetClass.Commod, 'Swap NG Exchange')

    with DataContext(datetime.date(2019, 1, 2), datetime.date(2019, 1, 2)):
        actual = tm._weighted_average_valuation_curve_for_calendar_strip(mock,
                                                                         contract_range='F21',
                                                                         query_type=QueryType.FAIR_PRICE,
                                                                         measure_field='fairPrice'
                                                                         )
        assert_series_equal(pd.Series(target['F21'],
                                      index=[datetime.date(2019, 1, 2)],
                                      name='price'),
                            pd.Series(actual))

        actual = tm._weighted_average_valuation_curve_for_calendar_strip(mock,
                                                                         contract_range='F21-H21',
                                                                         query_type=QueryType.FAIR_PRICE,
                                                                         measure_field='fairPrice'
                                                                         )
        assert_series_equal(pd.Series(target['F21-H21'],
                                      index=[datetime.date(2019, 1, 2)],
                                      name='price'),
                            pd.Series(actual))

        with pytest.raises(ValueError):
            tm._weighted_average_valuation_curve_for_calendar_strip(mock,
                                                                    contract_range='Invalid',
                                                                    query_type=QueryType.FAIR_PRICE,
                                                                    measure_field='fairPrice'
                                                                    )
        with pytest.raises(ValueError):
            tm._weighted_average_valuation_curve_for_calendar_strip(mock,
                                                                    contract_range='F20-I20',
                                                                    query_type=QueryType.FAIR_PRICE,
                                                                    measure_field='fairPrice'
                                                                    )
        with pytest.raises(ValueError):
            tm._weighted_average_valuation_curve_for_calendar_strip(mock,
                                                                    contract_range='3H20',
                                                                    query_type=QueryType.PRICE,
                                                                    measure_field='fairPrice'
                                                                    )

    replace.restore()


def test_fundamental_metrics():
    replace = Replacer()
    mock_spx = Index('MA890', AssetClass.Equity, 'SPX')
    replace('gs_quant.timeseries.measures.GsDataApi.get_market_data', mock_eq)
    period = '1y'
    direction = tm.FundamentalMetricPeriodDirection.FORWARD

    actual = tm.dividend_yield(mock_spx, period, direction)
    assert_series_equal(pd.Series([5, 1, 2], index=_index * 3, name='fundamentalMetric'), pd.Series(actual))
    assert actual.dataset_ids == _test_datasets
    with pytest.raises(NotImplementedError):
        tm.dividend_yield(..., period, direction, real_time=True)

    actual = tm.earnings_per_share(mock_spx, period, direction)
    assert_series_equal(pd.Series([5, 1, 2], index=_index * 3, name='fundamentalMetric'), pd.Series(actual))
    assert actual.dataset_ids == _test_datasets
    with pytest.raises(NotImplementedError):
        tm.earnings_per_share(..., period, direction, real_time=True)

    actual = tm.earnings_per_share_positive(mock_spx, period, direction)
    assert_series_equal(pd.Series([5, 1, 2], index=_index * 3, name='fundamentalMetric'), pd.Series(actual))
    assert actual.dataset_ids == _test_datasets
    with pytest.raises(NotImplementedError):
        tm.earnings_per_share_positive(..., period, direction, real_time=True)

    actual = tm.net_debt_to_ebitda(mock_spx, period, direction)
    assert_series_equal(pd.Series([5, 1, 2], index=_index * 3, name='fundamentalMetric'), pd.Series(actual))
    assert actual.dataset_ids == _test_datasets
    with pytest.raises(NotImplementedError):
        tm.net_debt_to_ebitda(..., period, direction, real_time=True)

    actual = tm.price_to_book(mock_spx, period, direction)
    assert_series_equal(pd.Series([5, 1, 2], index=_index * 3, name='fundamentalMetric'), pd.Series(actual))
    assert actual.dataset_ids == _test_datasets
    with pytest.raises(NotImplementedError):
        tm.price_to_book(..., period, direction, real_time=True)

    actual = tm.price_to_cash(mock_spx, period, direction)
    assert_series_equal(pd.Series([5, 1, 2], index=_index * 3, name='fundamentalMetric'), pd.Series(actual))
    assert actual.dataset_ids == _test_datasets
    with pytest.raises(NotImplementedError):
        tm.price_to_cash(..., period, direction, real_time=True)

    actual = tm.price_to_earnings(mock_spx, period, direction)
    assert_series_equal(pd.Series([5, 1, 2], index=_index * 3, name='fundamentalMetric'), pd.Series(actual))
    assert actual.dataset_ids == _test_datasets
    with pytest.raises(NotImplementedError):
        tm.price_to_earnings(..., period, direction, real_time=True)

    actual = tm.price_to_earnings_positive(mock_spx, period, direction)
    assert_series_equal(pd.Series([5, 1, 2], index=_index * 3, name='fundamentalMetric'), pd.Series(actual))
    assert actual.dataset_ids == _test_datasets
    with pytest.raises(NotImplementedError):
        tm.price_to_earnings_positive(..., period, direction, real_time=True)

    actual = tm.price_to_sales(mock_spx, period, direction)
    assert_series_equal(pd.Series([5, 1, 2], index=_index * 3, name='fundamentalMetric'), pd.Series(actual))
    assert actual.dataset_ids == _test_datasets
    with pytest.raises(NotImplementedError):
        tm.price_to_sales(..., period, direction, real_time=True)

    actual = tm.return_on_equity(mock_spx, period, direction)
    assert_series_equal(pd.Series([5, 1, 2], index=_index * 3, name='fundamentalMetric'), pd.Series(actual))
    assert actual.dataset_ids == _test_datasets
    with pytest.raises(NotImplementedError):
        tm.return_on_equity(..., period, direction, real_time=True)

    actual = tm.sales_per_share(mock_spx, period, direction)
    assert_series_equal(pd.Series([5, 1, 2], index=_index * 3, name='fundamentalMetric'), pd.Series(actual))
    assert actual.dataset_ids == _test_datasets
    with pytest.raises(NotImplementedError):
        tm.sales_per_share(..., period, direction, real_time=True)

    replace.restore()


def test_central_bank_swap_rate(mocker):
    target = {
        'meeting_absolute': -0.004550907771,
        'meeting_relative': -0.00002833724599999969,
        'eoy_absolute': -0.003359767756,
        'eoy_relative': 0.001162802769,
        'spot': -0.00455
    }
    mock_eur = Currency('MARFAGXDQRWM07Y2', 'EUR')

    with DataContext(dt.date(2019, 12, 6), dt.date(2019, 12, 6)):
        replace = Replacer()
        xrefs = replace('gs_quant.timeseries.measures.GsAssetApi.get_asset_xrefs', Mock())
        xrefs.return_value = [GsTemporalXRef(dt.date(2019, 1, 1), dt.date(2952, 12, 31), XRef(bbid='EUR', ))]
        mocker.patch.object(GsAssetApi, 'map_identifiers', side_effect=map_identifiers_default_mocker)

        mock_get_data = replace('gs_quant.data.dataset.Dataset.get_data', Mock())
        mock_get_data.return_value = mock_meeting_absolute()

        actual_abs = tm.central_bank_swap_rate(mock_eur, tm.MeetingType.MEETING_FORWARD, 'absolute',
                                               dt.date(2019, 12, 6))
        assert (target['meeting_absolute'] == actual_abs.loc[dt.date(2020, 1, 23)])
        assert actual_abs.dataset_ids == ('CENTRAL_BANK_WATCH',)

        actual_rel = tm.central_bank_swap_rate(mock_eur, tm.MeetingType.MEETING_FORWARD, 'relative',
                                               dt.date(2019, 12, 6))
        assert (target['meeting_relative'] == actual_rel.loc[dt.date(2020, 1, 23)])
        assert actual_rel.dataset_ids == ('CENTRAL_BANK_WATCH',)

        mock_get_data.return_value = mock_ois_spot()
        actual_spot = tm.central_bank_swap_rate(mock_eur, tm.MeetingType.SPOT, 'absolute', dt.date(2019, 12, 6))
        assert (target['spot'] == actual_spot.loc[dt.date(2019, 12, 6)])
        assert actual_spot.dataset_ids == ('CENTRAL_BANK_WATCH',)

        with pytest.raises(MqError):
            tm.central_bank_swap_rate(mock_eur, 'meeting_forward')

        with pytest.raises(MqError):
            tm.central_bank_swap_rate(mock_eur, tm.MeetingType.MEETING_FORWARD, 'normalized', '2019-09-01')

        with pytest.raises(MqError):
            tm.central_bank_swap_rate(mock_eur, tm.MeetingType.MEETING_FORWARD, 'absolute', 5)

        with pytest.raises(MqError):
            tm.central_bank_swap_rate(mock_eur, tm.MeetingType.MEETING_FORWARD, 'absolute', '01-09-2019')

        with pytest.raises(MqError):
            tm.central_bank_swap_rate(mock_eur, tm.MeetingType.SPOT, 'relative')

        with pytest.raises(NotImplementedError):
            tm.central_bank_swap_rate(mock_eur, tm.MeetingType.SPOT, 'absolute', real_time=True)

    replace.restore()


def test_policy_rate_expectation(mocker):
    target = {
        'meeting_number_absolute': -0.004550907771,
        'meeting_number_relative': -0.000028337246,
        'meeting_date_relative': -0.000028337246,
        'meeting_number_spot': -0.004522570525
    }
    mock_eur = Currency('MARFAGXDQRWM07Y2', 'EUR')

    with DataContext(dt.date(2019, 12, 6), dt.date(2019, 12, 6)):
        replace = Replacer()
        xrefs = replace('gs_quant.timeseries.measures.GsAssetApi.get_asset_xrefs', Mock())
        xrefs.return_value = [GsTemporalXRef(dt.date(2019, 1, 1), dt.date(2952, 12, 31), XRef(bbid='EUR', ))]
        mocker.patch.object(GsAssetApi, 'map_identifiers', side_effect=map_identifiers_default_mocker)
        mocker.patch.object(Dataset, 'get_data', side_effect=get_data_policy_rate_expectation_mocker)

        actual_num = tm.policy_rate_expectation(mock_eur, tm.MeetingType.MEETING_FORWARD, 'absolute', 2)
        assert (target['meeting_number_absolute'] == actual_num.loc[dt.date(2019, 12, 6)])
        assert actual_num.dataset_ids == ('CENTRAL_BANK_WATCH',)

        actual_date = tm.policy_rate_expectation(mock_eur, tm.MeetingType.MEETING_FORWARD, 'absolute',
                                                 dt.date(2020, 1, 23))
        assert (target['meeting_number_absolute'] == actual_date.loc[dt.date(2019, 12, 6)])
        assert actual_date.dataset_ids == ('CENTRAL_BANK_WATCH',)

        actual_num = tm.policy_rate_expectation(mock_eur, tm.MeetingType.MEETING_FORWARD, 'relative', 2)
        assert_allclose([target['meeting_number_relative']], [actual_num.loc[dt.date(2019, 12, 6)]],
                        rtol=1e-9, atol=1e-15)
        assert actual_num.dataset_ids == ('CENTRAL_BANK_WATCH',)

        actual_num = tm.policy_rate_expectation(mock_eur, tm.MeetingType.MEETING_FORWARD, 'absolute', 0)
        assert (target['meeting_number_spot'] == actual_num.loc[dt.date(2019, 12, 6)])
        assert actual_num.dataset_ids == ('CENTRAL_BANK_WATCH',)

        actual_date = tm.policy_rate_expectation(mock_eur, tm.MeetingType.MEETING_FORWARD, 'absolute', '2019-10-24')
        assert (target['meeting_number_spot'] == actual_date.loc[dt.date(2019, 12, 6)])
        assert actual_date.dataset_ids == ('CENTRAL_BANK_WATCH',)

        mocker.patch.object(Dataset, 'get_data', side_effect=[mock_meeting_expectation(),
                                                              mock_empty_market_data_response()])
        with pytest.raises(MqError):
            tm.policy_rate_expectation(mock_eur, tm.MeetingType.MEETING_FORWARD, 'relative', 2)

        with pytest.raises(MqError):
            tm.policy_rate_expectation(mock_eur, tm.MeetingType.SPOT)

        with pytest.raises(MqError):
            tm.policy_rate_expectation(mock_eur, tm.MeetingType.MEETING_FORWARD, 'relative', '5')

        with pytest.raises(MqError):
            tm.policy_rate_expectation(mock_eur, tm.MeetingType.MEETING_FORWARD, 'absolute', 5.5)

        with pytest.raises(MqError):
            tm.policy_rate_expectation(mock_eur, tm.MeetingType.MEETING_FORWARD, 'absolute', '01-09-2019')

        with pytest.raises(MqError):
            tm.policy_rate_expectation(mock_eur, tm.MeetingType.MEETING_FORWARD, 'normalized', dt.date(2019, 9, 1))

        with pytest.raises(MqError):
            tm.policy_rate_expectation(mock_eur, tm.MeetingType.MEETING_FORWARD, 'relative', -2)

        with pytest.raises(NotImplementedError):
            tm.policy_rate_expectation(mock_eur, tm.MeetingType.SPOT, 'absolute', real_time=True)

        mock_get_data = replace('gs_quant.data.dataset.Dataset.get_data', Mock())
        mock_get_data.return_value = pd.DataFrame()
        with pytest.raises(MqError):
            tm.policy_rate_expectation(mock_eur, tm.MeetingType.MEETING_FORWARD, 'absolute', 2)

    replace.restore()


def test_realized_volatility():
    from gs_quant.timeseries.econometrics import volatility, Returns
    from gs_quant.timeseries.statistics import generate_series

    random = generate_series(100).rename('spot')
    window = 10
    type_ = Returns.SIMPLE

    replace = Replacer()
    market_data = replace('gs_quant.timeseries.measures._market_data_timed', Mock())
    return_value = MarketDataResponseFrame(random)
    return_value.dataset_ids = _test_datasets
    market_data.return_value = return_value

    expected = volatility(random, window, type_)
    actual = tm.realized_volatility(Cross('MA123', 'ABCXYZ'), window, type_)
    assert_series_equal(expected, pd.Series(actual))
    assert actual.dataset_ids == _test_datasets
    replace.restore()


def test_esg_aggregate():
    replace = Replacer()

    mock_aapl = Stock('MA4B66MW5E27U9VBB94', 'AAPL')
    replace('gs_quant.timeseries.measures.GsDataApi.get_market_data', mock_esg)
    actual = tm.esg_aggregate(mock_aapl, tm.EsgMetric.ENVIRONMENTAL_SOCIAL_NUMERIC, tm.EsgValueUnit.SCORE)
    assert_series_equal(pd.Series([2, 4, 6], index=_index * 3, name='esNumericScore'), pd.Series(actual))
    assert actual.dataset_ids == _test_datasets

    actual = tm.esg_aggregate(mock_aapl, tm.EsgMetric.ENVIRONMENTAL_SOCIAL_POLICY, tm.EsgValueUnit.SCORE)
    assert_series_equal(pd.Series([2, 4, 6], index=_index * 3, name='esPolicyScore'), pd.Series(actual))
    assert actual.dataset_ids == _test_datasets

    actual = tm.esg_aggregate(mock_aapl, tm.EsgMetric.ENVIRONMENTAL_SOCIAL_AGGREGATE, tm.EsgValueUnit.SCORE)
    assert_series_equal(pd.Series([2, 4, 6], index=_index * 3, name='esScore'), pd.Series(actual))
    assert actual.dataset_ids == _test_datasets

    actual = tm.esg_aggregate(mock_aapl, tm.EsgMetric.GOVERNANCE_AGGREGATE, tm.EsgValueUnit.SCORE)
    assert_series_equal(pd.Series([2, 4, 6], index=_index * 3, name='gScore'), pd.Series(actual))
    assert actual.dataset_ids == _test_datasets

    actual = tm.esg_aggregate(mock_aapl, tm.EsgMetric.ENVIRONMENTAL_SOCIAL_MOMENTUM, tm.EsgValueUnit.SCORE)
    assert_series_equal(pd.Series([2, 4, 6], index=_index * 3, name='esMomentumScore'), pd.Series(actual))
    assert actual.dataset_ids == _test_datasets

    actual = tm.esg_aggregate(mock_aapl, tm.EsgMetric.GOVERNANCE_REGIONAL, tm.EsgValueUnit.SCORE)
    assert_series_equal(pd.Series([2, 4, 6], index=_index * 3, name='gRegionalScore'), pd.Series(actual))
    assert actual.dataset_ids == _test_datasets

    actual = tm.esg_aggregate(mock_aapl, tm.EsgMetric.ENVIRONMENTAL_SOCIAL_NUMERIC, tm.EsgValueUnit.PERCENTILE)
    assert_series_equal(pd.Series([81.2, 75.4, 65.7], index=_index * 3, name='esNumericPercentile'), pd.Series(actual))
    assert actual.dataset_ids == _test_datasets

    actual = tm.esg_aggregate(mock_aapl, tm.EsgMetric.ENVIRONMENTAL_SOCIAL_POLICY, tm.EsgValueUnit.PERCENTILE)
    assert_series_equal(pd.Series([81.2, 75.4, 65.7], index=_index * 3, name='esPolicyPercentile'), pd.Series(actual))
    assert actual.dataset_ids == _test_datasets

    actual = tm.esg_aggregate(mock_aapl, tm.EsgMetric.ENVIRONMENTAL_SOCIAL_AGGREGATE, tm.EsgValueUnit.PERCENTILE)
    assert_series_equal(pd.Series([81.2, 75.4, 65.7], index=_index * 3, name='esPercentile'), pd.Series(actual))
    assert actual.dataset_ids == _test_datasets

    actual = tm.esg_aggregate(mock_aapl, tm.EsgMetric.GOVERNANCE_AGGREGATE, tm.EsgValueUnit.PERCENTILE)
    assert_series_equal(pd.Series([81.2, 75.4, 65.7], index=_index * 3, name='gPercentile'), pd.Series(actual))
    assert actual.dataset_ids == _test_datasets

    actual = tm.esg_aggregate(mock_aapl, tm.EsgMetric.ENVIRONMENTAL_SOCIAL_MOMENTUM, tm.EsgValueUnit.PERCENTILE)
    assert_series_equal(pd.Series([81.2, 75.4, 65.7], index=_index * 3, name='esMomentumPercentile'), pd.Series(actual))
    assert actual.dataset_ids == _test_datasets

    actual = tm.esg_aggregate(mock_aapl, tm.EsgMetric.GOVERNANCE_REGIONAL, tm.EsgValueUnit.PERCENTILE)
    assert_series_equal(pd.Series([81.2, 75.4, 65.7], index=_index * 3, name='gRegionalPercentile'), pd.Series(actual))
    assert actual.dataset_ids == _test_datasets

    actual = tm.esg_aggregate(mock_aapl, tm.EsgMetric.ENVIRONMENTAL_SOCIAL_DISCLOSURE, tm.EsgValueUnit.SCORE)
    assert_series_equal(pd.Series([49.2, 55.7, 98.4], index=_index * 3, name='esDisclosurePercentage'),
                        pd.Series(actual))
    assert actual.dataset_ids == _test_datasets

    actual = tm.esg_aggregate(mock_aapl, tm.EsgMetric.ENVIRONMENTAL_SOCIAL_DISCLOSURE, tm.EsgValueUnit.PERCENTILE)
    assert_series_equal(pd.Series([49.2, 55.7, 98.4], index=_index * 3, name='esDisclosurePercentage'),
                        pd.Series(actual))
    assert actual.dataset_ids == _test_datasets

    actual = tm.esg_aggregate(mock_aapl, tm.EsgMetric.ENVIRONMENTAL_SOCIAL_DISCLOSURE)
    assert_series_equal(pd.Series([49.2, 55.7, 98.4], index=_index * 3, name='esDisclosurePercentage'),
                        pd.Series(actual))
    assert actual.dataset_ids == _test_datasets

    with pytest.raises(MqValueError):
        tm.esg_aggregate(mock_aapl, tm.EsgMetric.ENVIRONMENTAL_SOCIAL_NUMERIC)

    with pytest.raises(NotImplementedError):
        tm.esg_aggregate(mock_aapl, tm.EsgMetric.ENVIRONMENTAL_SOCIAL_NUMERIC, tm.EsgValueUnit.SCORE, real_time=True)

    replace.restore()


if __name__ == '__main__':
    pytest.main(args=["test_measures.py"])
