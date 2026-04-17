Set sh = CreateObject("WScript.Shell")
sh.CurrentDirectory = "C:\Users\KJ\code\note taker"
sh.Run Chr(34) & "C:\Users\KJ\code\note taker\venv\Scripts\pythonw.exe" & Chr(34) & " -m app.main", 0, False
