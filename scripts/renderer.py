import os, sys, threading, time, json
from multiprocessing import cpu_count

from pyfbsdk import *
from pyfbsdk_additions import *
import pythonidelib as pil

import vray

from utilities import *
from exporter import VRay4MobuExporter
# we use the 'accel' native module because PyOpenGL proved very slow
import accel


class VRayRenderCallback(FBRendererCallback):
    """Renders in the MoBu viewport using V-Ray RT
    
    Images received from V-Ray RT are blitted on the viewport as OpenGL textures
    """
    
    light_type_strings = ["Dome", "Rectangle", "Sphere", "Directional", "Sun"]
    
    def __init__(self, name):
        super(VRayRenderCallback, self).__init__(name)
        
        size = accel.getViewportSize() # getting this from the MoBu GL widget didn't give correct results
        self.img_width = max(16, size[0])
        self.img_height = max(16, size[1])
        self.use_fixed_res = False
        self.relative_res = 1.0
        self.last_resize_check_time = time.clock()
        self.updates_blocked = False
        self.session = Session()
        
        self.counter = 0
        self.last_presented_image = 0
        self.lock = threading.Lock()
        
        self._init_custom_props()
        
        FBSystem().OnConnectionDataNotify.Add(self.OnConnectionDataNotify)
        FBApplication().OnFileExit.Add(self._unregister)
    
    def _init_custom_props(self):
        user = False # True won't work unlike with lights
        
        p = self.PropertyCreate("[V] Motion updates/sec", FBPropertyType.kFBPT_int, 'Integer', False, user, None)
        p.SetMin(10, True)
        p.SetMax(100, True)
        p.Data = 60
        p = self.PropertyCreate("[V] Object updates/sec", FBPropertyType.kFBPT_int, 'Integer', False, user, None)
        p.SetMin(1, True)
        p.SetMax(10, True)
        p.Data = 4
        
        p = self.PropertyCreate("[V] Trace depth", FBPropertyType.kFBPT_int, 'Integer', False, user, None)
        p.SetMin(0, True)
        p.SetMax(32, True)
        p.Data = 5
        p = self.PropertyCreate("[V] GI depth", FBPropertyType.kFBPT_int, 'Integer', False, user, None)
        p.SetMin(0, True)
        p.SetMax(32, True)
        p.Data = 1
        p = self.PropertyCreate("[V] Samples per pixel", FBPropertyType.kFBPT_int, 'Integer', False, user, None)
        p.SetMin(1, True)
        p.SetMax(256, True)
        p.Data = 1
        p = self.PropertyCreate("[V] Bundle size", FBPropertyType.kFBPT_int, 'Integer', False, user, None)
        p.SetMin(32, True)
        p.SetMax(8196, True)
        p.Data = 256
        self.PropertyCreate("[V] Coherent tracing", FBPropertyType.kFBPT_bool, 'Bool', False, user, None)
        # sampling/time/noise limit?
        self.PropertyCreate("[V] Progressive SPP", FBPropertyType.kFBPT_bool, 'Bool', False, user, None)
        # resize tex?
        
        self.PropertyCreate("[V] Block updates", FBPropertyType.kFBPT_bool, 'Bool', False, user, None)
        
        prop = self.PropertyCreate("[V] Resolution mode", FBPropertyType.kFBPT_enum, 'Enum', False, user, None)
        enumlist = prop.GetEnumStringList(True)
        for name in ["Viewport relative", "Fixed"]:
            enumlist.Add(name)
        prop.NotifyEnumStringListChanged()
        
        p = self.PropertyCreate("[V] Viewport % resolution", FBPropertyType.kFBPT_int, 'Integer', False, user, None)
        p.SetMin(10, True)
        p.SetMax(200, True)
        p.Data = 100
        self.PropertyCreate("[V] Fixed resolution width", FBPropertyType.kFBPT_int, 'Integer', False, user, None)
        self.PropertyCreate("[V] Fixed resolution height", FBPropertyType.kFBPT_int, 'Integer', False, user, None)
        
        self.PropertyCreate("[V] Load session...", FBPropertyType.kFBPT_Action, 'Action', False, user, None)
        self.PropertyCreate("[V] Save session...", FBPropertyType.kFBPT_Action, 'Action', False, user, None)
        self.PropertyCreate("[V] Append scene...", FBPropertyType.kFBPT_Action, 'Action', False, user, None)
        self.PropertyCreate("[V] Choose MtlMulti...", FBPropertyType.kFBPT_Action, 'Action', False, user, None)
        self.PropertyCreate("[V] Apply VRmat (vrscene) material...", FBPropertyType.kFBPT_Action, 'Action', False, user, None)
        self.PropertyCreate("[V] Create light...", FBPropertyType.kFBPT_Action, 'Action', False, user, None)
        self.PropertyCreate("[V] Show/Hide VFB", FBPropertyType.kFBPT_Action, 'Action', False, user, None)
        self.PropertyCreate("[V] Export vrscene", FBPropertyType.kFBPT_Action, 'Action', False, user, None)
        
        p = self.PropertyCreate("[V] Meters scale", FBPropertyType.kFBPT_double, 'Number', False, user, None)
        p.SetMin(0.0, True)
        p.Data = 1.0
        p = self.PropertyCreate("[V] Photometric scale", FBPropertyType.kFBPT_double, 'Number', False, user, None)
        p.SetMin(0.0, True)
        p.Data = 0.001
        p = self.PropertyCreate("[V] Seconds scale", FBPropertyType.kFBPT_double, 'Number', False, user, None)
        p.SetMin(0.0, True)
        p.Data = 1.0
    
    def _unregister(self, control=None, event=None):
        FBSystem().OnConnectionDataNotify.Remove(self.OnConnectionDataNotify)
        FBApplication().OnFileExit.Remove(self._unregister)
    
    def OnConnectionDataNotify(self, control, event):
        if event.Action == FBConnectionAction.kFBCandidated and event.Plug.GetOwner() is self:
            name = str(event.Plug.Name)[4:]
            if name in ["Resolution mode", "Viewport % resolution", "Fixed resolution width", "Fixed resolution height"]:
                self.on_resolution()
            elif name in ["Trace depth", "GI depth", "Samples per pixel", "Bundle size", "Coherent tracing", "Progressive SPP"]:
                self.on_rt_settings()
            elif name in ["Meters scale", "Photometric scale", "Seconds scale"]:
                self.on_units()
            elif name in ["Motion updates/sec", "Object updates/sec"]:
                self.on_intervals()
            elif name == "Block updates":
                self.updates_blocked = event.Plug.Data
    
    def GetCallbackName(self):
        return "VRayRT"
    
    def GetCallbackDesc(self):
        return "V-Ray RT renderer"
    
    def GetCallbackPrefCount(self):
        return 1
    
    def GetCallbackPrefName(self, pIndex):
        return "GPU"
    
    def Attach(self):
        #print "[debug] attach"
        self.start_renderer()
        #print "[debug] end attach"

    def Detach(self):
        #print "[debug] detach"
        self.stop_renderer()
        self.exporter = None
        self.session = Session()
    
    def DetachDisplayContext(self, options):
        #print "[debug] detachDisplayContext"
        #self.stop_renderer()
        #r = FBSystem().Renderer
        #r.CurrentPaneCallbackIndex = -1
        #r.CurrentPaneCallbackIndex = len(r.RendererCallbacks) - 1
        pass
    
    def Render(self, options):
        if not self.updates_blocked:
            self.exporter.export()
        
        time_now = time.clock()
        if time_now > self.last_resize_check_time + 0.1:
            # only doing this once in a while, because it's kinda slow
            self.last_resize_check_time = time_now
            self.update_size()
        if self.the_image is None:
            return
        
        with self.lock:
            if self.counter > self.last_presented_image:
                time_now = time.clock()
                interval = time_now - self.last_present_time
                self.last_present_time = time_now
                self.last_frame_intervals.insert(0, interval)
                self.last_frame_intervals = self.last_frame_intervals[:self._get_fps_window_size()]
                
                last = 0
                self._frame_times.append(time_now)
                for x in xrange(len(self._frame_times)):
                    if time_now - self._frame_times[x] > 60.0:
                        last = x
                    else:
                        break
                self._frame_times = self._frame_times[last:]
                self.framecount_callback(len(self._frame_times))

                accel.updateTex(self.the_image)
                self.last_presented_image = self.counter
                #print "[debug] render frame %d (fps %f)" % (self.counter, self._get_fps())
                self.framerate_callback(self._get_fps())
        
        accel.blitImage()
    
    def _get_fps(self):
        interval_count = len(self.last_frame_intervals)
        if interval_count == 0:
            return 0
            
        timesum = 0.0
        for i in self.last_frame_intervals:
            timesum += i
        return interval_count / timesum
        
    def _get_fps_window_size(self):
        fps = self._get_fps()
        # about 0.25s window
        return max(1, int(fps / 4))
        
    def create_renderer(self):
        self.release_renderer()
        
        if self.use_fixed_res:
            w = self.fixed_width
            h = self.fixed_height
        else:
            w = self.img_width
            h = self.img_height
        
        mode = "rtGPU"
        # 1 thread is at 100% for the render loop and leave 1 free for the user
        # the max 8 limit is because we've found RT GPU performance degrades with too many threads (i.e. 24)
        num_threads = min(max(cpu_count() - 2, 1), 8)
        self.vray_renderer = vray.VRayRenderer(renderMode=mode, inProcess=True, \
            numThreads=num_threads, imageWidth=w, imageHeight=h, \
            rtNoiseThreshold=0, rtSampleLevel=0, keepRTRunning=True)
        
        # if we don't show it initially, we wouldn't be able to later (bug)
        self.vray_renderer.showFrameBuffer = True
        # we set many things each frame, so commit manually in one go for performance
        self.vray_renderer.autoCommit = False
        
        self.vray_renderer.setOnRtImageUpdated(gOnImageUpdated)
        self.vray_renderer.setOnRenderStart(gOnRenderStart)
        self.vray_renderer.setOnDumpMessage(gOnDumpMessage)
        
        self.exporter = VRay4MobuExporter()
        self.on_intervals()
        self.exporter.set_renderer(self.vray_renderer)
        
    def release_renderer(self):
        self.the_image = None
        self.exporter = None
        self.vray_renderer = None
        self.renderer_ready = False
        
    def start_renderer(self):
        #print "[debug] starting renderer"
        self.create_renderer()
        accel.initTex()

        # we need to instantiate this for later use
        settings_output = self.vray_renderer.classes.SettingsOutput()

        ui = self.vray_renderer.classes.SettingsUnitsInfo()
        ui.scene_upDir = vray.Vector(0.0, 1.0, 0.0)
        #ui.meters_scale = 0.0254;
        #ui.photometric_scale = 0.002094395;
        #ui.seconds_scale = 0.03333334;
        self.on_units()

        rs = self.vray_renderer.classes.SettingsRTEngine()
        rs.undersampling = 0
        rs.opencl_resizeTextures = 0 # enable if GPU RAM is not enough
        rs.disable_render_elements = 1
        rs.coherent_tracing = 0 # setting to 1 only makes sense with multiple SPP and interior GI
        self.on_rt_settings()

        self.last_present_time = time.clock()
        self.last_frame_intervals = []
        self._frame_times = []

        self.vray_renderer.setRTImageUpdateDifference(5.0)
        self.vray_renderer.setRTImageUpdateTimeout(200)
        self.vray_renderer.startSync()
        self.vray_renderer.showFrameBuffer = False
        
    def stop_renderer(self):
        #print "[debug] stopping renderer"
        if self.vray_renderer:
            self.vray_renderer.close()
            #print "[debug] closed:", self.vray_renderer.closed
        if self.exporter:
            self.exporter.clear()
        self.release_renderer()
        accel.releaseTex()
        
    def on_intervals(self):
        if not self.exporter:
            return
        
        prop = self.PropertyList.Find("[V] Motion updates/sec")
        if prop and prop.Data != 0:
            self.exporter.quick_update_interval = 1.0 / prop.Data
        prop = self.PropertyList.Find("[V] Object updates/sec")
        if prop and prop.Data != 0:
            self.exporter.full_update_interval = 1.0 / prop.Data
        
    def on_rt_settings(self):
        if not self.vray_renderer:
            return
        
        rs = self.vray_renderer.classes.SettingsRTEngine.getInstances()[0]
        prop = self.PropertyList.Find("[V] Trace depth")
        if prop:
            rs.trace_depth = prop.Data
        prop = self.PropertyList.Find("[V] GI depth")
        if prop:
            rs.gi_depth = prop.Data
        prop = self.PropertyList.Find("[V] Samples per pixel")
        if prop:
            rs.gpu_samples_per_pixel = prop.Data
        prop = self.PropertyList.Find("[V] Bundle size")
        if prop:
            rs.gpu_bundle_size = prop.Data
        prop = self.PropertyList.Find("[V] Coherent tracing")
        if prop:
            rs.coherent_tracing = prop.Data
        prop = self.PropertyList.Find("[V] Progressive SPP")
        if prop:
            rs.progressive_samples_per_pixel = prop.Data
            
        self.vray_renderer.commit()
        
    def on_units(self):
        if not self.vray_renderer:
            return
        
        ui = self.vray_renderer.classes.SettingsUnitsInfo.getInstances()[0]
        prop = self.PropertyList.Find("[V] Meters scale")
        if prop:
            ui.meters_scale = prop.Data
        prop = self.PropertyList.Find("[V] Photometric scale")
        if prop:
            ui.photometric_scale = prop.Data
        prop = self.PropertyList.Find("[V] Seconds scale")
        if prop:
            ui.seconds_scale = prop.Data
        
        self.exporter.reexport_cam() # physical camera is affected
        self.vray_renderer.commit()
        
    def on_resolution(self):
        type_prop = self.PropertyList.Find("[V] Resolution mode")
        if not type_prop:
            return
        if type_prop.AsString() == "Fixed":
            w = 0
            h = 0
            w_prop = self.PropertyList.Find("[V] Fixed resolution width")
            h_prop = self.PropertyList.Find("[V] Fixed resolution height")
            if w_prop and h_prop:
                w = int(w_prop.Data)
                h = int(h_prop.Data)
            if (w > 0 and h > 0):
                self.use_fixed_res = True
                self.fixed_width = w
                self.fixed_height = h
            else:
                print "Invalid resolution", w, "x", h
        else: # vp relative
            rel_prop = self.PropertyList.Find("[V] Viewport % resolution")
            if rel_prop:
                self.relative_res = rel_prop.Data / 100.0
                self.use_fixed_res = False
            
    def update_size(self):
        if not self.renderer_ready:
            return
        
        if self.use_fixed_res:
            size = (self.fixed_width, self.fixed_height)
        else:
            size = accel.getViewportSize()
            size = (int(size[0] * self.relative_res), int(size[1] * self.relative_res))
            
        width = max(16, size[0])
        height = max(16, size[1])
        if width != self.img_width or height != self.img_height:
            print "Resizing (",self.img_width,",",self.img_height,") to (",width,",",height,")"
            self.img_width = width
            self.img_height = height
            self.vray_renderer.size = (width, height)
    
    def update_image(self, image):
        with self.lock:
            self.the_image = image
            self.counter += 1
    
    def on_render_start(self):
        #print "[debug] render started"
        self.renderer_ready = True
        
    @staticmethod
    def _append_filter(renderer, typeName, instanceName):
        # Filter out geometry and settings plugins (including camera).
        # This is supposed to leave us with the lights and materials
        if typeName.endswith("Settings") or typeName.startswith("Settings") or typeName.startswith("Filter"):
            return False
        if typeName == "Node" or typeName == "GeomStaticMesh" or typeName == "RenderView" or typeName == "CameraPhysical":
            return False
        return True
        
    def append_scene(self, filename):
        if filename:
            print "Appending", filename, "..."
            self.vray_renderer.stop()
            #orig_plugins = [p for p in self.vray_renderer.plugins]
            self.vray_renderer.appendFiltered(filename, self._append_filter)
            self.vray_renderer.start()
            #new_plugins = [p for p in self.vray_renderer.plugins if p not in orig_plugins]
            self.session.appended_files.append(filename)
                    
    def toggleVFB(self):
        self.vray_renderer.showFrameBuffer = not self.vray_renderer.showFrameBuffer
        
    def apply_vrmat_many(self, selection, filename, matname):
        for item in selection:
            try: del self.session.applied_vrmats[item.mobu_obj.Name]
            except KeyError: pass
            try: del self.session.applied_multis[item.mobu_obj.Name]
            except KeyError: pass
            self.session.applied_vrmats[item.mobu_obj.Name] = (filename, matname)
        self.exporter.apply_vrmat(selection, filename, matname)

    def apply_multimat_many(self, selection, matname):
        for item in selection:
            try: del self.session.applied_vrmats[item.mobu_obj.Name]
            except KeyError: pass
            try: del self.session.applied_multis[item.mobu_obj.Name]
            except KeyError: pass
            self.session.applied_multis[item.mobu_obj.Name] = matname
        self.exporter.apply_multimtl(selection, matname)
        
    def block_updates(self, block):
        self.updates_blocked = block
        
    def save_session(self, filename):
        try:
            outfile = open(filename, 'w')
            json.dump(self.session.__dict__, outfile, indent=2)
            print outfile.name, "saved."
        except BaseException as e:
            print "Error saving session to", filename
            print e
        finally:
            outfile.close()
        
    def load_session(self, filename):
        try:
            infile = open(filename, 'r')
            readsess = json.load(infile)
            print infile.name, "loaded."
        except BaseException as e:
            print "Error reading session from", filename
            print e
        finally:
            infile.close()
        self._merge_session(readsess)
        
    def _merge_session(self, new_session):
        to_append = [af for af in new_session["appended_files"] if af not in self.session.appended_files]
        for scenefile in to_append:
            self.append_scene(scenefile)
            
        vrmats = {}
        for nodename, material in new_session["applied_vrmats"].items():
            pinfo = self.exporter.get_pinfo_by_name(nodename)
            if pinfo is None:
                print "Warning: Couldn't find node", nodename, "to apply vrmat", material[0]
            else:
                mat = (material[0], material[1])
                if mat in vrmats:
                    vrmats[mat] += [pinfo]
                else:
                    vrmats[mat] = [pinfo]
        for mat in vrmats.iterkeys():
            self.apply_vrmat_many(vrmats[mat], mat[0], mat[1])
                
        multis = {}
        for nodename, material in new_session["applied_multis"].items():
            pinfo = self.exporter.get_pinfo_by_name(nodename)
            if pinfo is None:
                print "Warning: Couldn't find node", nodename, "to apply multi material", material
            else:
                if material in multis:
                    multis[material] += [pinfo]
                else:
                    multis[material] = [pinfo]
        for m in multis.iterkeys():
            self.apply_multimat_many(multis[m], m)
        
    def create_light(self, typename, name, do_select):
        if not name:
            name = "V-Ray {0} Light".format(typename)
        light = FBLight(name)
        index = VRayRenderCallback.light_type_strings.index(typename)
        
        user = False
        prop = light.PropertyCreate("[V] V-Ray Type", FBPropertyType.kFBPT_enum, 'Enum', False, user, None)
        enumlist = prop.GetEnumStringList(True)
        for name in VRayRenderCallback.light_type_strings:
            enumlist.Add(name)
        prop.NotifyEnumStringListChanged()
        prop.Data = index
        prop.SetLocked(True) # mobu doesn't let us make this read-only
        
        # concrete values below are mostly V-Ray's defaults
        if typename == "Dome":
            light.Intensity = 1.0
            prop_tex = light.PropertyCreate("[V] Tex Filepath", FBPropertyType.kFBPT_charptr, 'String', False, user, None)
            prop_browse = light.PropertyCreate("[V] Tex Browse...", FBPropertyType.kFBPT_Action, 'Action', False, user, None)
            prop_spherical = light.PropertyCreate("[V] Spherical", FBPropertyType.kFBPT_bool, 'Bool', False, user, None)
        elif typename == "Rectangle":
            prop_tex = light.PropertyCreate("[V] Tex Filepath", FBPropertyType.kFBPT_charptr, 'String', False, user, None)
            prop_browse = light.PropertyCreate("[V] Tex Browse...", FBPropertyType.kFBPT_Action, 'Action', False, user, None)
            prop_usize = light.PropertyCreate("[V] U Size", FBPropertyType.kFBPT_float, 'Float', False, user, None)
            prop_vsize = light.PropertyCreate("[V] V Size", FBPropertyType.kFBPT_float, 'Float', False, user, None)
            prop_directional = light.PropertyCreate("[V] Directional", FBPropertyType.kFBPT_float, 'Float', False, user, None)
            prop_disc = light.PropertyCreate("[V] Is Disc", FBPropertyType.kFBPT_bool, 'Bool', False, user, None)
            prop_usize.Data = 20.0
            prop_vsize.Data = 20.0
        elif typename == "Sphere":
            prop_radius = light.PropertyCreate("[V] Radius", FBPropertyType.kFBPT_float, 'Float', False, user, None)
            prop_segments = light.PropertyCreate("[V] Segments", FBPropertyType.kFBPT_int, 'Integer', False, user, None)
            prop_radius.Data = 20.0
            prop_segments.Data = 20
            prop_segments.SetMin(4, True)
        elif typename == "Directional":
            light.Intensity = 1.0
        elif typename == "Sun":
            light.Intensity = 0.1 # 1.0 is too much if units haven't been set
            prop_turb = light.PropertyCreate("[V] Turbidity", FBPropertyType.kFBPT_float, 'Float', False, user, None)
            prop_ozone = light.PropertyCreate("[V] Ozone", FBPropertyType.kFBPT_float, 'Float', False, user, None)
            prop_vapor = light.PropertyCreate("[V] Vapor", FBPropertyType.kFBPT_float, 'Float', False, user, None)
            prop_sizemult = light.PropertyCreate("[V] Size multiplier", FBPropertyType.kFBPT_float, 'Float', False, user, None)
            prop_horizillum = light.PropertyCreate("[V] Horizontal illumination", FBPropertyType.kFBPT_float, 'Float', False, user, None)
            prop_colormode = light.PropertyCreate("[V] Color mode", FBPropertyType.kFBPT_int, 'Integer', False, user, None)
            prop_model = light.PropertyCreate("[V] Sky model", FBPropertyType.kFBPT_int, 'Integer', False, user, None)
            prop_turb.Data = 3.0
            prop_ozone.Data = 0.35
            prop_vapor.Data = 2.0
            prop_sizemult.Data = 1.0
            prop_horizillum.Data = 25000
            prop_colormode.Data = 0
            prop_model.Data = 0
        
        if do_select:
            clear_selection()
            light.Selected = True
        light.Show = True
        print typename, "Light object", repr(light.Name), "created", ["and selected." if do_select else "."][0]
        
    def export_file(self, filename):
        if not filename.endswith(".vrscene"):
            filename.append(".vrscene")
        export_settings = {}
        if self.vray_renderer.export(filename, export_settings):
            print "Exporting to", filename, "successful"
        else:
            print "Exporting to", filename, "failed"
    
    
def gGetVRayRTRenderer():
    r = None
    for item in FBSystem().Renderer.RendererCallbacks:
        if isinstance(item, VRayRenderCallback):
            r = item
    return r

def gOnRenderStart(renderer):
    r = gGetVRayRTRenderer()
    if r is not None:
        r.on_render_start()
    
def gOnImageUpdated(renderer, image):
    r = gGetVRayRTRenderer()
    if r is not None:
        r.update_image(image)
        
def gOnDumpMessage(renderer, msg, level):
    #debug_print_level = 19999
    debug_print_level = 100000 # all
    
    if level > debug_print_level:
        return
    
    gmt = time.gmtime()
    typestr = "?"
    if level < 10000:
        typestr = "ERROR"
    elif level < 20000:
        typestr = "Warning"
    elif level < 30000:
        typestr = "info"
    elif level < 40000:
        typestr = "debug"
        
    print "[{0:02d}:{1:02d}:{2:02d} VRay {3}] {4}".format(gmt.tm_hour, gmt.tm_min, gmt.tm_sec, typestr, msg.rstrip())
