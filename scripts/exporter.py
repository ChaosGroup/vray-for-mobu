from pyfbsdk import *
import vray
from utilities import *
import time, math
from accel import getViewportSize

def makeIntList(l):
    l = vray.List(l)
    l.setType("IntList")
    return l

def makeFloatList(l):
    l = vray.List(l)
    l.setType("FloatList")
    return l
    
def makeVectorList(l):
    l = vray.List(l)
    l.setType("VectorList")
    return l

def makeColorList(l):
    l = vray.List(l)
    l.setType("ColorList")
    return l

    
class PluginInfo:
    """Links V-Ray and MoBu instances
    
    Also store any other necessary data here
    """
    def __init__(self):
        self.plugin = None
        self.mobu_obj = None
    
class VRay4MobuExporter(object):
    """Keeps the V-Ray Renderer updated with the current scene state"""
    
    __metaclass__ = Singleton
    
    def __init__(self):
        self.cam = None
        self._cam_rotation_fix = FBMatrix([0,0,1,0, 0,1,0,0, -1,0,0,0, 0,0,0,1])
        self._light_rotation_fix = FBMatrix([1,0,0,0, 0,0,-1,0, 0,1,0,0, 0,0,0,1])
        self._dome_uvw_matrix_fix = vray.Matrix(vray.Vector(1,0,0), vray.Vector(0,0,1), vray.Vector(0,-1,0))
        self._use_phys_cam = False
        
        self.full_update_interval = 0.3
        self.quick_update_interval = 0.016
        
        self.clear()
        
        self._anylight_prop_dict = {
            "Visibility": ("enabled", "bool"),
            "Color": ("color", "color"),
            "Intensity": ("intensity", "float")
        }
        self._domelight_prop_dict = {
            "[V] Spherical": ("dome_spherical", "bool"),
            "[V] Tex Browse...": ("dome_tex", "action"),
            "[V] Tex Filepath": ("dome_tex", "texture")
        }
        self._rectlight_prop_dict = {
            "[V] U Size": ("u_size", "float"),
            "[V] V Size": ("v_size", "float"),
            "[V] Directional": ("directional", "float"),
            "[V] Is Disc": ("is_disc", "bool"),
            "[V] Tex Browse...": ("rect_tex", "action"),
            "[V] Tex Filepath": ("rect_tex", "texture")
        }
        self._spherelight_prop_dict = {
            "[V] Radius": ("radius", "float"),
            "[V] Segments": ("sphere_segments", "int")
        }
        self._sunlight_prop_dict = {
            "Visibility": ("enabled", "bool"),
            "Color": ("filter_color", "color"),
            "Intensity": ("intensity_multiplier", "float"),
            "[V] Turbidity": ("turbidity", "float"),
            "[V] Ozone": ("ozone", "float"),
            "[V] Vapor": ("water_vapour", "float"),
            "[V] Size multiplier": ("size_multiplier", "float"),
            "[V] Color mode": ("color_mode", "int"),
            "[V] Horizontal illumination": ("horiz_illum", "float"),
            "[V] Sky model": ("sky_model", "int")
        }
        self._directlight_prop_dict = {
            # nothing for now
        }
        self._cam_prop_dict = {
            "UseDepthOfField": ("use_dof", "bool"),
            "FocalLength": ("focal_length", "float"),
            "FocusAngle": ("f_number", "float"),
            "FilmWidth": ("film_width", "float"),
            "FocusDistance": ("focus_distance", "float"),
            "[V] Type": ("type", "int"),
            "[V] Shutter Speed": ("shutter_speed", "float"),
            "[V] Shutter Angle": ("shutter_angle", "float"),
            "[V] Shutter Offset": ("shutter_offset", "float"),
            "[V] Latency": ("latency", "float"),
            "[V] Vignetting": ("vignetting", "float"),
            "[V] Exposure Correction": ("exposure", "bool"),
            "[V] ISO": ("ISO", "int"),
            "[V] White Balance": ("white_balance", "color"),
            "[V] Use Blades": ("blades_enable", "bool"),
            "[V] Number of Blades": ("blades_num", "int"),
            "[V] Blades Rotation": ("blades_rotation", "float"),
            "[V] Center Bias": ("center_bias", "float"),
            "[V] Anisotropy": ("anisotropy", "float"),
            "[V] Horizontal Offset": ("horizontal_offset", "float"),
            "[V] Vertical Offset": ("vertical_offset", "float")
        }
        
    def __del__(self):
        #print "[debug] deleting exporter"
        pass
    
    def set_renderer(self, renderer):
        if self._renderer is not renderer:
            self._nodes = {}
        self._renderer = renderer
        
    def export(self):
        """Call on every frame. Always updates transforms.
        Other changes are handled on larger intervals"""
        
        if self._renderer is None or self._renderer.closed:
            return
        
        self._tick += 1
        current_time = time.clock()
        
        if self._tick == 1:
            self._def_light = self._renderer.classes.MayaLightDirect()
        
        # use the default light only while there is no scene light
        if len(self._scene.Lights) == 0:
            if self._def_light.enabled == False:
                self._def_light.enabled = True
        elif self._def_light.enabled == True:
            self._def_light.enabled = False
        
        # this also updates the existing camera
        self._create_camera(self._scene.Renderer.CurrentCamera)
        
        if current_time > self._last_full_update + self.full_update_interval:
            self._remove_and_add_nodes()
            self._last_full_update = current_time
        
        if current_time > self._last_quick_update + self.quick_update_interval:
            for node_pair in self._nodes.iteritems():
                self._update_transform(node_pair)
            self._last_quick_update = current_time
        
        self._renderer.commit()
        
