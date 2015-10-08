REM run this from where you cloned vray4mobu

mkdir "C:\Program Files\Autodesk\MotionBuilder 2015\bin\x64\python\site-packages\vray4mobu"
xcopy /E /Y scripts "C:\Program Files\Autodesk\MotionBuilder 2015\bin\x64\python\site-packages\vray4mobu"

rem copy /B /Y scripts\init_vray.py "C:\Program Files\Autodesk\MotionBuilder 2015\bin\config\PythonStartup"
