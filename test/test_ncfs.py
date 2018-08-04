import unittest
from ncfsplayground.fusenetcdf import NCFS


class TestIsVarDir(unittest.TestCase):

    def setUp(self):
        self.ncfs = NCFS(None, None, None)

    def test_is_var_dir_1(self):
        self.assertTrue(self.ncfs.is_var_dir('/abcd'))

    def test_is_var_dir_2(self):
        self.assertFalse(self.ncfs.is_var_dir('/abcd/def'))

    def test_is_var_dir_3(self):
        self.assertFalse(self.ncfs.is_var_dir('/'))

    def test_is_var_dir_4(self):
        self.assertFalse(self.ncfs.is_var_dir('/abcd/DATA_REPR'))


class TestIsVarData(unittest.TestCase):

    def setUp(self):
        self.ncfs = NCFS(None, None, None)

    def test_is_var_data_1(self):
        self.assertFalse(self.ncfs.is_var_data('/abcd'))

    def test_is_var_data_2(self):
        self.assertFalse(self.ncfs.is_var_data('/abcd/def'))

    def test_is_var_data_3(self):
        self.assertFalse(self.ncfs.is_var_data('/'))

    def test_is_var_data_4(self):
        self.assertTrue(self.ncfs.is_var_data('/abcd/DATA_REPR'))


class TestIsVarAttribute(unittest.TestCase):

    def setUp(self):
        self.ncfs = NCFS(None, None, None)

    def test_is_var_attribute_1(self):
        self.assertFalse(self.ncfs.is_var_attribute('/abcd'))

    def test_is_var_attribute_2(self):
        self.assertTrue(self.ncfs.is_var_attribute('/abcd/def'))

    def test_is_var_attribute_3(self):
        self.assertFalse(self.ncfs.is_var_attribute('/'))

    def test_is_var_attribute_4(self):
        self.assertFalse(self.ncfs.is_var_attribute('/abcd/DATA_REPR'))

    def test_is_var_attribute_5(self):
        self.assertFalse(self.ncfs.is_var_attribute('/abcd/dimensions'))


class StubVariable(object):
    def getncattr(self, name):
        if name == 'fooattr':
            return 'bar'
        else:
            raise AttributeError()


class StubDataset(object):
    variables = {'foovar': StubVariable()}


class TestExists(unittest.TestCase):

     def setUp(self):
         dataset = StubDataset()
         self.ncfs = NCFS(dataset, None, None)

     def test_exists_1(self):
         self.assertTrue(self.ncfs.exists('/foovar'))

     def test_exists_2(self):
         self.assertTrue(self.ncfs.exists('/foovar/fooattr'))

     def test_exists_3(self):
         self.assertFalse(self.ncfs.exists('/foovar/fooattr/foo'))
