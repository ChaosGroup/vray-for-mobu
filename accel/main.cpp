#include "Python.h"
#include "image.h"

#include <vector>
#include <algorithm>

#ifdef _WIN32
# include "windows.h"
#endif
#include "GL/GL.h"

#ifndef GL_FRAMEBUFFER_SRGB
# define GL_FRAMEBUFFER_SRGB 0x8DB9
#endif

GLuint g_tex = 0;

PyObject * initTex(PyObject* self, PyObject* args)
{
	glGenTextures(1, &g_tex);
	// todo return glgeterror status
	
	Py_RETURN_NONE;
}

PyObject * releaseTex(PyObject* self, PyObject* args)
{
	glDeleteTextures(1, &g_tex);
	g_tex = 0;
	// todo return glgeterror status
	
	Py_RETURN_NONE;
}

PyObject * updateTex(PyObject* self, PyObject* args)
{
	PyObject *imgObj;
	if (PyArg_ParseTuple(args, "O:updateTex", &imgObj)) {
		VRayPythonWrapper::Image *img = static_cast<VRayPythonWrapper::Image *>(imgObj);
		void *data = reinterpret_cast<void*>(((reinterpret_cast<uintptr_t>((img->imageNative)) + 15) & ~15) + 16); // <3 hacks
		// todo check g_tex
		glBindTexture(GL_TEXTURE_2D, g_tex);
		glTexImage2D(GL_TEXTURE_2D, 0, GL_RGBA, img->width, img->height, 0, GL_RGBA, GL_FLOAT, data);
		// todo glcheckerror
	}
	
	// todo return error status?
	Py_RETURN_NONE;
}

int _doBlit()
{
	/*static float quad_verts[] = {
		 1.0, -1.0, //-1.0,
		 1.0,  1.0, //-1.0,
		-1.0, -1.0, //-1.0,
		-1.0,  1.0, //-1.0
	};

	static float tex_verts[] = {
		1.0, 1.0,
		1.0, 0.0,
		0.0, 1.0,
		0.0, 0.0
	};*/
	
    glPushAttrib(GL_ALL_ATTRIB_BITS);
    glEnable(GL_FRAMEBUFFER_SRGB);
    glEnable(GL_TEXTURE_2D);
    //glDisable(GL_DEPTH_TEST);
    glDisable(GL_LIGHTING);
        
    glMatrixMode(GL_MODELVIEW);
    glPushMatrix();
    glLoadIdentity();
    glMatrixMode(GL_PROJECTION);
    glPushMatrix();
    glLoadIdentity();
        
    glBindTexture(GL_TEXTURE_2D, g_tex);
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR);
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR);
        
    glColor3f(1.0, 1.0, 1.0);
	/*glVertexPointer(2, GL_FLOAT, 0, quad_verts);
	glTexCoordPointer(2, GL_FLOAT, 0, tex_verts);
	glEnableClientState(GL_TEXTURE_COORD_ARRAY);
	glEnableClientState(GL_VERTEX_ARRAY);
	glDrawArrays(GL_TRIANGLE_STRIP, 0, 4);*/
    glBegin(GL_QUADS);
    glTexCoord2f(0.0, 0.0);  glVertex3f(-1.0,  1.0,  -1.0);
    glTexCoord2f(1.0, 0.0);  glVertex3f( 1.0,  1.0,  -1.0);
    glTexCoord2f(1.0, 1.0);  glVertex3f( 1.0, -1.0,  -1.0);
    glTexCoord2f(0.0, 1.0);  glVertex3f(-1.0, -1.0,  -1.0);
    glEnd();
        
    glPopMatrix();
    glMatrixMode(GL_MODELVIEW);
    glPopMatrix();
    glDisable(GL_FRAMEBUFFER_SRGB);
    glPopAttrib();

	return 0; // THIS IS EXTREMELY SLOW!!! glGetError();
}

PyObject * blitImage(PyObject* self, PyObject* args)
{
	// todo check g_tex
	_doBlit();
	
	Py_RETURN_NONE;
}

PyObject * getViewportSize(PyObject* self, PyObject* args)
{
	GLint size[4] = {0};
	glGetIntegerv(GL_VIEWPORT, size);

	return Py_BuildValue("ii", size[2], size[3]);
}

PyMethodDef AccelMethods[] = {
	// rendering
	{"initTex", initTex, METH_VARARGS, "Initialize an OpenGL texture for later blits"},
	{"updateTex", updateTex, METH_VARARGS, "Update the texture with a VRay image"},
	{"releaseTex", releaseTex, METH_VARARGS, "Release the GL resourse acquired with initTex()"},
	{"blitImage", blitImage, METH_VARARGS, "Blit the last image set with updateTex() to the entire OGL viewport"},
	// util
	{"getViewportSize", getViewportSize, METH_VARARGS, "Get the current size of the OpenGL viewport as a tuple"},
	{NULL, NULL, 0, NULL}
};

PyMODINIT_FUNC initaccel()
{
	Py_InitModule("accel", AccelMethods);
}

#ifdef _WIN32

BOOL WINAPI DllMain(HINSTANCE, DWORD, LPVOID)
{
	return TRUE;
}

#endif
