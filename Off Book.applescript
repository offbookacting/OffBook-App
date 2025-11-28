-- AppleScript to launch Off Book with proper name
-- Save this as an application in Script Editor to create a double-clickable app

on run
    set scriptPath to POSIX path of (path to me)
    set projectPath to text 1 thru -19 of scriptPath -- Remove "Off Book.app/Contents/Resources/Scripts/main.scpt"
    set pythonPath to projectPath & ".venv/bin/python"
    set mainPath to projectPath & "main.py"
    
    try
        do shell script "cd " & quoted form of projectPath & " && " & quoted form of pythonPath & " " & quoted form of mainPath
    on error errMsg
        display dialog "Error launching Off Book: " & errMsg buttons {"OK"} default button "OK"
    end try
end run












