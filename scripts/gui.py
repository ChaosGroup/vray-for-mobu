import os, sys, threading

from pyfbsdk import *
from pyfbsdk_additions import *
import pythonidelib as pil

import vray

from PySide import QtCore
from PySide import QtGui
from PySide import shiboken

from utilities import *
from exporter import VRay4MobuExporter
from blank_preview import blank_preview_b64
from renderer import *

# these will be rediricted to our window
orig_stdout = sys.stdout
orig_stderr = sys.stderr

the_window = None


def on_action_button(plug):
    if plug.Name == "[V] Tex Browse...":
        on_tex_browse(plug.GetOwner())
    
    # check if we have a running renderer
    if not the_window or not the_window.vray_renderer or not the_window.vray_renderer.vray_renderer or the_window.vray_renderer.vray_renderer.closed:
        return
    
    if plug.Name == "[V] Load session...":
        the_window.on_loadsession()
    if plug.Name == "[V] Save session...":
        the_window.on_savesession()
    if plug.Name == "[V] Append scene...":
        the_window.on_append()
    if plug.Name == "[V] Choose MtlMulti...":
        the_window.on_mtlmulti()
    if plug.Name == "[V] Apply VRmat (vrscene) material...":
        the_window.on_vrmat()
    if plug.Name == "[V] Create light...":
        the_window.on_lights()
    if plug.Name == "[V] Show/Hide VFB":
        the_window.on_vfb()
    if plug.Name == "[V] Export vrscene":
        the_window.on_export_file()
    
def on_tex_browse(node):
    vtype = node.PropertyList.Find("[V] V-Ray Type")
    tex_prop = node.PropertyList.Find("[V] Tex Filepath")
    if vtype is None or tex_prop is None:
        return
    
    popup = FBFilePopup()
    popup.Caption = "Choose texture file"
    popup.Path = str(on_tex_browse.last_path)
    popup.Filter = "*.exr;*.png;*.bmp;*.tga;*.hdr;*.jpg;*.jpeg;*.pic;*.tif;*.tiff;*.psd;*.vrimg;*.sgi;*.rgb;*.rgba;*.dds"
    popup.FileName = str(tex_prop.Data)
    accepted = popup.Execute()
    if not accepted or not popup.FileName:
        return
    
    on_tex_browse.last_path = popup.Path
    tex_prop.Data = popup.FullFilename
    
on_tex_browse.last_path = ""

def _model_cmp(a, b):
    if a.mobu_obj.Name < b.mobu_obj.Name:
        return -1
    elif a.mobu_obj.Name == b.mobu_obj.Name:
        return 0
    else:
        return 1
    
