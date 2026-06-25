[app]
title = My Assistant
package.name = myassistant
package.domain = org.aleks
source.dir = .
source.include_exts = py,png,jpg,kv,atlas,ttf,txt
version = 1.7
requirements = python3,kivy,requests,certifi,pybit,pycryptodome,websocket-client
orientation = portrait
fullscreen = 0
android.permissions = INTERNET,RECORD_AUDIO
android.archs = arm64-v8a
android.allow_backup = True

[buildozer]
log_level = 2
warn_on_root = 1
