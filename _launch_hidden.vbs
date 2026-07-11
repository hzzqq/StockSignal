Set WshShell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
scriptDir = fso.GetParentFolderName(WScript.ScriptFullName)
batPath = scriptDir & "\启动StockSignal.bat"
WshShell.Run "cmd /c """ & batPath & """ hidden", 0, False