class VRMatDialog(QtGui.QDialog):

    last_dir = QtCore.QDir()

    def __init__(self, renderer, parent=None):
        super(VRMatDialog, self).__init__(parent)

        self.renderer = renderer

        self._init_widgets()

        self.models = self.renderer.exporter.get_models()
        self.models.sort(_model_cmp)
        names = [model.mobu_obj.Name for model in self.models]
        self._name_list.addItems(names)
        self.on_selected_material() # set blank preview

    def _init_widgets(self):
        self._name_list = QtGui.QListWidget()
        self._mat_list = QtGui.QListWidget()
        self._browse_btn = QtGui.QPushButton("Browse...")
        self._mat_name_label = QtGui.QLabel("")
        self._mat_thumb_label = QtGui.QLabel("")
        self._accept_btn = QtGui.QPushButton("Apply")
        self._reject_btn = QtGui.QPushButton("Close")

        self._mat_thumb_label.setSizePolicy(QtGui.QSizePolicy.Minimum, QtGui.QSizePolicy.Minimum)
        self._mat_thumb_label.resize(128, 128)
        self._mat_name_label.setMaximumWidth(200)
        self._name_list.setSelectionMode(QtGui.QAbstractItemView.ExtendedSelection)
        self._mat_list.setSelectionMode(QtGui.QAbstractItemView.SingleSelection)

        QtCore.QObject.connect(self._browse_btn, QtCore.SIGNAL("pressed()"), self.on_browse)
        QtCore.QObject.connect(self._accept_btn, QtCore.SIGNAL("pressed()"), self.on_accept)
        QtCore.QObject.connect(self._reject_btn, QtCore.SIGNAL("pressed()"), self.on_reject)
        QtCore.QObject.connect(self._mat_list, QtCore.SIGNAL("itemSelectionChanged()"), self.on_selected_material)

        btn_layout = QtGui.QHBoxLayout()
        btn_layout.addWidget(self._accept_btn)
        btn_layout.addWidget(self._reject_btn)
        
        browse_layout = QtGui.QVBoxLayout()
        browse_layout.addStretch()
        browse_layout.addWidget(self._browse_btn)
        browse_layout.addWidget(self._mat_name_label)
        
        file_layout = QtGui.QHBoxLayout()
        file_layout.addWidget(self._mat_thumb_label)
        file_layout.addLayout(browse_layout)
        
        vrmat_layout = QtGui.QVBoxLayout()
        vrmat_layout.addLayout(file_layout)
        vrmat_layout.addWidget(self._mat_list)
        vrmat_layout.addLayout(btn_layout)

        layout = QtGui.QHBoxLayout()
        layout.addWidget(self._name_list)
        layout.addLayout(vrmat_layout)

        self.setLayout(layout)
        self.setWindowTitle("VRmat dialog")

    def on_browse(self):
        popup = FBFilePopup()
        popup.Caption = "Open VRmat or vrscene"
        popup.Path = str(VRMatDialog.last_dir.dirName())
        popup.Filter = "*.vrmat;*.vismat;*.vrscene"
        popup.FileName = ""
        accepted = popup.Execute()
        if not accepted or not popup.FileName:
            return
        filename = popup.FullFilename
        VRMatDialog.last_dir = QtCore.QDir(filename)
        self._mat_name_label.setText(filename)
        self._mat_name_label.setToolTip(filename)
        
        matnames = []
        if filename:
            vrmat = vray.VRMat(str(filename))
            matnames = vrmat.getMaterialList()
        self._mat_list.clear()
        self._mat_list.addItems(matnames)
        if matnames:
            self._mat_list.setCurrentRow(0)
        
    def on_selected_material(self):
        filename = self._mat_name_label.text()
        matname = ""
        if self._mat_list.selectedItems():
            matname = self._mat_list.selectedItems()[0].text()
        
        encoded_png = None
        if filename:
            vrmat = vray.VRMat(str(filename))
            encoded_png = vrmat.getEncodedThumbnail(matname)
        
        if not encoded_png:
            encoded_png = blank_preview_b64
        image_array = QtCore.QByteArray().fromBase64(encoded_png)
        image = QtGui.QPixmap()
        image.loadFromData(image_array, "PNG")
        self._mat_thumb_label.setPixmap(image)

    def on_accept(self):
        selection = []
        for i in xrange(self._name_list.count()):
            if self._name_list.item(i).isSelected():
                selection.append(self.models[i])
        filename = self._mat_name_label.text()
        matname = ""
        matname_sel = self._mat_list.selectedItems()
        if matname_sel:
            matname = matname_sel[0].text()
        if selection and filename and matname:
            self.renderer.apply_vrmat_many(selection, filename, matname)
        #self.accept()
    
    def on_reject(self):
        self.reject()


class MtlMultiDialog(QtGui.QDialog):

    def __init__(self, renderer, parent=None):
        super(MtlMultiDialog, self).__init__(parent)

        self.renderer = renderer

        self._init_widgets()

        self.models = self.renderer.exporter.get_models()
        self.models.sort(_model_cmp)
        names = [model.mobu_obj.Name for model in self.models]
        self._name_list.addItems(names)
        
        multis = self.renderer.vray_renderer.classes.MtlMulti.getInstances()
        self.multi_names = None
        if multis:
            self.multi_names = [m.getName() for m in multis]
            self._mat_list.addItems(self.multi_names)
        else:
            #QtGui.QMessageBox.information(self, "Notice", "No MtlMulti in the scene\nTry appending a .vrscene")
            print "No MtlMulti in the scene. Try appending a .vrscene"
            self._accept_btn.setEnabled(False)

    def _init_widgets(self):
        self._name_list = QtGui.QListWidget()
        self._mat_list = QtGui.QListWidget()
        self._accept_btn = QtGui.QPushButton("Apply")
        self._reject_btn = QtGui.QPushButton("Close")

        self._name_list.setSelectionMode(QtGui.QAbstractItemView.ExtendedSelection)
        self._mat_list.setSelectionMode(QtGui.QAbstractItemView.SingleSelection)

        QtCore.QObject.connect(self._accept_btn, QtCore.SIGNAL("pressed()"), self.on_accept)
        QtCore.QObject.connect(self._reject_btn, QtCore.SIGNAL("pressed()"), self.on_reject)

        btn_layout = QtGui.QHBoxLayout()
        btn_layout.addWidget(self._accept_btn)
        btn_layout.addWidget(self._reject_btn)
        
        mat_layout = QtGui.QVBoxLayout()
        mat_layout.addWidget(self._mat_list)
        mat_layout.addLayout(btn_layout)

        layout = QtGui.QHBoxLayout()
        layout.addWidget(self._name_list)
        layout.addLayout(mat_layout)

        self.setLayout(layout)
        self.setWindowTitle("MtlMulti dialog")

    def on_accept(self):
        selection = []
        for i in xrange(self._name_list.count()):
            if self._name_list.item(i).isSelected():
                selection.append(self.models[i])
        matname = None
        if self._mat_list.currentItem():
            matname = self._mat_list.currentItem().text()
        if selection and matname:
            self.renderer.apply_multimat_many(selection, matname)
        #self.accept()
    
    def on_reject(self):
        self.reject()


