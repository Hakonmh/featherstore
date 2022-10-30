from collections import namedtuple
import pytest
from .fixtures import *

import pyarrow as pa
from pandas.testing import assert_frame_equal

TypeMapper = namedtuple('TypeMapper', 'arrow_dtype pandas_dtype')
TYPE_MAP = {
    'float16': TypeMapper(pa.float16(), 'float'),
    'float32': TypeMapper(pa.float32(), 'float'),
    'float64': TypeMapper(pa.float64(), 'float'),
    'decimal128(5, 5)': TypeMapper(pa.decimal128(5, 5), 'float'),
    'decimal128(19, 0)': TypeMapper(pa.decimal128(19, 0), 'float'),
    'int16': TypeMapper(pa.int16(), 'int'),
    'int32': TypeMapper(pa.int32(), 'int'),
    'int64': TypeMapper(pa.int64(), 'int'),
    'uint32': TypeMapper(pa.uint32(), 'uint'),
    'bool': TypeMapper(pa.bool_(), 'bool'),
    'date32': TypeMapper(pa.date32(), 'datetime'),
    'date64': TypeMapper(pa.date64(), 'datetime'),
    'time32': TypeMapper(pa.time32('ms'), 'datetime'),
    'time64': TypeMapper(pa.time64('us'), 'datetime'),
    'timestamp': TypeMapper(pa.timestamp('us'), 'datetime'),
    'string': TypeMapper(pa.string(), 'string'),
    'large_string': TypeMapper(pa.large_string(), 'string'),
    'binary': TypeMapper(pa.binary(), 'string'),
    'large_binary': TypeMapper(pa.large_binary(), 'string'),
}

KWARG_FORMATS = ['dict', 'list']
kwarg_format_idx = 0


@pytest.mark.parametrize(
    ("from_dtype", "to_dtype"),
    [
        ('float32', 'float64'),
        ('float32', 'decimal128(5, 5)'),
        ('int64', 'int32'),
        ('int32', 'float64'),
        ('int32', 'decimal128(19, 0)'),
        ('uint32', 'int32'),
        ('bool', 'int16'),
        ('bool', 'string'),
        ('int64', 'bool'),
        ('date32', 'date64'),
        ('date32', 'timestamp'),
        ('date64', 'date32'),
        ('timestamp', 'date64'),
        ('timestamp', 'time32'),
        ('time32', 'time64'),
        ('binary', 'large_binary'),
        ('binary', 'string'),
        ('string', 'binary'),
        ('large_string', 'string'),
    ]
)
def test_change_pa_dtype(store, from_dtype, to_dtype):
    # Arrange
    COLS = ['c1', 'c2']
    original_df = _make_table(dtype=from_dtype, rows=60, cols=3)
    expected = _change_dtype(original_df, to_dtype, cols=COLS)

    partition_size = get_partition_size(original_df)
    table = store.select_table(TABLE_NAME)
    table.write(original_df, partition_size=partition_size)

    cols, dtype = _format_cols_and_to_key_args(COLS, to_dtype)
    # Act
    table.astype(cols, to=dtype)
    # Assert
    _assert_frame_equal(table, expected)


@pytest.mark.parametrize(
    ("from_dtype", "to_dtype"),
    [
        ('float32', 'float64'),
        ('int64', 'int32'),
        ('int32', 'float64'),
        ('uint32', 'int32'),
        ('bool', 'int16'),
        ('int64', 'bool'),
    ]
)
def test_change_np_dtype(store, from_dtype, to_dtype):
    # Arrange
    COLS = ['c1', 'c2']
    original_df = _make_table(dtype=from_dtype, rows=60, cols=3)
    expected = _change_dtype(original_df, to_dtype, cols=COLS)

    partition_size = get_partition_size(original_df)
    table = store.select_table(TABLE_NAME)
    table.write(original_df, partition_size=partition_size)
    cols, dtype = _format_cols_and_to_key_args(COLS, to_dtype, as_numpy_dtype=True)
    # Act
    table.astype(cols, to=dtype)
    # Assert
    _assert_frame_equal(table, expected)


def _make_table(dtype, rows=30, cols=3):
    pandas_dtype = TYPE_MAP[dtype].pandas_dtype
    df = make_table(rows=rows, cols=cols, astype="arrow", dtype=pandas_dtype)
    df = _change_dtype(df, dtype)
    return df


def _change_dtype(df, to_dtype, cols=None):
    arrow_dtype = TYPE_MAP[to_dtype].arrow_dtype
    schema = df.schema
    cols = cols if cols else schema.names
    for idx, field in enumerate(schema):
        if field.name in cols:
            field = field.with_type(arrow_dtype)
            schema = schema.set(idx, field)
    df = df.cast(schema)
    return df