##        if self._tick == 1:
##           _save()
        
    def _save(self, suffix=""):
        # for debugging
        fname = "c:/export_%s%04d.vrscene" % (suffix, self._tick)
        export_settings = {}
        export_settings['useHexFormat'] = False
        self._renderer.export(fname, export_settings)

    def clear(self):
        print "", # WHAT THE HELL: if I don't print here, Mobu freezes
        #print "[debug] clear exporter"
        self._scene = FBSystem().Scene
        self._last_full_update = 0
        self._last_quick_update = 0
        self._nodes = {} # used to connect FB objects and V-Ray plugin instances
        self._renderer = None
        self._use_phys_cam = False
        self._rend_view = None
        self._cam_plugin = None
        self._def_light = None
        self._tick = 0
        
        # fix matrix in case of restart
        if self.cam:
            self.cam._old_fbmatrix = FBMatrix()
            self.cam._old_fbmatrix[15] = 2.0 # make it different
        self.cam = None
        
    def _get_models_and_lights(self, node, models, lights):
        if isinstance(node, FBLight):
            lights.append(node)
        elif not isinstance(node, FBCamera):
            models.append(node)
        for child in node.Children:
            self._get_models_and_lights(child, models, lights)
        
    def _update_transform(self, node_pair):
        node = node_pair[0]
        plugin = node_pair[1].plugin
        
        xform_now = FBMatrix()
        node.GetMatrix(xform_now, FBModelTransformationType.kModelTransformation_Geometry)
        final_xform = xform_now
        has_diff = xform_now.NotEqual(node._old_fbmatrix)
        
        if not has_diff:
            return
        
        if isinstance(node, FBLight):
            final_xform = FBMatrix()
            FBMatrixMult(final_xform, xform_now, self._light_rotation_fix)
        
        # def_light is handled in create_camera as it is attached to it
        if plugin != self._def_light:
            plugin.transform = make_vray_xform_fb(final_xform)
            if plugin.getType() == "LightDome" and plugin.dome_tex and plugin.dome_tex.uvwgen:
                invmat = FBMatrix(xform_now)
                invmat.Inverse()
                tm = make_vray_xform_fb(invmat)
                plugin.dome_tex.uvwgen.uvw_matrix = self._dome_uvw_matrix_fix * tm.matrix
            if plugin.getType() == "SunLight":
                vec = FBVector3d(xform_now[12], xform_now[13], xform_now[14])
                vec.Normalize()
                up = FBVector3d(0, 1, 0)
                
                xaxis = up.CrossProduct(vec)
                xaxis.Normalize()
                yaxis = vec.CrossProduct(xaxis)
                yaxis.Normalize()
                
                rotmat = FBMatrix()
                rotmat[0] = xaxis[0]
                rotmat[1] = xaxis[1]
                rotmat[2] = xaxis[2]
                rotmat[4] = yaxis[0]
                rotmat[5] = yaxis[1]
                rotmat[6] = yaxis[2]
                rotmat[8] = vec[0]
                rotmat[9] = vec[1]
                rotmat[10] = vec[2]
                
                vray_rotmat = make_vray_xform_fb(rotmat)
                plugin.transform = vray_rotmat
        
        # we need to store this for the has_diff check
        # the code used to compare to the plugin.transform in vray, but it
        # was causing erroneous updates due to precision issues
        node._old_fbmatrix.CopyFrom(xform_now)
        
    def _remove_and_add_nodes(self):
        models = []
        lights = []
        self._get_models_and_lights(self._scene.RootModel, models, lights)
        
        for node in self._nodes.keys():
            if node not in models and node not in lights:
                ##print "[debug] deleting", node.Name, node
                if isinstance(node, FBLight) and hasattr(node, "_sky_to_delete"):
                    # FIXME single instance assumed (enforce?)
                    se = self._renderer.classes.SettingsEnvironment.getInstances()[0]
                    se.bg_tex = None
                    se.gi_tex = None
                    se.reflect_tex = None
                    se.refract_tex = None
                    del self._renderer.plugins[node._sky_to_delete]
                del self._renderer.plugins[self._nodes[node].plugin]
                del self._nodes[node]

        for model in models:
            if model not in self._nodes:
                self._create_model(model)
        for light in lights:
            if light not in self._nodes:
                self._create_light(light)
                
    def _create_model(self, model):
        import random
        
        t = type(model)
        if t != FBModel and t != FBModelCube and t != FBModelPlane:
            return
        
        if model.Geometry is None or type(model.Geometry) is not FBMesh:
            return
        
        # _vray_skip is used for quick filtering of models and lights we can't handle (creation attempt on every tick)
        if model.PropertyList.Find("_vray_skip") and model.PropertyList.Find("_vray_skip").Data == True:
            return
        
        ##print "[debug] creating model", model.Name
        ver_array = model.Geometry.GetPositionsArray()
        nor_array = model.Geometry.GetNormalsDirectArray()
        ver_idx_array = model.Geometry.PolygonVertexArrayGet()
        nor_idx_array = model.Geometry.GetNormalsIndexArray()
        mat_idx_array = model.Geometry.GetMaterialIndexArray()
        
        normal_mode = model.Geometry.NormalMappingMode
        if normal_mode != FBGeometryMappingMode.kFBGeometryMapping_BY_POLYGON_VERTEX and normal_mode != FBGeometryMappingMode.kFBGeometryMapping_BY_CONTROL_POINT:
            print "Unsupported normal mapping mode", normal_mode, "for", model.Name
            p = model.PropertyList.Find("_vray_skip")
            if not p:
                p = model.PropertyCreate("_vray_skip", FBPropertyType.kFBPT_bool, 'Bool', False, True, None)
            p.Data = True
            return
        
        material_mode = model.Geometry.MaterialMappingMode
        if material_mode != FBGeometryMappingMode.kFBGeometryMapping_BY_POLYGON and material_mode != FBGeometryMappingMode.kFBGeometryMapping_ALL_SAME:
            print "Unsupported material mapping mode", material_mode, "for", model.Name
            p = model.PropertyList.Find("_vray_skip")
            if not p:
                p = model.PropertyCreate("_vray_skip", FBPropertyType.kFBPT_bool, 'Bool', False, True, None)
            p.Data = True
            return
            
        if model.Geometry.NormalReferenceMode != FBGeometryReferenceMode.kFBGeometryReference_DIRECT:
            print "Unsupported normal ref mode", model.Geometry.NormalReferenceMode, "for", model.Name
            p = model.PropertyList.Find("_vray_skip")
            if not p:
                p = model.PropertyCreate("_vray_skip", FBPropertyType.kFBPT_bool, 'Bool', False, True, None)
            p.Data = True
            return
        
        num_verts = len(ver_array) / 3
        num_norms = len(nor_array) / 3
        if len(mat_idx_array) == 1 and len(ver_idx_array) > 3:
            mat_idx_array = []
        
        # triangulate convex polygons (ear clipping)
        if not model.Geometry.IsTriangleMesh():
            orig_ver_idx = ver_idx_array
            del ver_idx_array
            ver_idx_array = []
            
            read_idx = 0
            for face in xrange(0, model.Geometry.PolygonCount()):
                n = model.Geometry.PolygonVertexCount(face)
                for i in xrange(1, n-1):
                    ver_idx_array += [orig_ver_idx[read_idx], orig_ver_idx[read_idx + i], orig_ver_idx[read_idx + i + 1]]
                read_idx += n
            
            if nor_idx_array:
                if normal_mode == FBGeometryMappingMode.kFBGeometryMapping_BY_CONTROL_POINT:
                    # FIXME probably wrong
                    nor_idx_array = ver_idx_array
                else:
                    orig_nor_idx = nor_idx_array
                    del nor_idx_array
                    nor_idx_array = []
                    read_idx = 0
                    for face in xrange(0, model.Geometry.PolygonCount()):
                        n = model.Geometry.PolygonVertexCount(face)
                        for i in xrange(1, n-1):
                            nor_idx_array += [orig_nor_idx[read_idx], orig_nor_idx[read_idx + i], orig_nor_idx[read_idx + i + 1]]
                        read_idx += n
            
            if mat_idx_array:
                new_mat_idx_array = []
                for x in xrange(len(mat_idx_array)):
                    new_mat_idx_array += [mat_idx_array[x]] * (model.Geometry.PolygonVertexCount(x) - 2)
                mat_idx_array = new_mat_idx_array
        
        if not nor_idx_array:
            if normal_mode == FBGeometryMappingMode.kFBGeometryMapping_BY_CONTROL_POINT:
                # FIXME? not sure if this is correct - need a test case
                #import copy
                #nor_idx_array = copy.deepcopy(ver_idx_array)
                nor_idx_array = ver_idx_array
            else:
                if model.Geometry.IsTriangleMesh():
                    nor_idx_array = range(num_norms)
                else:
                    nor_idx_array = []
                    idx = 0
                    for face in xrange(0, model.Geometry.PolygonCount()):
                        n = model.Geometry.PolygonVertexCount(face)
                        for i in xrange(1, n-1):
                            nor_idx_array += [idx, idx + i, idx + i + 1]
                        idx += n
        
        
        # process UV map channels
        _mc_names = model.Geometry.GetUVSets()
        mc_names = []
        # convert from fb string list to normal list
        for name in _mc_names:
            mc_names.append(str(name))
        if not mc_names:
            mc_names.append(None)
        mc = []
        mc_index = 1
        for name in mc_names:
            uvs = model.Geometry.GetUVSetDirectArray(name)
            indices = model.Geometry.GetUVSetIndexArray(name)
            if not model.Geometry.IsTriangleMesh():
                orig_indices = indices
                del indices
                indices = []
                
                read_idx = 0
                for face in xrange(model.Geometry.PolygonCount()):
                    n = model.Geometry.PolygonVertexCount(face)
                    for i in xrange(1, n-1):
                        indices += [orig_indices[read_idx], orig_indices[read_idx + i], orig_indices[read_idx + i + 1]]
                    read_idx += n
                    
            uvws = [] # FB has UVs, while vray expects UVWs
            uvs_len = len(uvs)
            if uvs_len % 2 == 1:
                uvs.append(0.0)
            for i in xrange(0, uvs_len, 2):
                uvws.append(vray.Vector(uvs[i], uvs[i+1], 0.0))
            mc.append(vray.List([mc_index, makeVectorList(uvws), makeIntList(indices)]))
            mc_index += 1
        
        #print model.Name, "[tri, nv, nf, nn, nnf, nmi]",model.Geometry.IsTriangleMesh(), num_verts, len(ver_idx_array) /3, num_norms, len(nor_idx_array)/3, len(mat_idx_array)
        vertices = makeVectorList(num_verts * [None])
        faces = makeIntList(ver_idx_array)
        normals = makeVectorList(num_norms * [None])
        face_normals = makeIntList(nor_idx_array)
        map_channels = vray.List(mc)
        map_channels_names = vray.List(mc_names)
        mat_ids = makeIntList(mat_idx_array)

        # fill vertex and normal arrays in vray format
        for i in xrange(0, len(ver_array), 3):
            vertices[i/3] = vray.Vector(ver_array[i], ver_array[i+1], ver_array[i+2])
        
        for i in xrange(0, len(nor_array), 3):
            normals[i/3] = vray.Vector(nor_array[i], nor_array[i+1], nor_array[i+2])

        mesh = self._renderer.classes.GeomStaticMesh()
        mesh.dynamic_geometry = True # this is very important for performance
        mesh.vertices = vertices
        mesh.faces = faces
        mesh.normals = normals
        mesh.faceNormals = face_normals
        mesh.map_channels = map_channels
        mesh.face_mtlIDs = mat_ids
        
        brdf = self._renderer.classes.BRDFDiffuse()
        brdf.color = vray.Color(random.random(), random.random(), random.random())
        #brdf.color = vray.Color(0.5, 0.5, 0.5)
        
        material = self._renderer.classes.MtlSingleBRDF()
        material.brdf = brdf
        
        vrnode = self._renderer.classes.Node()
        vrnode.material = material
        vrnode.geometry = mesh
        
        model._old_fbmatrix = FBMatrix()
        model._old_fbmatrix[15] = 2.0 # make it different
        
        pinfo = PluginInfo()
        pinfo.plugin = vrnode
        pinfo.mobu_obj = model
        self._nodes[model] = pinfo
        
    def _create_light(self, light):
        if light.PropertyList.Find("_vray_skip") and light.PropertyList.Find("_vray_skip").Data == True:
            return
        
        vtype = light.PropertyList.Find("[V] V-Ray Type")
        if not vtype:
            print "Not implemented for", light.Name, light
            p = light.PropertyList.Find("_vray_skip")
            if not p:
                p = light.PropertyCreate("_vray_skip", FBPropertyType.kFBPT_bool, 'Bool', False, True, None)
            p.Data = True
            return
        
        # fix enum after loading from file
        enumlist = vtype.GetEnumStringList(True)
        if len(enumlist) == 0:
            for name in ["Dome", "Rectangle", "Sphere", "Directional", "Sun"]:
                enumlist.Add(name)
            vtype.NotifyEnumStringListChanged()
        
        if vtype.AsString() == "Dome":
            vrlight = self._renderer.classes.LightDome()
            vrlight.use_dome_tex = True
            vrlight.tex_resolution = 2048 # the default 512 is too pixelated
            for propname in self._domelight_prop_dict.keys():
                prop = light.PropertyList.Find(propname)
                self.update_custom_prop(prop, vrlight, *self._domelight_prop_dict[propname])
        elif vtype.AsString() == "Rectangle":
            vrlight = self._renderer.classes.LightRectangle()
            vrlight.use_rect_tex = True
            for propname in self._rectlight_prop_dict.keys():
                prop = light.PropertyList.Find(propname)
                self.update_custom_prop(prop, vrlight, *self._rectlight_prop_dict[propname])
        elif vtype.AsString() == "Sphere":
            vrlight = self._renderer.classes.LightSphere()
            for propname in self._spherelight_prop_dict.keys():
                prop = light.PropertyList.Find(propname)
                self.update_custom_prop(prop, vrlight, *self._spherelight_prop_dict[propname])
        elif vtype.AsString() == "Directional":
            vrlight = self._renderer.classes.LightDirect()
            for propname in self._directlight_prop_dict.keys():
                prop = light.PropertyList.Find(propname)
                self.update_custom_prop(prop, vrlight, *self._directlight_prop_dict[propname])
        elif vtype.AsString() == "Sun":
            vrlight = self._renderer.classes.SunLight()
            vrlight.up_vector = vray.Vector(0.0, 1.0, 0.0)
            vrlight.target_transform = vray.Transform(vray.Matrix(vray.Vector(1.0, 0.0, 0.0), vray.Vector(0.0, 1.0, 0.0), vray.Vector(0.0, 0.0, 1.0)), vray.Vector(0.0, 0.0, 0.0))
            sky = self._renderer.classes.TexSky()
            sky.sun = vrlight
            try:
                se = self._renderer.classes.SettingsEnvironment.getInstances()[0]
            except:
                se = self._renderer.classes.SettingsEnvironment()
            se.bg_tex = sky
            se.gi_tex = sky
            se.reflect_tex = sky
            se.refract_tex = sky
            light._sky_to_delete = sky # we need this so that we can shut down the sky when we delete the light
            for propname in self._sunlight_prop_dict.keys():
                prop = light.PropertyList.Find(propname)
                self.update_custom_prop(prop, vrlight, *self._sunlight_prop_dict[propname])
        else:
            return
        
        if vtype.AsString() != "Sun":
            for propname in self._anylight_prop_dict.keys():
                prop = light.PropertyList.Find(propname)
                self.update_custom_prop(prop, vrlight, *self._anylight_prop_dict[propname])
        
        light._old_fbmatrix = FBMatrix()
        light._old_fbmatrix[15] = 2.0 # make it different
        
        pinfo = PluginInfo()
        pinfo.plugin = vrlight
        pinfo.mobu_obj = light
        self._nodes[light] = pinfo
        
    def _create_camera(self, cam):
        """This is actually used both for initial creation and updates"""
        
        need_set = False
        if cam is not self.cam:
            self.cam = cam
            self._init_cam_props(cam)
            
            prop = cam.PropertyList.Find("[V] Use Physical")
            self._use_phys_cam = prop.Data
            
            try:
                getattr(cam, "_old_fbmatrix")
            except:
                cam._old_fbmatrix = FBMatrix()
                cam._old_fbmatrix[15] = 2.0 # make it different
            
            if self._cam_plugin:
                del self._renderer.plugins[self._cam_plugin]
            self._cam_plugin = None
            
            try:
                sDof = self._renderer.classes.SettingsCameraDof.getInstances()[0]
                del self._renderer.plugins[sDof]
            except:
                pass
            
            # need to re-export this for DoF to work properly
            self._renderer.classes.SettingsCameraDof()
            
            if not self._use_phys_cam:
                self._cam_plugin = self._renderer.classes.CameraDefault()
            else:
                self._cam_plugin = self._renderer.classes.CameraPhysical()
                self._cam_plugin.specify_fov = True
                self._cam_plugin.specify_focus = True
                
                for p in cam.PropertyList:
                    if p.Name != "[V] Use Physical" and p.Name in self._cam_prop_dict.keys():
                        if p.Name == "FocusDistance":
                            if self.cam.Interest is None or self.cam.FocusDistanceSource == FBCameraFocusDistanceSource.kFBFocusDistanceSpecificDistance:
                                self._cam_plugin.focus_distance = float(self.cam.FocusSpecificDistance)
                        elif p.Name == "FilmWidth":
                            self._cam_plugin.film_width = float(p.Data) * 25.4
                        else:
                            self.update_custom_prop(p, self._cam_plugin, *self._cam_prop_dict[p.Name])
            
            need_set = True
        
        if not self._rend_view:
            self._rend_view = self._renderer.classes.RenderView()
            # important! currently we need to manually set this to 0 for camera movements to take effect
            self._rend_view.use_scene_offset = 0
            
        if self._use_phys_cam and cam.Interest is not None and cam.FocusDistanceSource == FBCameraFocusDistanceSource.kFBFocusDistanceCameraInterest:
            dist_vec = cam.Interest.Translation.Data - cam.Translation.Data
            dist = dist_vec.Length()
            if not eps_equal(self._cam_plugin.focus_distance, dist):
                self._cam_plugin.focus_distance = dist
        
        xform_now = FBMatrix()
        cam.GetMatrix(xform_now, FBModelTransformationType.kModelTransformation_Geometry)
        final_xform = xform_now
        has_diff = xform_now.NotEqual(cam._old_fbmatrix)
        
        # the cam lookAt direction is +X in fbx ...
        if has_diff and self._def_light:
            final_xform = FBMatrix()
            FBMatrixMult(final_xform, xform_now, self._cam_rotation_fix)
            
            self._rend_view.transform = make_vray_xform_fb(final_xform)
            self._def_light.transform = self._rend_view.transform
            
            cam._old_fbmatrix.CopyFrom(xform_now)
        
        if cam.ApertureMode == FBCameraApertureMode.kFBApertureHorizontal:
            newFov = DEG_TO_RAD * cam.FieldOfView.Data
        else:
            aspect = self._renderer.size[0]/float(self._renderer.size[1])
            newFov = 2.0 * math.atan(aspect * math.tan(0.5 * DEG_TO_RAD * cam.FieldOfView.Data))
        if need_set or not eps_equal(newFov, self._rend_view.fov):
            self._rend_view.fov = newFov
            if self._use_phys_cam:
                self._cam_plugin.fov = newFov
        
        if need_set:
            self._renderer.camera = self._cam_plugin
    
    def reexport_cam(self):
        """Some physical camera and units changes will only work by recreating the plugin"""
        self.cam = None
        if self._tick:
            self._create_camera(self._scene.Renderer.CurrentCamera)
        
    def get_models(self):
        models = [item for item in self._nodes.itervalues() if item.plugin.getClass().getName() == "Node"]
        return models
        
    def get_pinfo_by_name(self, nodename):
        for node in self._nodes.iterkeys():
            if node.Name == nodename:
                return self._nodes[node]
        return None
        
    def apply_vrmat(self, pinfos, filename, matname):
        print "Applying", matname, "(", filename, ")", "..."
        for pinfo in pinfos:
            
            if pinfo.plugin.getClass().getName() != "Node":
                continue
            
            vrmat = self._renderer.classes.MtlVRmat()
            vrmat.filename = str(filename)
            vrmat.mtlname = str(matname)
            
            mtl = self._renderer.classes.MtlSingleBRDF()
            mtl.brdf = vrmat
            
            pinfo.plugin.material = mtl
        
        self._renderer.commit()
    
    def apply_multimtl(self, pinfos, matname):
        print "Applying", matname, "..."
        for pinfo in pinfos:
            
            if pinfo.plugin.getClass().getName() != "Node":
                continue
            
            try:
                mtl = self._renderer.plugins[matname]
                pinfo.plugin.material = mtl
            except:
                print "  FAILED on", pinfo.plugin.getName()
        
        self._renderer.commit()
    
    def find_mobu_node(self, vray_node):
        for m, v in self._nodes.iteritems():
            if vray_node is v:
                return m
        return None
            
    def _delete_tex(self, vray_plug, param_name):
        tex = vray_plug[param_name]
        vray_plug[param_name] = None
        if tex:
            bitmap = tex.bitmap
            uvwgen = tex.uvwgen
            if bitmap:
                del self._renderer.plugins[bitmap]
            if uvwgen:
                del self._renderer.plugins[uvwgen]
            del self._renderer.plugins[tex]
            
    def _create_tex(self, vray_plug, param_name, tex_path):
        if vray_plug.getType() == "LightDome":
            uvwgen = self._renderer.classes.UVWGenEnvironment()
            uvwgen.uvw_matrix = self._dome_uvw_matrix_fix
        else:
            uvwgen = self._renderer.classes.UVWGenChannel()
            
        bitmap = self._renderer.classes.BitmapBuffer()
        bitmap.file = tex_path
        
        tex = self._renderer.classes.TexBitmap()
        tex.bitmap = bitmap
        tex.uvwgen = uvwgen
        
        vray_plug[param_name] = tex
        
    def _update_tex(self, vray_plug, param_name, tex_path):
        tex_param = vray_plug[param_name]
        
        # temporary fix, until vray gets fixed
        if param_name == "dome_tex":
            vray_plug.use_dome_tex = (tex_path != "")
        if param_name == "rect_tex":
            vray_plug.use_rect_tex = (tex_path != "")
            
        if tex_param is None and tex_path:
            self._create_tex(vray_plug, param_name, tex_path)
            return True
        elif tex_param:
            if not tex_path:
                self._delete_tex(vray_plug, param_name)
                return True
            else:
                if tex_param.bitmap:
                    old_path = tex_param.bitmap.file
                    if old_path != tex_path:
                        vray_plug[param_name].bitmap.file = tex_path
                        return True
                    return False
        
    def update_custom_prop(self, prop, vray_plug, param_name, type_name):
        try:
            param = vray_plug[param_name]
        except:
            return False
        
        if type_name == "bool":
            if bool(prop.Data) != param:
                vray_plug[param_name] = bool(prop.Data)
                return True
        elif type_name == "int":
            if int(prop.Data) != param:
                vray_plug[param_name] = int(prop.Data)
                return True
        elif type_name == "float":
            if not eps_equal(float(prop.Data), param):
                vray_plug[param_name] = float(prop.Data)
                return True
        elif type_name == "color":
            vray_color = list(param)
            mobu_color = list(prop.Data)
            equal = True
            for i in xrange(3):
                if not eps_equal(mobu_color[i], vray_color[i]):
                    return False
            vray_plug[param_name] = vray.Color(*mobu_color)
            return True
        elif type_name == "texture":
            return self._update_tex(vray_plug, param_name, prop.Data)
        return False
    
    def _init_cam_props(self, cam):
        if cam.PropertyList.Find("[V] Use Physical"):
            # already initialized, but fix enum after loading from file
            prop = cam.PropertyList.Find("[V] Type")
            enumlist = prop.GetEnumStringList(True)
            if len(enumlist) == 0:
                for name in ["Still", "Movie", "Video"]:
                    enumlist.Add(name)
                prop.NotifyEnumStringListChanged()
            return
        
        user = False
        cam.PropertyCreate("[V] Use Physical", FBPropertyType.kFBPT_bool, 'Bool', False, user, None)
        
        prop = cam.PropertyCreate("[V] Type", FBPropertyType.kFBPT_enum, 'Enum', False, user, None)
        enumlist = prop.GetEnumStringList(True)
        for name in ["Still", "Movie", "Video"]:
            enumlist.Add(name)
        prop.NotifyEnumStringListChanged()
        
        fangle_prop = cam.PropertyList.Find("Focus Angle")
        cam.PropertyCreate("[V] F-Number", FBPropertyType.kFBPT_Reference, 'Reference', False, user, fangle_prop)
        
        prop = cam.PropertyCreate("[V] Shutter Speed", FBPropertyType.kFBPT_float, 'Float', False, user, None)
        prop.SetMin(0.0, True)
        prop.Data = 300.0
        prop = cam.PropertyCreate("[V] Shutter Angle", FBPropertyType.kFBPT_float, 'Float', False, user, None)
        prop.SetMin(0.0, True)
        prop.SetMax(360.0, True)
        prop.Data = 180.0
        prop = cam.PropertyCreate("[V] Shutter Offset", FBPropertyType.kFBPT_float, 'Float', False, user, None)
        prop.SetMin(-360.0, True)
        prop.SetMax(360.0, True)
        prop = cam.PropertyCreate("[V] Latency", FBPropertyType.kFBPT_float, 'Float', False, user, None)
        prop.SetMin(0.0, True)
        prop = cam.PropertyCreate("[V] Vignetting", FBPropertyType.kFBPT_float, 'Float', False, user, None)
        prop.SetMin(0.0, True)
        prop.Data = 1.0
        prop = cam.PropertyCreate("[V] Exposure Correction", FBPropertyType.kFBPT_bool, 'Bool', False, user, None)
        prop.Data = True
        prop = cam.PropertyCreate("[V] ISO", FBPropertyType.kFBPT_int, 'Integer', False, user, None)
        prop.SetMin(1.0, True)
        prop.Data = 200
        prop = cam.PropertyCreate("[V] White Balance", FBPropertyType.kFBPT_ColorRGB, 'Color', False, user, None)
        prop.Data = FBColor(1.0, 1.0, 1.0)
        prop = cam.PropertyCreate("[V] Use Blades", FBPropertyType.kFBPT_bool, 'Bool', False, user, None)
        prop = cam.PropertyCreate("[V] Number of Blades", FBPropertyType.kFBPT_int, 'Integer', False, user, None)
        prop.SetMin(0, True)
        prop.Data = 5
        prop = cam.PropertyCreate("[V] Blades Rotation", FBPropertyType.kFBPT_float, 'Float', False, user, None)
        prop = cam.PropertyCreate("[V] Center Bias", FBPropertyType.kFBPT_float, 'Float', False, user, None)
        prop.SetMin(-100.0, True)
        prop.SetMax(100.0, True)
        prop = cam.PropertyCreate("[V] Anisotropy", FBPropertyType.kFBPT_float, 'Float', False, user, None)
        prop.SetMin(-1.0, True)
        prop.SetMax(1.0, True)
        prop = cam.PropertyCreate("[V] Horizontal Offset", FBPropertyType.kFBPT_float, 'Float', False, user, None)
        prop = cam.PropertyCreate("[V] Vertical Offset", FBPropertyType.kFBPT_float, 'Float', False, user, None)
        
    def on_camera_prop(self, plug, do_commit=True):
        if not self._renderer or plug.GetOwner() != self.cam:
            return
        
        if plug.Name == "[V] Use Physical" or self._use_phys_cam:
            self.cam = None
        
    def on_light_prop(self, plug, do_commit=True):
        if not self._renderer:
            return
        
        light = plug.GetOwner()
        try:
            plugin = self._nodes[light].plugin
        except:
            return
        
        vtype = light.PropertyList.Find("[V] V-Ray Type")
        if vtype is None:
            return
        
        if plug.Name in self._anylight_prop_dict and vtype.AsString() != "Sun":
            self.update_custom_prop(plug, plugin, *self._anylight_prop_dict[plug.Name])
        elif vtype.AsString() == "Dome" and plug.Name in self._domelight_prop_dict:
            self.update_custom_prop(plug, plugin, *self._domelight_prop_dict[plug.Name])
        elif vtype.AsString() == "Rectangle" and plug.Name in self._rectlight_prop_dict:
            self.update_custom_prop(plug, plugin, *self._rectlight_prop_dict[plug.Name])
        elif vtype.AsString() == "Sphere" and plug.Name in self._spherelight_prop_dict:
            self.update_custom_prop(plug, plugin, *self._spherelight_prop_dict[plug.Name])
        elif vtype.AsString() == "Directional" and plug.Name in self._directlight_prop_dict:
            self.update_custom_prop(plug, plugin, *self._directlight_prop_dict[plug.Name])
        elif vtype.AsString() == "Sun" and plug.Name in self._sunlight_prop_dict:
            self.update_custom_prop(plug, plugin, *self._sunlight_prop_dict[plug.Name])
        else:
            do_commit = False
            
        if do_commit:
            self._renderer.commit()
    