class LightsDialog(QtGui.QDialog):

    def __init__(self, renderer, parent=None):
        super(LightsDialog, self).__init__(parent)

        self.renderer = renderer

        self._init_widgets()

    def _init_widgets(self):
        self._accept_btn = QtGui.QPushButton("Create")
        self._reject_btn = QtGui.QPushButton("Cancel")
        
        QtCore.QObject.connect(self._accept_btn, QtCore.SIGNAL("pressed()"), self.on_accept)
        QtCore.QObject.connect(self._reject_btn, QtCore.SIGNAL("pressed()"), self.on_reject)

        btn_layout = QtGui.QHBoxLayout()
        btn_layout.addWidget(self._accept_btn)
        btn_layout.addWidget(self._reject_btn)

        self._type_combo = QtGui.QComboBox()
        self._type_combo.addItems(["Dome", "Rectangle", "Sphere", "Directional", "Sun"])
        self._name_field = QtGui.QLineEdit()
        self._name_field.setPlaceholderText("Type name here")
        self._sel_cbox = QtGui.QCheckBox("Select")
        self._sel_cbox.setChecked(True)

        layout = QtGui.QVBoxLayout()
        layout.addWidget(self._type_combo)
        layout.addWidget(self._name_field)
        layout.addWidget(self._sel_cbox)
        layout.addLayout(btn_layout)

        self.setLayout(layout)
        self.setWindowTitle("Create V-Ray light")

    def on_accept(self):
        type_ = self._type_combo.currentText()
        name = str(self._name_field.text())
        do_sel = self._sel_cbox.isChecked()
        self.renderer.create_light(type_, name, do_sel)
        self.accept()
    
    def on_reject(self):
        self.reject()