def _format_cols_and_to_key_args(cols, to_dtype, as_numpy_dtype=False):
    """Selects every other test to format arguments as one of either:
        * cols=['c1', 'c2'], to=[dtype1, dtype2]
        * cols = {'c1': dtype1, 'c2': dtype2}
    """
    global kwarg_format_idx
    kwarg_format_idx = (kwarg_format_idx + 1) % 2
    kwarg_format = KWARG_FORMATS[kwarg_format_idx]

    dtype = TYPE_MAP[to_dtype].arrow_dtype
    if as_numpy_dtype:
        dtype = dtype.to_pandas_dtype()
    if kwarg_format == 'dict':
        cols = {col: dtype for col in cols}
        to = None
    elif kwarg_format == 'list':
        to = [dtype] * len(cols)
    return cols, to


def _assert_frame_equal(table, expected):
    _assert_arrow(table, expected)
    _assert_polars(table, expected)
    _assert_pandas(table, expected)


def _assert_arrow(table, expected):
    df = table.read_arrow()
    assert df.equals(expected)


def _assert_polars(table, expected):
    df = table.read_polars()
    expected = pl.from_arrow(expected)
    assert df.frame_equal(expected)


def _assert_pandas(table, expected):
    df = table.read_pandas()
    expected = expected.to_pandas(date_as_object=False)
    expected = __convert_object_cols_to_string(expected)
    assert_frame_equal(df, expected, check_dtype=True)


def __convert_object_cols_to_string(df):
    for col in df.columns:
        if df[col].dtype.name == 'object':
            if isinstance(df[col][0], str):
                df[col] = df[col].astype('string')
    return df


NEW_DTYPES_PROVIDED_TWICE = [{'c0': pa.int16()}, [pa.int16()]]
NEW_DTYPES_NOT_PROVIDED = [['c0', 'c1'], None]
INVALID_COLS_ARGUMENT_DTYPE = ['c0', [pa.int16()]]
INVALID_COLS_KEYS_ARGUMENT_DTYPE = [{1: pa.int32}, None]
INVALID_COLS_VALUES_ARGUMENT_DTYPE = [{'c0': 123}, None]
INVALID_TO_ARGUMENT_DTYPE = [['c0'], pa.int16()]
INVALID_TO_ITEMS_DTYPE = [['c0'], [123]]
NUMBER_OF_COLS_AND_DTYPES_DONT_MATCH = [['c0', 'c1'], [pa.int16()]]
FORBIDDEN_INDEX_DTYPE = [[DEFAULT_ARROW_INDEX_NAME], [pa.float32()]]
NON_ARROW_DTYPE = [['c0'], [pl.Float32()]]
INVALID_NEW_DTYPE = [['c0'], [pa.float32()]]
DUPLICATE_COL_NAMES = [['c0', 'c0'], [pa.int16(), pa.int32()]]


@pytest.mark.parametrize(
    ("args", "exception"),
    [
        (NEW_DTYPES_PROVIDED_TWICE, AttributeError),
        (NEW_DTYPES_NOT_PROVIDED, AttributeError),
        (NUMBER_OF_COLS_AND_DTYPES_DONT_MATCH, ValueError),
        (INVALID_COLS_ARGUMENT_DTYPE, TypeError),
        (INVALID_COLS_KEYS_ARGUMENT_DTYPE, TypeError),
        (INVALID_COLS_VALUES_ARGUMENT_DTYPE, TypeError),
        (INVALID_TO_ARGUMENT_DTYPE, TypeError),
        (INVALID_TO_ITEMS_DTYPE, TypeError),
        (FORBIDDEN_INDEX_DTYPE, TypeError),
        (NON_ARROW_DTYPE, TypeError),
        (INVALID_NEW_DTYPE, pa.ArrowInvalid),
        (DUPLICATE_COL_NAMES, IndexError),
    ],
    ids=[
        "NEW_DTYPES_PROVIDED_TWICE",
        "NEW_DTYPES_NOT_PROVIDED",
        "NUMBER_OF_COLS_AND_DTYPES_DONT_MATCH",
        "INVALID_COLS_ARGUMENT_DTYPE",
        "INVALID_COLS_KEYS_ARGUMENT_DTYPE",
        "INVALID_COLS_VALUES_ARGUMENT_DTYPE",
        "INVALID_TO_ARGUMENT_DTYPE",
        "INVALID_TO_ITEMS_DTYPE",
        "FORBIDDEN_INDEX_DTYPE",
        "NON_ARROW_DTYPE",
        "INVALID_NEW_DTYPE",
        "DUPLICATE_COL_NAMES"
    ]
)
def test_can_change_dtype(store, args, exception):
    # Arrange
    original_df = make_table(cols=5, astype='pandas')
    table = store.select_table(TABLE_NAME)
    table.write(original_df)
    col_names = args[0]
    dtypes = args[1]
    # Act and Assert
    with pytest.raises(exception):
        table.astype(col_names, to=dtypes)
