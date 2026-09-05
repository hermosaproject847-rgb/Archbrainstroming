' First-run installer: the SFX extracts everything to a temp folder and runs
' this. It copies the app to a permanent location, makes a Desktop + Start-menu
' shortcut, and launches the app.
Option Explicit
Dim fso, sh, src, dest, d, pr, lnk
Set fso = CreateObject("Scripting.FileSystemObject")
Set sh  = CreateObject("WScript.Shell")

src  = fso.GetParentFolderName(WScript.ScriptFullName)
dest = sh.ExpandEnvironmentStrings("%LOCALAPPDATA%") & "\ArchBrainStorming"

' copy the whole payload to the permanent install folder
sh.Run "robocopy """ & src & """ """ & dest & _
       """ /E /NFL /NDL /NJH /NJS /NC /NS /NP", 0, True

' Desktop shortcut
d = sh.SpecialFolders("Desktop")
Set lnk = sh.CreateShortcut(d & "\ARCH BRAIN STORMING.lnk")
lnk.TargetPath = dest & "\ARCH BRAIN STORMING.vbs"
lnk.WorkingDirectory = dest
lnk.IconLocation = dest & "\ui\appicon.ico"
lnk.Description = "ARCH BRAIN STORMING"
lnk.Save

' Start-menu shortcut
pr = sh.SpecialFolders("Programs")
Set lnk = sh.CreateShortcut(pr & "\ARCH BRAIN STORMING.lnk")
lnk.TargetPath = dest & "\ARCH BRAIN STORMING.vbs"
lnk.WorkingDirectory = dest
lnk.IconLocation = dest & "\ui\appicon.ico"
lnk.Description = "ARCH BRAIN STORMING"
lnk.Save

' --- WebView2 runtime check: the app needs Edge WebView2 to draw its window.
' If it is missing, open Microsoft's download and tell the user, then stop
' (launching would only show a broken window).
Dim hasWV
hasWV = WebView2Installed(sh)
If Not hasWV Then
  MsgBox "One quick step first:" & vbCrLf & vbCrLf & _
         "This PC does not have the Microsoft Edge WebView2 Runtime, which " & _
         "ARCH BRAIN STORMING needs to show its window." & vbCrLf & vbCrLf & _
         "The download page will now open - install it (free, from " & _
         "Microsoft), then open ARCH BRAIN STORMING from the Desktop shortcut.", _
         48, "ARCH BRAIN STORMING - one step needed"
  sh.Run "https://go.microsoft.com/fwlink/p/?LinkId=2124703", 1, False
Else
  sh.CurrentDirectory = dest
  sh.Run """" & dest & "\ARCH BRAIN STORMING.vbs""", 0, False
End If

MsgBox "ARCH BRAIN STORMING is installed." & vbCrLf & vbCrLf & _
       "A shortcut is on your Desktop and in the Start menu." & vbCrLf & _
       "Note: to use 'Read Drawing' (AI reading of a sketch/PDF), install " & _
       "Claude Desktop on this PC and sign in once. Everything else works " & _
       "without it.", 64, "ARCH BRAIN STORMING"

Function WebView2Installed(sh)
  Dim k, pv
  WebView2Installed = False
  On Error Resume Next
  k = "HKLM\SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\" & _
      "{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}\pv"
  pv = sh.RegRead(k)
  If Err.Number = 0 And Len(pv) > 0 And pv <> "0.0.0.0" Then WebView2Installed = True
  Err.Clear
  If Not WebView2Installed Then
    k = "HKCU\SOFTWARE\Microsoft\EdgeUpdate\Clients\" & _
        "{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}\pv"
    pv = sh.RegRead(k)
    If Err.Number = 0 And Len(pv) > 0 And pv <> "0.0.0.0" Then WebView2Installed = True
    Err.Clear
  End If
  On Error GoTo 0
End Function
