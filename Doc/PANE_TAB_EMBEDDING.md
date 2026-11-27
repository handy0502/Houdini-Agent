# 在 Houdini 面板 Tab 中使用 Agent

本分支新增 Python Panel 集成。Agent 可以放进 Houdini 的 pane tab，与网络编辑器等面板一起停靠、拆分，并随 desktop 保存。浮动窗口入口仍然可用；同一 Houdini 进程中的面板和浮动窗口共享 `Controller`、`ChatModel` 与聊天历史。

## 安装和打开

先运行当前分支的独立 Agent，让启动器将 Bridge package 写入对应 Houdini 用户目录。package 中的 `HOUDINI_PATH` 会让 Houdini 加载以下内容：

- `houdini_agent/houdini_package/python_panels/HoudiniAgent.pypanel`：面板定义。
- `houdini_agent/houdini_package/toolbar/HoudiniAgent.shelf`：打开面板的 Shelf 按钮。

首次安装 package 后，保存场景并重启 Houdini。在 pane 的新建 Tab 菜单中选择 **Houdini Agent**，或使用随包提供的 Shelf 按钮。

也可在已加载本项目的 Houdini Python Shell 或自定义 Shelf 中运行：

```python
from houdini_agent.ui_qml import pane
pane.open_pane_tab()
```

它会检查面板定义是否已安装，优先切换到现有 Agent Tab；没有现有 Tab 时，在鼠标所在 pane 或网络编辑器所在 pane 新建。没有可用 pane 时才创建浮动 Python Panel。

设置 `HAGENT_UI=pane` 后，原有 `houdini_agent.main.show_tool()` 优先打开面板，失败时回退浮动窗口；也可直接调用 `houdini_agent.main.show_panel()`。默认 `HAGENT_UI=qml` 仍打开浮动窗口。

本项目 QML 使用 Qt 6 模块，内嵌运行需要能够加载这些模块的 Houdini / PySide6 环境。Python 导入中的 PySide2 回退不表示 Qt 5 的 QML 界面已经验收。独立 Agent 自带或安装自己的 Qt，不受 Houdini 内嵌 Qt 版本限制。

## 渲染与输入

默认链路为：

```text
Python Panel onCreateInterface()
  -> pane.create_widget()
  -> host.create_native_view() / QQuickView
  -> QWidget.createWindowContainer()
  -> Houdini pane tab
```

`QQuickView` 提供原生窗口，改善 Houdini 宿主中的键盘焦点。若遇到显卡、远程桌面或原生子窗口兼容问题，可在打开面板前设置：

```python
import os
os.environ["HAGENT_PANE_RENDERER"] = "widget"
```

随后关闭并重新打开面板，使用 `QQuickWidget` 回退路径；浮动窗口始终使用 `QQuickWidget`。

面板创建或激活后会重试聚焦输入框。`Ctrl+N` 新建对话，`Ctrl+B` 切换侧栏，`Ctrl+,` 打开设置；三个快捷键只在面板拥有键盘焦点时启用，隐藏或失焦后释放宿主快捷键。QML 使用 `WindowShortcut`，由 Python 宿主同步焦点状态；`WidgetShortcut` 在这两种 QML 宿主中无法正确匹配。

首次聚焦成功后会停止重试；点击其它控件或切走面板也会取消尚未执行的延迟聚焦，避免把用户刚转移到参数面板的输入抢回。设置齿轮左侧的「更新」按钮仅在有新版本时显示，下载进度和待安装取消操作也在该处显示。

`QQuickWidget` 回退路径另外安装焦点与输入法事件过滤器，帮助处理宿主截获的文本按键。原生路径由窗口接收键盘事件，不转发重复输入。输入框按 `Enter` 发送，`Shift+Enter` 换行。

## 会话和生命周期

- 同一 Houdini 中多个 Agent 面板和浮动窗口共用一份会话状态，消息同步，一次只运行一个 Agent 请求。
- 清空对话的确认绑定发起操作时的会话；其它视图切换会话或开始运行后，旧确认不会清空当前对话，需要重新确认。
- 关闭面板会保存历史并释放该视图的监视器；进程中的 Controller 保留，正在执行的回合继续运行。
- 切换或清空 HIP 前、Houdini 退出时也会保存历史。重新打开面板会连接到现有 Controller。
- 面板布局由 Houdini desktop 保存；聊天历史使用 Agent 原有的 `cache/qml_sessions` 存储，两者分开管理。
- 多个 Houdini 进程各有自己的内嵌 Controller。外部 Agent 则通过右上角连接菜单选择其中一个 Bridge；Windows Bridge 独占端口，后启动的会话自动顺延到空闲端口。

## 更新和排查

修改 `.pypanel` 脚本后可在 Houdini Python Shell 调用：

```python
from houdini_agent.ui_qml import pane
pane.reload_active_panel()
```

修改 Python 模块后建议保存场景并重启 Houdini，以清除进程内已加载的旧模块。QML 禁用磁盘缓存，关闭并重开视图可读取新的 QML 文件。

- 找不到面板菜单：检查 Houdini 用户目录中的 `packages/HoudiniAgent.json`，以及其中 `HAGENT_REPO` 指向的代码路径。首次安装 package 后需重启 Houdini。
- 面板显示加载异常：查看面板中的 traceback 或 Houdini Python Shell。启动错误会显示为只读文本，不会只留下空白。
- 无法输入：先确认面板渲染路径，必要时尝试 `HAGENT_PANE_RENDERER=widget`。诊断日志记录于 Windows `%LOCALAPPDATA%/HoudiniAgent/pane.log`，Linux `~/HoudiniAgent/pane.log`。
- 多会话仍显示同一端口：保存场景并重启所有使用旧 Bridge 代码的 Houdini，再刷新外部 Agent 的会话列表。

## 自动回归和实机验收

`tests/test_pane_panel.py` 检查 XML 定义、代码路径、Tab 打开逻辑，并在隔离的 Qt 子进程中分别覆盖 native/widget 两种渲染路径、输入、快捷键和销毁。测试使用临时设置与历史目录，不读取用户的真实聊天缓存。`tests/test_panel_scroll.py` 检查设置与供应商页面的滚动边界。

离屏测试不能替代 Houdini 宿主验收。发布前仍需在目标 Houdini 中确认：Tab 停靠与拆分、desktop 恢复、中文输入法、与宿主快捷键的焦点交接、关闭后重开，以及真实场景工具执行。Rocky Linux 9 上还需验证显卡驱动与窗口系统。
