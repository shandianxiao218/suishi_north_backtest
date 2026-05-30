# 安装 Git for Windows
Write-Host "正在下载 Git for Windows..."

# 下载 Git for Windows 安装程序
$downloadUrl = "https://github.com/git-for-windows/git/releases/download/v2.45.1.Git-2.45.1-64-bit/Git-2.45.1-64-bit.exe"
$outputFile = "$env:TEMP\git-installer.exe"

Invoke-WebRequest -Uri $downloadUrl -OutFile $outputFile

Write-Host "Git 安装程序已下载到: $outputFile"
Write-Host "请手动运行此安装程序并完成安装。"
Write-Host "安装完成后，请关闭此窗口并重新打开一个新的终端。"
Write-Host "安装建议："
Write-Host "1. 选择默认组件即可"
Write-Host "2. 编辑器选择 VS Code（可选）"
Write-Host "3. PATH 环境变量选择第一项（自动添加）"
Write-Host "4. 默认终端选择 Git Bash（推荐）"

# 打开下载目录
Invoke-Item "$env:TEMP"