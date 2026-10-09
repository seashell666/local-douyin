# 家庭抖音 APK

本地家庭抖音的Android客户端，用WebView包装网页版，实现全屏沉浸式体验。

## 功能特性

- **真正全屏**：隐藏状态栏和导航栏，沉浸式刷视频
- **无边缘滑动导航**：不会像浏览器那样左滑右滑跳到别的页面
- **视频自动播放**：无需手动点击，上下滑动自动播放
- **返回键智能处理**：视频全屏→退出全屏；博主主页/音乐页→返回上一层；否则→后台运行
- **屏幕常亮**：刷视频时不会自动锁屏
- **服务器地址可配置**：连续点击左上角5次弹出设置框
- **断网自动恢复**：网络断开提示，恢复后自动刷新
- **视频全屏支持**：横屏全屏播放

## 编译方法

### 方法一：Android Studio（推荐，功能最全）

1. 下载安装 [Android Studio](https://developer.android.com/studio)（免费，约1GB）
2. 打开 Android Studio，选择 `Open an existing project`
3. 选择本项目目录 `local-douyin-apk`
4. 等待 Gradle 同步完成（第一次会下载依赖，约5分钟）
5. 菜单 `Build` → `Build Bundle(s) / APK(s)` → `Build APK(s)`
6. 编译完成后弹窗点击 `locate`，APK在 `app/build/outputs/apk/debug/app-debug.apk`
7. 把APK传到手机安装（需要开启"未知来源应用安装"）

### 方法二：在线打包（不用装软件）

见下方"在线打包服务"章节。

## 使用说明

1. 确保电脑端家庭抖音服务已启动（`http://192.168.0.107:8000`）
2. 手机和电脑连接同一WiFi
3. 安装并打开APK
4. 如果连接失败，连续点击屏幕左上角5次，修改服务器地址

## 修改服务器地址

- **默认地址**：`http://192.168.0.107:8000`
- **修改方法**：连续点击屏幕左上角（60x60区域）5次，弹出设置框
- 地址保存在本地，下次启动自动使用

## 项目结构

```
local-douyin-apk/
├── app/
│   ├── build.gradle
│   └── src/main/
│       ├── AndroidManifest.xml
│       ├── java/com/localdouyin/app/MainActivity.java  ← 核心代码
│       └── res/
│           ├── layout/activity_main.xml
│           ├── values/ (strings.xml, themes.xml, colors.xml)
│           ├── xml/network_security_config.xml
│           ├── drawable/ic_launcher_foreground.png
│           └── mipmap-*/ic_launcher.png
├── build.gradle
├── settings.gradle
├── gradle.properties
└── README.md
```

## 注意事项

- 最低支持 Android 5.0（API 21）
- 应用需要联网权限和振动权限
- 局域网HTTP请求已放行（cleartextTrafficPermitted=true）
- 应用签名为debug签名，如需发布请自行配置release签名
