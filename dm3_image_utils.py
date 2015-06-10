# ParseDM3File reads in a DM3 file and translates it into a dictionary
# this module treats that dictionary as an image-file and extracts the
# appropriate image data as numpy arrays.
# It also tries to create files from numpy arrays that DM can read.
#
# Some notes:
# Only complex64 and complex128 types are converted to structarrays,
# ie they're arrays of structs. Everything else, (including RGB) are
# standard arrays.
# There is a seperate DatatType and PixelDepth stored for images different
# from the tag file datatype. I think these are used more than the tag
# datratypes in describing the data.
from .parse_dm3 import *
import numpy as np

# conditional imports
import sys
if sys.version < '3':
    def u(x=None):
        return unicode(x if x is not None else str())
    unicode_type = unicode
    long_type = long
    def str_to_utf16_bytes(s):
        return bytes(s)
else:
    def u(x=None):
        return str(x if x is not None else str())
    unicode_type = str
    long_type = int
    def str_to_utf16_bytes(s):
        return s.encode('utf-16')

structarray_to_np_map = {
    ('d', 'd'): np.complex128,
    ('f', 'f'): np.complex64}

np_to_structarray_map = {v: k for k, v in iter(structarray_to_np_map.items())}

# we want to amp any image type to a single np array type
# but a sinlge np array type could map to more than one dm type.
# For the moment, we won't be strict about, eg, discriminating
# int8 from bool, or even unit32 from RGB. In the future we could
# convert np bool type eg to DM bool and treat y,x,3 int8 images
# as RGB.

# note uint8 here returns the same data type as int8 0 could be that the
# only way they're differentiated is via this type, not the raw type
# in the tag file? And 8 is missing!
dm_image_dtypes = {
    1: ("int16", np.int16),
    2: ("float32", np.float32),
    3: ("Complex64", np.complex64),
    6: ("uint8", np.int8),
    7: ("int32", np.int32),
    9: ("int8", np.int8),
    10: ("uint16", np.uint16),
    11: ("uint32", np.uint32),
    12: ("float64", np.float64),
    13: ("Complex128", np.complex128),
    14: ("Bool", np.int8),
    23: ("RGB", np.int32)
}


def imagedatadict_to_ndarray(imdict):
    """
    Converts the ImageData dictionary, imdict, to an nd image.
    """
    arr = imdict['Data']
    im = None
    if isinstance(arr, array.array):
        im = np.asarray(arr, dtype=arr.typecode)
    elif isinstance(arr, structarray):
        t = tuple(arr.typecodes)
        im = np.frombuffer(
            arr.raw_data,
            dtype=structarray_to_np_map[t])
    # print "Image has dmimagetype", imdict["DataType"], "numpy type is", im.dtype
    assert dm_image_dtypes[imdict["DataType"]][1] == im.dtype
    assert imdict['PixelDepth'] == im.dtype.itemsize
    return im.reshape(imdict['Dimensions'][::-1])


def ndarray_to_imagedatadict(nparr):
    """
    Convert the numpy array nparr into a suitable ImageList entry dictionary.
    Returns a dictionary with the appropriate Data, DataType, PixelDepth
    to be inserted into a dm3 tag dictionary and written to a file.
    """
    ret = {}
    dm_type = next(k for k, v in iter(dm_image_dtypes.items()) if v[1] == nparr.dtype.type)
    ret["DataType"] = dm_type
    ret["PixelDepth"] = nparr.dtype.itemsize
    ret["Dimensions"] = list(nparr.shape[::-1])
    if nparr.dtype.type in np_to_structarray_map:
        types = np_to_structarray_map[nparr.dtype.type]
        ret["Data"] = structarray(types)
        ret["Data"].raw_data = bytes(nparr.data)
    else:
        ret["Data"] = array.array(nparr.dtype.char, nparr.flatten())
    return ret


import types
def display_keys(tag, indent=None):
    indent = indent if indent is not None else str()
    if isinstance(tag, types.ListType) or isinstance(tag, types.TupleType):
        for i, v in enumerate(tag):
            logging.debug("%s %s:", indent, i)
            display_keys(v, indent + "..")
    elif isinstance(tag, types.DictType):
        for k, v in iter(tag.items()):
            logging.debug("%s key: %s", indent, k)
            display_keys(v, indent + "..")
    elif isinstance(tag, types.BooleanType):
        logging.debug("%s bool: %s", indent, tag)
    elif isinstance(tag, types.IntType):
        logging.debug("%s int: %s", indent, tag)
    elif isinstance(tag, types.LongType):
        logging.debug("%s long: %s", indent, tag)
    elif isinstance(tag, types.FloatType):
        logging.debug("%s float: %s", indent, tag)
    elif isinstance(tag, types.StringType):
        logging.debug("%s string: %s", indent, tag)
    elif isinstance(tag, unicode_type):
        logging.debug("%s unicode: %s", indent, tag)
    else:
        logging.debug("%s %s: DATA", indent, type(tag))


