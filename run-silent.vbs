' ============================================================
'  ARCH BRAIN STORMING - silent background launcher
'  Starts the web server + the named Cloudflare tunnel with NO
'  visible window, so https://saradigitalstudios.com is live.
'  Auto-runs at Windows login (a copy sits in the Startup folder).
' ============================================================
Option Explicit
Dim sh, env, proj, py, cf, tunnel, port
Set sh = CreateObject("WScript.Shell")

proj   = "C:\Users\rahat.iqbal\Downloads\New folder (8)\SketchToPlan"
py     = sh.ExpandEnvironmentStrings("%USERPROFILE%") & "\pyembed\pythonw.exe"
cf     = proj & "\cloudflared.exe"
tunnel = "archbrainstorming"
port   = "8080"

sh.CurrentDirectory = proj
Set env = sh.Environment("PROCESS")
env("PORT")       = port
env("MPLBACKEND") = "Agg"

' 1) web server (windowless python), hidden, do not wait
sh.Run """" & py & """ """ & proj & "\webserver.py""", 0, False

' give the server a few seconds to bind the port
WScript.Sleep 6000

' 2) the named tunnel, hidden, do not wait
sh.Run """" & cf & """ tunnel run --url http://localhost:" & port & " " & tunnel, 0, False
