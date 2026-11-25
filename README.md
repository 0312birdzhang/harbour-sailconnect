# Sailconnect

Sailfish OS 真实手机屏幕的实验性 CarPlay 发送端，自动发现局域网中的 WinPlay、LinuxPlay 和 MacPlay 接收端。
复用 Sailplay 的配对、加密、RTSP、HID 解析和屏幕流模块。独立运行，不启动车载
桌面或虚拟 Wayland 合成器，不调整网络，也不读取或修改 Sailplay 的配对数据。

## 当前可交付内容

- 独立 Silica 应用、systemd / D-Bus 后台和 aarch64 RPM 构建脚本；蓝牙 iAP2 引导后，通过局域网传输画面。
- 通过 DNS-SD 广播发现接收端名称、地址、实际端口与接口；主页选择接收端后即可连接。
- 原生屏幕尺寸从实际 recorder 缓冲区自动读取，网络接口可自动选择；手动覆盖与画质参数收进高级设置。
- lipstick-recorder → 等比黑边缩放 → x264 H.264 → CarPlay 屏幕流。
- 接收端尺寸协商、三档分辨率、15/30/60 fps、码率和每会话固定旋转角度。
- 每次连接默认开启远程控制；画面开始且手机解锁后才接受输入，也可在连接前关闭远控开关。
- 界面支持英文、简体中文和繁体中文，随系统语言切换；连接状态和常见错误也提供翻译。
- 单点触摸后端支持按下、移动和抬起，可表达点击、拖动、长按和边缘滑动。
- 黑边起始触摸被忽略；有效拖动可以延伸至手机边缘。撤销控制、锁屏、事件通道
  断开、应用退出和会话结束时销毁专用 uinput 设备。锁屏撤销后需重新允许控制。
- 原生尺寸不匹配时采集停止，避免用错误尺寸注入输入。

其他系统语言默认使用英文。翻译源文件位于 `app/translations/`，构建脚本生成并打包 Qt 翻译目录。

已在 Pixel 3 / Sailfish OS 5.2.0.22 安装运行，并与 WinPlay 1.2.5 经电脑热点完成
配对、加密控制、视频发送和返回 HID 报告。用户已确认真实屏幕的画面、比例和颜色正常。
完整手势验收和 30 分钟性能回归状态见 VALIDATION.md。
自动旋转、多点触摸、音频、文字键盘注入、USB 和公网连接尚未实现。
系统屏幕键盘可以通过单点点击操作；具体效果待设备确认。

## 安装和使用

面向支持 `/run/display/wayland-0`、`defaultuser`、lipstick-recorder 和 uinput
的 aarch64 Sailfish 系统。安装包的 ELF 依赖由当前 SDK 自动生成；旧系统可能
需要用对应 SDK 重建，不能靠忽略依赖强装。

```sh
devel-su pkcon install-local ./harbour-sailconnect-0.1.0-11.aarch64.rpm
```

首次使用时，在系统蓝牙设置中配对手机与接收电脑，并保持手机蓝牙开启。
首次打开会显示五步连接向导：蓝牙配对、同一局域网、准备手机端、启动接收端、连接投屏。
准备蓝牙连接和开启投屏前会自动停止已安装的 `sailplay.service`，等待其清理完成，避免两个应用争用连接。未安装 Sailplay 时跳过；停止失败会报错。不会修改 Sailplay 的开机启动设置，结束投屏后也不会自动恢复该服务。
向导显示当前手机状态，可直接打开系统蓝牙或 Wi-Fi 设置；接收端通过发现列表选择。
确认开始投屏并完成向导后，后续打开进入主页。可暂时跳过，也可从主页下拉菜单再次打开。
主页下拉菜单还提供关于页面，显示图标、安装版本、作者、许可证、参考项目和接收端下载链接。
手机和电脑连接同一局域网，先打开 Sailconnect；应用自动准备蓝牙 iAP2 服务并搜索接收端。
再在 WinPlay、LinuxPlay 或 MacPlay 中开始接收。选择列表中的接收端，再点击连接。
需要重新搜索时点击“搜索接收端”，也会重新准备蓝牙服务。
扫描读取 `_airplay._tcp.local` 广播中的 SRV、TXT、A/AAAA 记录，使用实际公布的端口，
而不是把 17000 写死。IPv6 链路本地地址使用手机自身的接口作用域。

未发现接收端时，可打开“手动输入地址”，只填写 IP 和端口。默认备用端口为 17000。
网络接口、屏幕尺寸、旋转、分辨率、帧率和码率位于“高级设置”；默认自动读取实际屏幕缓冲区尺寸。
关闭“自动识别屏幕尺寸”才需手动填写原生宽高。旋转仍是每次会话固定，改变方向需先停止。

