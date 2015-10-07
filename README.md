**Make sure you read and comply with LICENSE.md**

You will need a V-Ray AppSDK package to run V-Ray for MotionBuilder. You will
also need one AppSDK license and one V-Ray 3.0 Render Node license.

To install for MotionBuilder 2015 do the following:

* Run install_python_2015.bat

* Run install_bin_2015.bat *from where your AppSDK is*

* Compile the "accel" project - it outputs directly into MoBu's folder. Don't
forget to set x64/Release before compiling

To run on MotionBuilder 2015: Just start it using the run_2015.bat script *from
the AppSDK folder*

For other MoBu versions, just edit the scripts and accel project to the
respective version.

Similar steps should make it work on Linux (LD_LIBRARY_PATH instead of PATH).

NOTE: It is recommended to use an AppSDK build made after September 27th 2015.
