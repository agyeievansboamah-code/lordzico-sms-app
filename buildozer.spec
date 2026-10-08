[app]
title = LORDZICO SMS.
package.name = lordzicosms.
package.domain = org.lordzico
source.dir = .
source.include_exts = py,png
source.exclude_dirs = later
version = 1.1
p4a.branch = v2024.01.21
requirements = python3,kivy==2.3.0,pyjnius,plyer
icon.filename = %(source.dir)s/icon.png
orientation = portrait
fullscreen = 0
android.permissions = SEND_SMS,READ_EXTERNAL_STORAGE
android.api = 33
android.minapi = 24
android.archs = arm64-v8a
android.accept_sdk_license = True

[buildozer]
log_level = 2
warn_on_root = 1
