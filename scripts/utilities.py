from pyfbsdk import *
from vray import Transform, Vector
import math

DEG_TO_RAD = math.pi / 180.0
RAD_TO_DEG = 180.0 / math.pi

class Singleton(type):
    """Singleton to use as a __metaclass__"""
    _instances = {}
    def __call__(cls):
        if cls not in cls._instances:
            cls._instances[cls] = super(Singleton, cls).__call__()
        return cls._instances[cls]

class Session(object):
    """Used to store some scene data that doesn't get saved in .FBX files"""
    def __init__(self):
        self.appended_files = []
        self.applied_vrmats = {}
        self.applied_multis = {}
    
    def is_empty(self):
        return not (self.appended_files or self.applied_vrmats or self.applied_multis)
    
def make_fb_xform_vray(vray_matrix):
    res = FBMatrix()
    res[0]  = vray_matrix[0][0][0]
    res[1]  = vray_matrix[0][0][1]
    res[2]  = vray_matrix[0][0][2]
    res[3]  = 0
    res[4]  = vray_matrix[0][1][0]
    res[5]  = vray_matrix[0][1][1]
    res[6]  = vray_matrix[0][1][2]
    res[7]  = 0
    res[8]  = vray_matrix[0][2][0]
    res[9]  = vray_matrix[0][2][1]
    res[10] = vray_matrix[0][2][2]
    res[11] = 0
    res[12] = vray_matrix[1][0]
    res[13] = vray_matrix[1][1]
    res[14] = vray_matrix[1][2]
    res[15] = 1
    return res
    
def make_vray_xform_fb(fb_matrix):
    # this could be removed if a Transform(list) constructor gets implemented
    res = Transform()
    res[0][0][0] = fb_matrix[0]
    res[0][0][1] = fb_matrix[1]
    res[0][0][2] = fb_matrix[2]
    res[0][1][0] = fb_matrix[4]
    res[0][1][1] = fb_matrix[5]
    res[0][1][2] = fb_matrix[6]
    res[0][2][0] = fb_matrix[8]
    res[0][2][1] = fb_matrix[9]
    res[0][2][2] = fb_matrix[10]
    res[1][0]    = fb_matrix[12]
    res[1][1]    = fb_matrix[13]
    res[1][2]    = fb_matrix[14]
    return res
    
def eps_equal(left, right, epsilon=0.0001):
    if abs(left - right) > epsilon:
        return False
    return True
    
def equal_fb_matrices(left, right, epsilon=0.0001):
    for cell in xrange(16):
        if abs(left[cell] - right[cell]) > epsilon:
            return False
    return True
    
def clear_selection():
    sel = FBModelList()
    FBGetSelectedModels(sel)
    FBBeginChangeAllModels()
    for m in sel:
        m.Selected = False
    FBEndChangeAllModels()
    