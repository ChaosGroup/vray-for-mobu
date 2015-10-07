import time

from pyfbsdk import *
from pyfbsdk_additions import *

from gui import WidgetHolder
from gui import on_action_button
from exporter import VRay4MobuExporter # for cam props


class VRayForMoBu(FBTool):
    
    def __init__(self):
        FBTool.__init__(self, "V-Ray")
        
        self.widgetHolder = WidgetHolder()
        self.BuildLayout()
        self.StartSizeX = 600
        self.StartSizeY = 400
        
    def BuildLayout(self):
        x = FBAddRegionParam(0, FBAttachType.kFBAttachLeft, "")
        y = FBAddRegionParam(0, FBAttachType.kFBAttachTop, "")
        w = FBAddRegionParam(0, FBAttachType.kFBAttachRight, "")
        h = FBAddRegionParam(0, FBAttachType.kFBAttachBottom, "")
        self.AddRegion("main", "main", x, y, w, h)
        self.SetControl("main", self.widgetHolder)

        
def gOnConnectionDataNotify(control, event):
    if event.Action != FBConnectionAction.kFBCandidated:
        return
    # this causes a crash on shutdown when accessing CurrentPaneCallbackIndex. Looks like another Mobu bug >.<
    # r = FBSystem().Scene.Renderer
    # if r.CurrentPaneCallbackIndex == -1 or r.RendererCallbacks[r.CurrentPaneCallbackIndex].Name != "VRayRT":
        # return
    if type(event.Plug) == FBPropertyAction:
        # this gets fired twice for some reason, so we need to skip the second call
        gOnConnectionDataNotify.action_count += 1
        if gOnConnectionDataNotify.action_count % 2:
            on_action_button(event.Plug)
    elif isinstance(event.Plug.GetOwner(), FBCamera):
        VRay4MobuExporter().on_camera_prop(event.Plug)
    elif isinstance(event.Plug.GetOwner(), FBLight):
        VRay4MobuExporter().on_light_prop(event.Plug)

gOnConnectionDataNotify.action_count = 0

def gRegisterHandlers():    
    FBSystem().OnConnectionDataNotify.Add(gOnConnectionDataNotify)
    FBApplication().OnFileExit.Add(gUnregisterHandlers)

def gUnregisterHandlers(control=None, event=None):
    FBSystem().OnConnectionDataNotify.Remove(gOnConnectionDataNotify)
    FBApplication().OnFileExit.Remove(gUnregisterHandlers)

    
    
def gMain():    
    time.clock() # init
    vfmobu = VRayForMoBu()
    FBAddTool(vfmobu)
    ShowTool(vfmobu)
    
    
gRegisterHandlers()

#if True or __name__ == "__main__":
FBDestroyToolByName("V-Ray")
gMain()