def fix_strings(d):
    if isinstance(d, dict):
        r = dict()
        for k, v in d.items():
            if k != "Data":
                r[k] = fix_strings(v)
            else:
                r[k] = v
        return r
    elif isinstance(d, list):
        l = list()
        for v in d:
            l.append(fix_strings(v))
        return l
    elif isinstance(d, array.array):
        return d.tostring().decode("utf-16")
    else:
        return d

def load_image(file):
    """
    Loads the image from the file-like object or string file.
    If file is a string, the file is opened and then read.
    Returns a numpy ndarray of our best guess for the most important image
    in the file.
    """
    if isinstance(file, str) or isinstance(file, unicode_type):
        with open(file, "rb") as f:
            return load_image(f)
    dmtag = parse_dm_header(file)
    dmtag = fix_strings(dmtag)
    #display_keys(dmtag)
    img_index = -1
    image_tags = dmtag['ImageList'][img_index]
    data = imagedatadict_to_ndarray(image_tags['ImageData'])
    calibrations = []
    calibration_tags = image_tags['ImageData'].get('Calibrations', dict())
    for dimension in calibration_tags.get('Dimension', list()):
        calibrations.append((dimension['Origin'], dimension['Scale'], dimension['Units']))
    brightness = calibration_tags.get('Brightness', dict())
    intensity = brightness.get('Origin', 0.0), brightness.get('Scale', 1.0), brightness.get('Units', str())
    title = image_tags.get('Name')
    properties = dict()
    voltage = None
    if 'ImageTags' in image_tags:
        properties["imported_properties"] = image_tags['ImageTags']
        voltage = image_tags['ImageTags'].get('ImageScanned', dict()).get('EHT', dict())
        if voltage:
            properties["autostem"] = { "high_tension_v": float(voltage) }
            properties["extra_high_tension"] = float(voltage)  # TODO: file format: remove extra_high_tension
    return data, tuple(reversed(calibrations)), intensity, title, properties


def save_image(data, dimensional_calibrations, intensity_calibration, metadata, file):
    """
    Saves the nparray data to the file-like object (or string) file.
    If file is a string the file is created and written to
    """
    if isinstance(file, str):
        with open(file, "wb") as f:
            return save_image(n, f)
    # we need to create a basic DM tree suitable for an image
    # we'll try the minimum: just an data list
    # doesn't work. Do we need a ImageSourceList too?
    # and a DocumentObjectList?
    data_dict = ndarray_to_imagedatadict(data)
    ret = {}
    ret["ImageList"] = [{"ImageData": data_dict}]
    if dimensional_calibrations and len(dimensional_calibrations) == len(data.shape):
        dimension_list = data_dict.setdefault("Calibrations", dict()).setdefault("Dimension", list())
        for dimensional_calibration in reversed(dimensional_calibrations):
            dimension = dict()
            dimension['Origin'] = dimensional_calibration.offset
            dimension['Scale'] = dimensional_calibration.scale
            dimension['Units'] = u(dimensional_calibration.units)
            dimension_list.append(dimension)
    if intensity_calibration:
        brightness = data_dict.setdefault("Calibrations", dict()).setdefault("Brightness", dict())
        brightness['Origin'] = intensity_calibration.offset
        brightness['Scale'] = intensity_calibration.scale
        brightness['Units'] = str(intensity_calibration.units)
    # I think ImageSource list creates a mapping between ImageSourceIds and Images
    ret["ImageSourceList"] = [{"ClassName": "ImageSource:Simple", "Id": [0], "ImageRef": 0}]
    # I think this lists the sources for the DocumentObjectlist. The source number is not
    # the indxe in the imagelist but is either the index in the ImageSourceList or the Id
    # from that list. We also need to set the annotation type to identify it as an data
    ret["DocumentObjectList"] = [{"ImageSource": 0, "AnnotationType": 20}]
    # finally some display options
    ret["Image Behavior"] = {"ViewDisplayID": 8}
    ret["ImageList"][0]["ImageTags"] = metadata
    ret["InImageMode"] = 1
    parse_dm_header(file, ret)


# logging.debug(image_tags['ImageData']['Calibrations'])
# {u'DisplayCalibratedUnits': True, u'Dimension': [{u'Origin': -0.0, u'Units': u'nm', u'Scale': 0.01171875}, {u'Origin': -0.0, u'Units': u'nm', u'Scale': 0.01171875}, {u'Origin': 0.0, u'Units': u'', u'Scale': 0.01149425096809864}], u'Brightness': {u'Origin': 0.0, u'Units': u'', u'Scale': 1.0}}
