@echo off
chcp 65001 > nul
cd /d "%~dp0\.."
echo ===========================================
echo 番茄发文助手 Electron版 (PyWebView) 一键打包
echo ===========================================
echo.
tasklist /FI "IMAGENAME eq FanqiePublisher_PRO.exe" | find /I "FanqiePublisher_PRO.exe" > nul
if not errorlevel 1 (
    echo 检测到 FanqiePublisher_PRO.exe 正在运行。
    echo 请先关闭所有番茄发文助手窗口，再重新双击本脚本打包。
    echo 否则 Windows 会锁住旧 exe，导致新代码无法覆盖进去。
    pause
    exit /b 1
)
echo 未检测到旧程序运行，可以安全打包。
echo.
echo 正在安装打包工具 pyinstaller ...
py -3 -m pip install pyinstaller
if errorlevel 1 goto build_failed
echo 正在确保项目依赖完整...
py -3 -m pip install -r requirements.txt
if errorlevel 1 goto build_failed
py -3 -m playwright install chromium
if errorlevel 1 goto build_failed
echo.
echo 开始打包成独立桌面软件...
:: 注意这里需要将 web 文件夹一同打包进去
py -3 -m PyInstaller --clean --noconfirm -F -w -i "assets\\logo.ico" --add-data "app\\web;app\\web" -n FanqiePublisher_PRO main_webview.py
if errorlevel 1 goto build_failed
echo.
echo 正在为您生成桌面快捷方式...
powershell -Command "$s=(New-Object -COM WScript.Shell).CreateShortcut('%USERPROFILE%\Desktop\番茄发文大魔王.lnk');$s.TargetPath='%CD%\dist\FanqiePublisher_PRO.exe';$s.WorkingDirectory='%CD%';$s.IconLocation='%CD%\assets\logo.ico';$s.Save()"
echo 桌面快捷方式已成功创建！
echo.
echo ===========================================
echo 打包完成！
echo 请前往 dist/ 文件夹下查看 FanqiePublisher_PRO.exe 软件
echo 注意：软件自带了网页UI界面，运行效果类似 Electron 应用。
echo 如果启动白屏，请检查客户机是否自带了 Edge WebView2 (Win10/11 默认自带)。
echo ===========================================
pause
exit /b 0

:build_failed
echo.
echo 打包失败，请查看上方错误信息。
pause
exit /b 1