现有接收端的无线/局域网模式需要蓝牙 iAP2 引导，本应用提供临时 RFCOMM 服务，
随后通过 TCP 建立配对验证、加密控制及视频通道。网络 SETUP 使用手机蓝牙地址，
匹配接收端选择的已配对手机；加密密钥仍使用 Sailconnect 自己的持久身份。
连接建立后也支持网络 iAP2 消息，避免接收端在交接后再次等待蓝牙。无需修改接收端。
通用 AirPlay 镜像服务不一定兼容。应用不自动切换 Wi-Fi。

接收端启动后点击连接；接收端尚未就绪时显示“等待 WinPlay”。远控默认开启；
画面开始且手机解锁后才接受输入，也可随时关闭开关切换为只读。停止入口在
主界面和封面。关闭应用会停止会话，应用异常消失时后台通过 D-Bus 所有者消失
信号停止会话。保持手机本地可操作；不绕过锁屏。

没有活动连接时隐藏停止按钮和封面停止动作；等待连接或重连时仍可停止本次连接请求。
活动封面使用随系统氛围着色的透明投屏线稿，显示简短连接状态和正在传输的尺寸。

连接参数保存在独立的 Sailconnect 用户配置中，远控许可不会持久化。
Pixel 3 的建议参数：追求清晰度用 Full / 30fps；追求流畅度用 Automatic / 60fps。
自动档会在 60fps 时优先选择不超过 1280×720 的协商档位；WinPlay 从 1080p 改为
720p 时会相应使用全尺寸 720p，避免再次缩小。60fps 使用更快的编码预设、
连续重绘和进程级性能核心亲和性；不更改 CPU governor 或系统全局设置。
界面同时显示目标与实测帧率，初始约 5 秒后更新实测值。
WinPlay 停止或重启接收后，手机会清理旧会话并继续等待重连。重连按本次连接的远控设置初始化；
锁屏会撤销当前会话的控制，解锁后需手动打开开关。点击停止或关闭应用会结束整个连接请求。
旋转设置与采集和输入映射共用。当前固定捕获方向，改变方向需要停止再连接。
自动模式使用录屏缓冲区的真实宽高；手动模式也必须填写该尺寸。MCE 锁状态不可查询时禁用控制。
若 uinput 不可用或权限不足，会撤销控制并记录错误；没有虚拟桌面回退。

后台日志：`devel-su journalctl -u sailconnect.service -f`。
接收端能力记录：`/run/sailconnect/receiver.plist`（仅 root 可读）。
配对身份：`/var/lib/sailconnect/identity.json`（卸载保留，避免意外更换身份）。

## 构建与验证

应用图标采用 Sailfish OS 官方圆与方组合轮廓，以手机、接收端屏幕和投射箭头表达投屏功能。
矢量源文件为 `rpm/harbour-sailconnect.svg`，RPM 包含 86、108、128、172 像素的 PNG 图标。
设计预览与导出方法见 [design/README.md](design/README.md)。

本机 WSL Ubuntu-22.04 配置了 Sailfish SDK，可执行：

```powershell
wsl -d Ubuntu-22.04 -u root -- bash /mnt/d/code/harbour-sailconnect/scripts/build-package-from-wsl.sh
wsl -d Ubuntu-22.04 -- bash -lc 'cd /mnt/d/code/harbour-sailconnect && python3 -m pytest'
```

构建脚本从随附的 x264 源码编译，输出 RPM 及对应应用源码压缩包。SDK 路径和
target 可通过 `SDK` / `TARGET` 环境变量设置。源码包内包含捕获源码、测试和脚本。
不向设备自动安装，也不修改 Sailplay 工程。

可从 SSH 进行可重复的局域网验证（终止命令即停止会话）：

```sh
PYTHONPATH=/opt/sailconnect python3 -m sailconnect.client --host 192.168.137.1 --quality 3 --fps 60 --seconds 1800 --control
```

命令行也可自动发现接收端：

```sh
PYTHONPATH=/opt/sailconnect python3 -m sailconnect.client --scan
```

命令行默认自动选择网络接口并读取屏幕尺寸；显式指定 `--interface`、`--native-width` 和
`--native-height` 才覆盖自动配置。

命令默认开启远控；添加 `--view-only` 则本次连接及重连均只读。`--control` 保留为兼容参数。
锁屏后不会自动恢复当前会话的控制。

验证记录和仍待验证的设备项目见 [VALIDATION.md](VALIDATION.md)。
许可和上游声明见 [THIRD_PARTY.md](THIRD_PARTY.md)。
