Option Explicit

Dim shell, command, index

If WScript.Arguments.Count < 1 Then
    WScript.Quit 87
End If

command = QuoteArgument(WScript.Arguments(0))
For index = 1 To WScript.Arguments.Count - 1
    command = command & " " & QuoteArgument(WScript.Arguments(index))
Next

Set shell = CreateObject("WScript.Shell")
WScript.Quit shell.Run(command, 0, True)

Function QuoteArgument(value)
    If InStr(value, Chr(34)) > 0 Then
        WScript.Quit 87
    End If
    QuoteArgument = Chr(34) & value & Chr(34)
End Function
