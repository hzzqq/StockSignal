' StockSignal Frontend v2 hidden worker launcher.
' Runs start_frontend_v2.bat --worker in a HIDDEN cmd window (0 = hidden,
' False = do not wait). Same proven pattern as _launch_hidden.vbs used by v1:
' the visible launcher console shares NO console with the services, so closing
' it can never send CTRL_CLOSE_EVENT to the backend / Vite processes.
Option Explicit
Dim sh, q, batPath, workerArg
If WScript.Arguments.Count < 2 Then WScript.Quit 2
Set sh = CreateObject("WScript.Shell")
q = Chr(34)
batPath = WScript.Arguments(0)
workerArg = WScript.Arguments(1)
sh.Run "cmd.exe /d /c " & q & q & batPath & q & " " & workerArg & q, 0, False
