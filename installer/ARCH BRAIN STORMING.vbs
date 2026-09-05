' Launcher - starts ARCH BRAIN STORMING using the bundled portable Python,
' with no console window. Sits in the install folder next to app.py.
' If nothing opens, run "Run in debug mode.bat" to see the error.
Set sh = CreateObject("WScript.Shell")
Dim p : p = Left(WScript.ScriptFullName, InStrRev(WScript.ScriptFullName, "\"))
sh.CurrentDirectory = p
sh.Run """" & p & "python\pythonw.exe"" """ & p & "app.py""", 0, False
