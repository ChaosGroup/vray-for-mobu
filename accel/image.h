#ifndef __VRAY_IMAGE_H__
#define __VRAY_IMAGE_H__

// copied from appsdk/python module
// hacked private members to public

class VRayImage;

namespace VRayPythonWrapper {

	class Image : public PyObject {
	public:
		VRayImage* imageNative;
		long x, y;
		long width, height;
		PyObject* host;

		// methods ripped out
	};
}

#endif
