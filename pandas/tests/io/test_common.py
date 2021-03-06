"""
    Tests for the pandas.io.common functionalities
"""
import mmap
import pytest
import os
from os.path import isabs

import pandas as pd
import pandas.util.testing as tm

from pandas.io import common
from pandas.compat import is_platform_windows, StringIO

from pandas import read_csv, concat

try:
    from pathlib import Path
except ImportError:
    pass

try:
    from py.path import local as LocalPath
except ImportError:
    pass


class CustomFSPath(object):
    """For testing fspath on unknown objects"""
    def __init__(self, path):
        self.path = path

    def __fspath__(self):
        return self.path


HERE = os.path.dirname(__file__)


class TestCommonIOCapabilities(object):
    data1 = """index,A,B,C,D
foo,2,3,4,5
bar,7,8,9,10
baz,12,13,14,15
qux,12,13,14,15
foo2,12,13,14,15
bar2,12,13,14,15
"""

    def test_expand_user(self):
        filename = '~/sometest'
        expanded_name = common._expand_user(filename)

        assert expanded_name != filename
        assert isabs(expanded_name)
        assert os.path.expanduser(filename) == expanded_name

    def test_expand_user_normal_path(self):
        filename = '/somefolder/sometest'
        expanded_name = common._expand_user(filename)

        assert expanded_name == filename
        assert os.path.expanduser(filename) == expanded_name

    def test_stringify_path_pathlib(self):
        tm._skip_if_no_pathlib()

        rel_path = common._stringify_path(Path('.'))
        assert rel_path == '.'
        redundant_path = common._stringify_path(Path('foo//bar'))
        assert redundant_path == os.path.join('foo', 'bar')

    def test_stringify_path_localpath(self):
        tm._skip_if_no_localpath()

        path = os.path.join('foo', 'bar')
        abs_path = os.path.abspath(path)
        lpath = LocalPath(path)
        assert common._stringify_path(lpath) == abs_path

    def test_stringify_path_fspath(self):
        p = CustomFSPath('foo/bar.csv')
        result = common._stringify_path(p)
        assert result == 'foo/bar.csv'

    def test_get_filepath_or_buffer_with_path(self):
        filename = '~/sometest'
        filepath_or_buffer, _, _ = common.get_filepath_or_buffer(filename)
        assert filepath_or_buffer != filename
        assert isabs(filepath_or_buffer)
        assert os.path.expanduser(filename) == filepath_or_buffer

    def test_get_filepath_or_buffer_with_buffer(self):
        input_buffer = StringIO()
        filepath_or_buffer, _, _ = common.get_filepath_or_buffer(input_buffer)
        assert filepath_or_buffer == input_buffer

    def test_iterator(self):
        reader = read_csv(StringIO(self.data1), chunksize=1)
        result = concat(reader, ignore_index=True)
        expected = read_csv(StringIO(self.data1))
        tm.assert_frame_equal(result, expected)

        # GH12153
        it = read_csv(StringIO(self.data1), chunksize=1)
        first = next(it)
        tm.assert_frame_equal(first, expected.iloc[[0]])
        tm.assert_frame_equal(concat(it), expected.iloc[1:])

    @pytest.mark.parametrize('reader, module, path', [
        (pd.read_csv, 'os', os.path.join(HERE, 'data', 'iris.csv')),
        (pd.read_table, 'os', os.path.join(HERE, 'data', 'iris.csv')),
        (pd.read_fwf, 'os', os.path.join(HERE, 'data',
                                         'fixed_width_format.txt')),
        (pd.read_excel, 'xlrd', os.path.join(HERE, 'data', 'test1.xlsx')),
        (pd.read_feather, 'feather', os.path.join(HERE, 'data',
                                                  'feather-0_3_1.feather')),
        (pd.read_hdf, 'tables', os.path.join(HERE, 'data', 'legacy_hdf',
                                             'datetimetz_object.h5')),
        (pd.read_stata, 'os', os.path.join(HERE, 'data', 'stata10_115.dta')),
        (pd.read_sas, 'os', os.path.join(HERE, 'sas', 'data',
                                         'test1.sas7bdat')),
        (pd.read_json, 'os', os.path.join(HERE, 'json', 'data',
                                          'tsframe_v012.json')),
        (pd.read_msgpack, 'os', os.path.join(HERE, 'msgpack', 'data',
                                             'frame.mp')),
        (pd.read_pickle, 'os', os.path.join(HERE, 'data',
                                            'categorical_0_14_1.pickle')),
    ])
    def test_read_fspath_all(self, reader, module, path):
        pytest.importorskip(module)

        mypath = CustomFSPath(path)
        result = reader(mypath)
        expected = reader(path)
        if path.endswith('.pickle'):
            # categorical
            tm.assert_categorical_equal(result, expected)
        else:
            tm.assert_frame_equal(result, expected)

    @pytest.mark.parametrize('writer_name, writer_kwargs, module', [
        ('to_csv', {}, 'os'),
        ('to_excel', {'engine': 'xlwt'}, 'xlwt'),
        ('to_feather', {}, 'feather'),
        ('to_hdf', {'key': 'bar', 'mode': 'w'}, 'tables'),
        ('to_html', {}, 'os'),
        ('to_json', {}, 'os'),
        ('to_latex', {}, 'os'),
        ('to_msgpack', {}, 'os'),
        ('to_pickle', {}, 'os'),
        ('to_stata', {}, 'os'),
    ])
    def test_write_fspath_all(self, writer_name, writer_kwargs, module):
        p1 = tm.ensure_clean('string')
        p2 = tm.ensure_clean('fspath')
        df = pd.DataFrame({"A": [1, 2]})

        with p1 as string, p2 as fspath:
            pytest.importorskip(module)
            mypath = CustomFSPath(fspath)
            writer = getattr(df, writer_name)

            writer(string, **writer_kwargs)
            with open(string, 'rb') as f:
                expected = f.read()

            writer(mypath, **writer_kwargs)
            with open(fspath, 'rb') as f:
                result = f.read()

            assert result == expected


class TestMMapWrapper(object):

    def setup_method(self, method):
        self.mmap_file = os.path.join(tm.get_data_path(),
                                      'test_mmap.csv')

    def test_constructor_bad_file(self):
        non_file = StringIO('I am not a file')
        non_file.fileno = lambda: -1

        # the error raised is different on Windows
        if is_platform_windows():
            msg = "The parameter is incorrect"
            err = OSError
        else:
            msg = "[Errno 22]"
            err = mmap.error

        tm.assert_raises_regex(err, msg, common.MMapWrapper, non_file)

        target = open(self.mmap_file, 'r')
        target.close()

        msg = "I/O operation on closed file"
        tm.assert_raises_regex(
            ValueError, msg, common.MMapWrapper, target)

    def test_get_attr(self):
        with open(self.mmap_file, 'r') as target:
            wrapper = common.MMapWrapper(target)

        attrs = dir(wrapper.mmap)
        attrs = [attr for attr in attrs
                 if not attr.startswith('__')]
        attrs.append('__next__')

        for attr in attrs:
            assert hasattr(wrapper, attr)

        assert not hasattr(wrapper, 'foo')

    def test_next(self):
        with open(self.mmap_file, 'r') as target:
            wrapper = common.MMapWrapper(target)
            lines = target.readlines()

        for line in lines:
            next_line = next(wrapper)
            assert next_line.strip() == line.strip()

        pytest.raises(StopIteration, next, wrapper)
