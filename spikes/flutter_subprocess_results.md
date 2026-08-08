This is the output:
```
Resolving dependencies... (1.0s)
Downloading packages...
  matcher 0.12.19 (0.12.20 available)
  meta 1.18.0 (1.19.0 available)
  test_api 0.7.11 (0.7.13 available)
  vector_math 2.2.0 (2.4.2 available)
Got dependencies!
4 packages have newer versions incompatible with dependency constraints.
Try `flutter pub outdated` for more information.
Launching lib\main.dart on Windows in debug mode...
Building Windows application...                                    43.5s
√ Built build\windows\x64\runner\Debug\flutter_subprocess.exe
Syncing files to device Windows...                                 113ms

Flutter run key commands.
r Hot reload.
R Hot restart.
h List all available interactive commands.
d Detach (terminate "flutter run" but leave application running).
c Clear the screen
q Quit (terminate the application on the device).

A Dart VM Service on Windows is available at: http://127.0.0.1:64120/g7BIqzgO5LY=/
The Flutter DevTools debugger and profiler on Windows is available at:
http://127.0.0.1:64120/g7BIqzgO5LY=/devtools/?uri=ws://127.0.0.1:64120/g7BIqzgO5LY=/ws
[ERROR:flutter/runtime/dart_vm_initializer.cc(40)] Unhandled Exception: Null check operator used on a null value
#0      ScrollPosition.maxScrollExtent (package:flutter/src/widgets/scroll_position.dart:239:49)
#1      _SubprocessPageState._appendLog.<anonymous closure> (package:flutter_subprocess/main.dart:67:35)
#2      new Future.microtask.<anonymous closure> (dart:async/future.dart:287:40)
#3      _microtaskLoop (dart:async/schedule_microtask.dart:40:35)
#4      _startMicrotaskLoop (dart:async/schedule_microtask.dart:49:5)

Lost connection to device.
```