class VRayWindow(QtGui.QFrame):
    def __init__(self, parent=None):
        super(VRayWindow, self).__init__(parent)
        
        self.main_thread = threading.current_thread()
        self.vray_renderer = None
        
        self.show_vray_log = False
        self.text_queue = []
        self.text_queue_lock = threading.Lock()
        
        self.last_session_path = ""
        self.last_append_path = ""
        self.last_export_path = ""
        
        self._text_edit = QtGui.QPlainTextEdit()
        self._fps_meter = QtGui.QProgressBar()
        self._frame_counter = QtGui.QProgressBar()
        self._show_vray_log_cbox = QtGui.QCheckBox("V-Ray Log")
        
        QtCore.QObject.connect(self._show_vray_log_cbox, QtCore.SIGNAL("stateChanged(int)"), self.on_vray_log)
        
        self._text_edit.setMinimumSize(QtCore.QSize(120, 50))
        self._text_edit.setReadOnly(True)
        self._text_edit.setFont(QtGui.QFont("Monospace"))
        self._fps_meter.setRange(0, 60)
        self._fps_meter.setFormat("%v FPS")
        self._fps_meter.setMaximumWidth(240)
        self._fps_meter.setValue(0)
        self._frame_counter.setRange(0, 4000)
        self._frame_counter.setFormat("%v F/min")
        self._frame_counter.setMaximumWidth(240)
        self._frame_counter.setValue(0)
        
        self._layout = QtGui.QGridLayout()
        self._layout.addWidget(self._fps_meter, 0, 0)
        self._layout.addWidget(self._frame_counter, 0, 1)
        self._layout.addWidget(self._show_vray_log_cbox, 0, 2)
        
        self._layout.addWidget(self._text_edit, 1, 0, -1, -1)
        
        self._layout.setColumnStretch(0, 1)
        self._layout.setColumnStretch(1, 1)
        self._layout.setColumnStretch(2, 3)
        self._layout.setRowStretch(1, 1)
        
        self.setLayout(self._layout)
        #self.resize(500, 500)
        
        sys.stdout = sys.stderr = self
        
        self.on_attach()
    
    def closeEvent(self, event):
        self.on_detach()
        sys.stdout = orig_stdout
        sys.stderr = orig_stderr
        #print "[debug] reset std{out|err}"
        event.accept()
    
    def on_attach(self):
        if self.vray_renderer is None:
            self.vray_renderer = VRayRenderCallback("VRayRT")
            self.vray_renderer.framecount_callback = self.set_framecount
            self.vray_renderer.framerate_callback = self.set_framerate
        r = FBSystem().Renderer
        r.RendererCallbacks.append(self.vray_renderer)
        r.CurrentPaneCallbackIndex = len(r.RendererCallbacks) - 1
    
    def on_detach(self):
        if self.vray_renderer is not None:
            r = FBSystem().Renderer
            r.RendererCallbacks.remove(self.vray_renderer)
            r.CurrentPaneCallbackIndex = len(r.RendererCallbacks) - 1
            self.vray_renderer.Detach() # FB doesnt do it. why?!
            self.vray_renderer.FBDelete()
            self.vray_renderer = None
        self.set_framerate(0)
        
    def on_append(self):
        fp = FBFilePopup()
        fp.Style = FBFilePopupStyle.kFBFilePopupOpen
        fp.Caption = "Scene to append"
        fp.Filter = "*.vrscene"
        fp.Path = self.last_append_path
        accepted = fp.Execute()
        if accepted:
            self.last_append_path = fp.Path
        if self.vray_renderer and fp.FullFilename:
            self.vray_renderer.append_scene(fp.FullFilename)

    def on_mtlmulti(self):
        dlg = MtlMultiDialog(self.vray_renderer, self)
        dlg.setWindowModality(QtCore.Qt.WindowModal)
        dlg.show()

    def on_vrmat(self):
        dlg = VRMatDialog(self.vray_renderer, self)
        dlg.setWindowModality(QtCore.Qt.WindowModal)
        dlg.show()
        
    def on_lights(self):
        dlg = LightsDialog(self.vray_renderer, self)
        dlg.setWindowModality(QtCore.Qt.WindowModal)
        dlg.show()

    def on_vfb(self):
        if self.vray_renderer:
            self.vray_renderer.toggleVFB()
            
    def on_export_file(self):
        if self.vray_renderer:
            fp = FBFilePopup()
            fp.Style = FBFilePopupStyle.kFBFilePopupSave
            fp.Caption = "Export vrscene file"
            fp.Filter = "*.vrscene"
            fp.Path = self.last_export_path
            accepted = fp.Execute()
            if accepted:
                self.last_export_path = fp.Path
            if self.vray_renderer and fp.FullFilename:
                self.vray_renderer.export_file(fp.FullFilename)
            
    def set_framerate(self, fps):
        self._fps_meter.setValue(min(max(0, fps), 60))
        
    def set_framecount(self, count):
        self._frame_counter.setValue(count)

    def on_vray_log(self, state):
        self.show_vray_log = (state == QtCore.Qt.Checked)
        
    def on_savesession(self):
        if self.vray_renderer is None:
            return
        popup = FBFilePopup()
        popup.Caption = "Save Session"
        popup.Path = self.last_session_path
        popup.Filter = "*.json"
        popup.FileName = ""
        popup.Style = FBFilePopupStyle.kFBFilePopupSave
        accepted = popup.Execute()
        if not accepted or not popup.FileName:
            return
        self.last_session_path = popup.Path
        self.vray_renderer.save_session(popup.FullFilename)
        
    def on_loadsession(self):
        if self.vray_renderer is None:
            return
        popup = FBFilePopup()
        popup.Caption = "Load Session"
        popup.Path = self.last_session_path
        popup.Filter = "*.json"
        popup.FileName = ""
        accepted = popup.Execute()
        if not accepted or not popup.FileName:
            return
        self.last_session_path = popup.Path
        self.vray_renderer.load_session(popup.FullFilename)
        
    def write(self, text):
        if threading.current_thread() is self.main_thread:
            self._text_edit.moveCursor(QtGui.QTextCursor.End)
            if self.show_vray_log:
                with self.text_queue_lock:
                    for t in self.text_queue:
                        self._text_edit.insertPlainText(t)
                    self.text_queue = []
            self._text_edit.insertPlainText(text)
            self._text_edit.ensureCursorVisible()
            self._text_edit.update()
        elif self.show_vray_log:
            with self.text_queue_lock:
                self.text_queue.append(text)
        print >> orig_stdout, text,
        #pil.FlushOutput()


class WidgetHolder(FBWidgetHolder):
    def WidgetCreate(self, widgetParent):
        global the_window
        self.widget = VRayWindow(shiboken.wrapInstance(widgetParent, QtGui.QWidget))
        the_window = self.widget
        return shiboken.getCppPointer(self.widget)[0]
        