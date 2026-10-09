package com.localdouyin.app;

import android.app.Activity;
import android.app.AlertDialog;
import android.app.DownloadManager;
import android.content.BroadcastReceiver;
import android.content.ClipData;
import android.content.ClipboardManager;
import android.content.Context;
import android.content.Intent;
import android.content.IntentFilter;
import android.content.SharedPreferences;
import android.graphics.Color;
import android.net.ConnectivityManager;
import android.net.NetworkInfo;
import android.net.Uri;
import android.os.Build;
import android.os.Bundle;
import android.os.Environment;
import android.os.Handler;
import android.os.Looper;
import android.text.InputType;
import android.view.KeyEvent;
import android.view.MotionEvent;
import android.view.View;
import android.view.WindowManager;
import android.webkit.ConsoleMessage;
import android.webkit.JavascriptInterface;
import android.webkit.RenderProcessGoneDetail;
import android.webkit.WebChromeClient;
import android.webkit.WebResourceError;
import android.webkit.WebResourceRequest;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.EditText;
import android.widget.FrameLayout;
import android.widget.TextView;
import android.widget.Toast;

import java.io.File;

public class MainActivity extends Activity {

    private static final String PREFS_NAME = "local_douyin_prefs";
    private static final String KEY_URL = "server_url";
    private static final String DEFAULT_URL = "http://192.168.0.107:8000";

    private WebView webView;
    private TextView errorView;
    private View customView;
    private WebChromeClient.CustomViewCallback customViewCallback;
    private FrameLayout customViewContainer;

    private String currentUrl;
    private boolean isLoading = false;
    private boolean networkAvailable = true;

    // 左上角连续点击计数（用于调出设置）
    private int cornerTapCount = 0;
    private long lastCornerTapTime = 0;
    private static final int CORNER_TAP_THRESHOLD = 5;
    private static final long CORNER_TAP_WINDOW = 2000;

    // 最后一次触摸位置（用于判断系统返回手势是左边缘还是右边缘触发的）
    private float lastTouchX = -1;
    private long lastTouchTime = 0;

    private BroadcastReceiver networkReceiver = new BroadcastReceiver() {
        @Override
        public void onReceive(Context context, Intent intent) {
            boolean wasAvailable = networkAvailable;
            networkAvailable = isNetworkAvailable();
            if (networkAvailable && !wasAvailable) {
                // 网络恢复，自动刷新
                runOnUiThread(() -> {
                    errorView.setVisibility(View.GONE);
                    webView.setVisibility(View.VISIBLE);
                    webView.reload();
                });
            } else if (!networkAvailable) {
                runOnUiThread(() -> showError("网络连接已断开\n请检查WiFi后重试"));
            }
        }
    };

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);

        // 全屏 + 常亮 + 刘海屏延伸
        getWindow().addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);
        getWindow().getDecorView().setSystemUiVisibility(
                View.SYSTEM_UI_FLAG_LAYOUT_STABLE
                        | View.SYSTEM_UI_FLAG_LAYOUT_HIDE_NAVIGATION
                        | View.SYSTEM_UI_FLAG_LAYOUT_FULLSCREEN
                        | View.SYSTEM_UI_FLAG_HIDE_NAVIGATION
                        | View.SYSTEM_UI_FLAG_FULLSCREEN
                        | View.SYSTEM_UI_FLAG_IMMERSIVE_STICKY);

        setContentView(R.layout.activity_main);

        // 检查并请求"所有文件访问权限"（Android 11+）
        checkAndRequestAllFilesAccess();

        webView = findViewById(R.id.webview);
        errorView = findViewById(R.id.error_view);
        customViewContainer = new FrameLayout(this);
        customViewContainer.setBackgroundColor(Color.BLACK);

        setupWebView();

        // 读取保存的URL
        SharedPreferences prefs = getSharedPreferences(PREFS_NAME, MODE_PRIVATE);
        currentUrl = prefs.getString(KEY_URL, DEFAULT_URL);

        // 注册网络监听
        IntentFilter filter = new IntentFilter(ConnectivityManager.CONNECTIVITY_ACTION);
        registerReceiver(networkReceiver, filter);

        // 加载页面
        loadUrl(currentUrl);
    }

    /**
     * 检查并请求"所有文件访问权限"（Android 11+）
     * 这个权限不能通过普通requestPermissions请求，需要跳转到设置页面
     */
    private void checkAndRequestAllFilesAccess() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.R) {
            if (!android.os.Environment.isExternalStorageManager()) {
                // 没有权限，弹出对话框引导用户开启
                new android.app.AlertDialog.Builder(this)
                        .setTitle("需要存储权限")
                        .setMessage("下载视频需要【所有文件访问权限】。\n\n点击【去开启】，在设置页面打开【允许管理所有文件】开关，然后返回即可。")
                        .setPositiveButton("去开启", (dialog, which) -> {
                            try {
                                Intent intent = new Intent(android.provider.Settings.ACTION_MANAGE_APP_ALL_FILES_ACCESS_PERMISSION);
                                intent.setData(android.net.Uri.parse("package:" + getPackageName()));
                                startActivity(intent);
                            } catch (Exception e) {
                                // 部分ROM可能不支持这个Intent，回退到通用设置
                                Intent intent = new Intent(android.provider.Settings.ACTION_MANAGE_ALL_FILES_ACCESS_PERMISSION);
                                startActivity(intent);
                            }
                        })
                        .setNegativeButton("暂不", (dialog, which) -> {
                            // 用户拒绝，仍然可以使用，只是下载到Download目录
                            Toast.makeText(this, "视频将下载到 Download/douyin/ 目录", Toast.LENGTH_LONG).show();
                        })
                        .setCancelable(false)
                        .show();
            }
        }
    }

    @SuppressWarnings("deprecation")
    private void setupWebView() {
        WebSettings settings = webView.getSettings();
        settings.setJavaScriptEnabled(true);
        settings.setDomStorageEnabled(true);
        settings.setDatabaseEnabled(true);
        settings.setCacheMode(WebSettings.LOAD_DEFAULT);
        settings.setMediaPlaybackRequiresUserGesture(false); // 视频自动播放
        settings.setUseWideViewPort(true);
        settings.setLoadWithOverviewMode(true);
        settings.setSupportZoom(false);
        settings.setBuiltInZoomControls(false);
        settings.setDisplayZoomControls(false);
        settings.setAllowFileAccess(true);
        settings.setAllowContentAccess(true);
        settings.setMixedContentMode(WebSettings.MIXED_CONTENT_ALWAYS_ALLOW);
        settings.setUserAgentString(settings.getUserAgentString() + " LocalDouyin/1.0");

        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            settings.setSafeBrowsingEnabled(false);
        }

        webView.setBackgroundColor(Color.BLACK);
        webView.setLayerType(View.LAYER_TYPE_HARDWARE, null);

        // 注册JavaScript接口（供前端调用下载视频等原生功能）
        webView.addJavascriptInterface(new DownloadBridge(), "AndroidBridge");

        // 禁用WebView默认长按（文本选择/上下文菜单），让JS长按弹窗正常工作
        webView.setLongClickable(false);
        webView.setHapticFeedbackEnabled(false);
        webView.setOnLongClickListener(v -> true);

        // WebViewClient：处理页面加载和错误
        webView.setWebViewClient(new WebViewClient() {
            @Override
            public boolean shouldOverrideUrlLoading(WebView view, WebResourceRequest request) {
                String url = request.getUrl().toString();
                if (url.startsWith("http://") || url.startsWith("https://")) {
                    // http(s)：在WebView内加载
                    view.loadUrl(url);
                    return true;
                }
                // 非http(s) scheme（如 snssdk1128:// 调起抖音）：交给系统处理，避免WebView加载失败黑屏
                try {
                    Intent intent = new Intent(Intent.ACTION_VIEW, request.getUrl());
                    intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
                    startActivity(intent);
                } catch (Exception e) {
                    android.util.Log.d("LocalDouyin", "scheme launch failed: " + url + " " + e);
                }
                return true;
            }

            @Override
            public boolean onRenderProcessGone(WebView view, RenderProcessGoneDetail detail) {
                // WebView渲染进程崩溃（可能因内存不足/播放器异常）：不弹崩溃页，自动重载当前地址
                if (webView != null && currentUrl != null) {
                    webView.postDelayed(new Runnable() {
                        @Override
                        public void run() {
                            try { webView.loadUrl(currentUrl); } catch (Exception ignored) {}
                        }
                    }, 300);
                }
                return true; // 阻止默认崩溃对话框（黑屏+安卓图标）
            }

            @Override
            public void onPageFinished(WebView view, String url) {
                super.onPageFinished(view, url);
                isLoading = false;
                if (networkAvailable) {
                    errorView.setVisibility(View.GONE);
                    webView.setVisibility(View.VISIBLE);
                }
            }

            @Override
            public void onReceivedError(WebView view, WebResourceRequest request, WebResourceError error) {
                super.onReceivedError(view, request, error);
                if (request.isForMainFrame()) {
                    isLoading = false;
                    showError("无法连接到服务器\n\n地址：" + currentUrl + "\n\n请确认：\n1. 手机和电脑在同一WiFi\n2. 电脑端服务已启动\n3. IP地址是否正确\n\n连续点击左上角5次可修改地址");
                }
            }
        });

        // WebChromeClient：视频全屏、console
        webView.setWebChromeClient(new WebChromeClient() {
            @Override
            public void onShowCustomView(View view, CustomViewCallback callback) {
                if (customView != null) {
                    callback.onCustomViewHidden();
                    return;
                }
                customView = view;
                customViewCallback = callback;
                addContentView(customViewContainer, new FrameLayout.LayoutParams(
                        FrameLayout.LayoutParams.MATCH_PARENT,
                        FrameLayout.LayoutParams.MATCH_PARENT));
                customViewContainer.addView(view);
                customViewContainer.setVisibility(View.VISIBLE);
            }

            @Override
            public void onHideCustomView() {
                if (customView == null) return;
                customViewContainer.setVisibility(View.GONE);
                customViewContainer.removeView(customView);
                customView = null;
                if (customViewCallback != null) {
                    customViewCallback.onCustomViewHidden();
                }
            }

            @Override
            public boolean onConsoleMessage(ConsoleMessage cm) {
                android.util.Log.d("LocalDouyin", cm.message() + " @ " + cm.sourceId() + ":" + cm.lineNumber());
                return true;
            }
        });

        // 左上角连续点击检测 + 边缘滑动拦截（绕过MIUI系统返回手势）
        final float[] edgeStartX = {0};
        final float[] edgeStartY = {0};
        final String[] edgeSide = {""};
        final boolean[] edgePossible = {false};
        final boolean[] edgeSwiping = {false};

        webView.setOnTouchListener((v, event) -> {
            float x = event.getX();
            float y = event.getY();
            float w = webView.getWidth();
            int edgeWidth = (int) (getResources().getDisplayMetrics().density * 100);

            switch (event.getAction()) {
                case MotionEvent.ACTION_DOWN:
                    // 左上角连续点击检测
                    if (x < 60 && y < 60) {
                        long now = System.currentTimeMillis();
                        if (now - lastCornerTapTime < CORNER_TAP_WINDOW) {
                            cornerTapCount++;
                        } else {
                            cornerTapCount = 1;
                        }
                        lastCornerTapTime = now;
                        if (cornerTapCount >= CORNER_TAP_THRESHOLD) {
                            cornerTapCount = 0;
                            showUrlDialog();
                        }
                    }
                    // 边缘滑动检测：记录起点
                    edgePossible[0] = false;
                    edgeSwiping[0] = false;
                    if (x < edgeWidth) {
                        edgeSide[0] = "left";
                        edgeStartX[0] = x;
                        edgeStartY[0] = y;
                        edgePossible[0] = true;
                    } else if (x > w - edgeWidth) {
                        edgeSide[0] = "right";
                        edgeStartX[0] = x;
                        edgeStartY[0] = y;
                        edgePossible[0] = true;
                    }
                    return false; // ACTION_DOWN不消费，让点击事件正常处理

                case MotionEvent.ACTION_MOVE:
                    if (edgePossible[0] && !edgeSwiping[0]) {
                        float dx = x - edgeStartX[0];
                        float dy = y - edgeStartY[0];
                        // 检测到水平滑动趋势（8px且水平分量大于垂直分量），立即进入边缘滑动模式
                        if (Math.abs(dx) > 8 && Math.abs(dx) > Math.abs(dy)) {
                            edgeSwiping[0] = true;
                            // 立即取消Web端的长按和上下滑动，避免被拦截
                            webView.evaluateJavascript(
                                    "window.cancelLongPress && window.cancelLongPress()",
                                    null);
                        }
                    }
                    if (edgeSwiping[0]) {
                        return true; // 消费MOVE事件，阻止系统返回手势和Web端处理
                    }
                    return false;

                case MotionEvent.ACTION_UP:
                case MotionEvent.ACTION_CANCEL:
                    if (edgeSwiping[0]) {
                        float dx = x - edgeStartX[0];
                        // 调用JS的边缘滑动处理接口
                        final String jsSide = edgeSide[0];
                        final float jsDx = dx;
                        webView.evaluateJavascript(
                                "window.handleEdgeSwipe && window.handleEdgeSwipe('" + jsSide + "', " + jsDx + ")",
                                null);
                        edgePossible[0] = false;
                        edgeSwiping[0] = false;
                        return true; // 消费UP事件
                    }
                    edgePossible[0] = false;
                    edgeSwiping[0] = false;
                    return false;
            }
            return false;
        });
    }

    private void loadUrl(String url) {
        if (url == null || url.isEmpty()) url = DEFAULT_URL;
        currentUrl = url;
        isLoading = true;
        webView.loadUrl(url);
    }

    private void showError(String message) {
        errorView.setText(message);
        errorView.setVisibility(View.VISIBLE);
        webView.setVisibility(View.GONE);
    }

    private boolean isNetworkAvailable() {
        ConnectivityManager cm = (ConnectivityManager) getSystemService(Context.CONNECTIVITY_SERVICE);
        if (cm == null) return false;
        NetworkInfo info = cm.getActiveNetworkInfo();
        return info != null && info.isConnected();
    }

    /**
     * 修改服务器地址对话框
     */
    private void showUrlDialog() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M) {
            // 震动反馈
            webView.performHapticFeedback(3); // HAPTIC_FEEDBACK_CONFIRM
        }

        final EditText input = new EditText(this);
        input.setText(currentUrl);
        input.setInputType(InputType.TYPE_TEXT_VARIATION_URI);
        input.setSelection(input.getText().length());

        int pad = dpToPx(20);
        FrameLayout container = new FrameLayout(this);
        container.setPadding(pad, pad / 2, pad, 0);
        container.addView(input);

        new AlertDialog.Builder(this)
                .setTitle("服务器地址")
                .setMessage("输入家庭抖音服务地址\n例如：http://192.168.0.107:8000")
                .setView(container)
                .setPositiveButton("保存并重启", (dialog, which) -> {
                    String newUrl = input.getText().toString().trim();
                    if (!newUrl.isEmpty()) {
                        if (!newUrl.startsWith("http://") && !newUrl.startsWith("https://")) {
                            newUrl = "http://" + newUrl;
                        }
                        SharedPreferences prefs = getSharedPreferences(PREFS_NAME, MODE_PRIVATE);
                        prefs.edit().putString(KEY_URL, newUrl).apply();
                        Toast.makeText(this, "地址已保存，正在重新加载...", Toast.LENGTH_SHORT).show();
                        loadUrl(newUrl);
                    }
                })
                .setNegativeButton("取消", null)
                .setNeutralButton("恢复默认", (dialog, which) -> {
                    input.setText(DEFAULT_URL);
                })
                .show();
    }

    private int dpToPx(int dp) {
        return (int) (dp * getResources().getDisplayMetrics().density);
    }

    /**
     * 记录每次触摸的位置，用于在onBackPressed中判断系统返回手势的触发来源
     * （左边缘右滑 / 右边缘左滑 / 按返回键）
     */
    @Override
    public boolean dispatchTouchEvent(MotionEvent ev) {
        if (ev.getAction() == MotionEvent.ACTION_DOWN) {
            lastTouchX = ev.getRawX();
            lastTouchTime = System.currentTimeMillis();
        }
        return super.dispatchTouchEvent(ev);
    }

    /**
     * 返回键处理：
     * 1. 视频全屏 → 退出全屏
     * 2. 调用JS的handleBackPressWithHistory判断处理方式
     * 3. 返回"handled" → JS已处理（进入/关闭博主主页、切换页面等），不做任何操作
     * 4. 返回"exit" → 退出应用
     * 完全不依赖WebView历史记录，所有逻辑在JS端处理
     */
    @Override
    public void onBackPressed() {
        // 视频全屏时先退出全屏
        if (customView != null) {
            webView.getWebChromeClient().onHideCustomView();
            return;
        }

        int screenWidth = getResources().getDisplayMetrics().widthPixels;
        int edgeWidth = (int) (getResources().getDisplayMetrics().density * 100);
        float touchX = lastTouchX;

        // 调用JS统一处理，根据返回值决定后续操作
        webView.evaluateJavascript(
                "(function(){ try { return window.handleBackPressWithHistory ? window.handleBackPressWithHistory(" + touchX + ", " + screenWidth + ", " + edgeWidth + ") : 'exit'; } catch(e) { return 'exit'; } })()",
                value -> {
                    String result = value != null ? value.replace("\"", "") : "exit";
                    if ("handled".equals(result)) {
                        // JS已处理（进入/关闭博主主页、切换页面等），不做任何操作
                    } else {
                        // 退出应用
                        moveTaskToBack(true);
                    }
                });
    }

    /**
     * 音量键监听：按音量加/减自动解除静音
     * 不消费事件，让系统正常调节音量
     */
    @Override
    public boolean dispatchKeyEvent(KeyEvent event) {
        int keyCode = event.getKeyCode();
        if (keyCode == KeyEvent.KEYCODE_VOLUME_UP || keyCode == KeyEvent.KEYCODE_VOLUME_DOWN) {
            if (event.getAction() == KeyEvent.ACTION_DOWN) {
                webView.evaluateJavascript("(function(){ try { if(window.unmute) window.unmute(); } catch(e){} })()", null);
            }
        }
        return super.dispatchKeyEvent(event);
    }

    /**
     * Android 10+：排除左右边缘区域，系统返回手势不拦截，交给JS的edgeSwipe处理
     * 必须设置在DecorView上，左右各100dp（系统上限200dp）
     */
    private void applySystemGestureExclusion() {
        if (android.os.Build.VERSION.SDK_INT >= android.os.Build.VERSION_CODES.Q) {
            int exclusionWidth = (int) (getResources().getDisplayMetrics().density * 100);
            int screenWidth = getResources().getDisplayMetrics().widthPixels;
            int screenHeight = getResources().getDisplayMetrics().heightPixels;
            android.graphics.Rect leftRect = new android.graphics.Rect(0, 0, exclusionWidth, screenHeight);
            android.graphics.Rect rightRect = new android.graphics.Rect(screenWidth - exclusionWidth, 0, screenWidth, screenHeight);
            java.util.List<android.graphics.Rect> rects = new java.util.ArrayList<>();
            rects.add(leftRect);
            rects.add(rightRect);
            getWindow().getDecorView().setSystemGestureExclusionRects(rects);
        }
    }

    @Override
    public void onWindowFocusChanged(boolean hasFocus) {
        super.onWindowFocusChanged(hasFocus);
        // 重新获得焦点时恢复沉浸式
        if (hasFocus) {
            getWindow().getDecorView().setSystemUiVisibility(
                    View.SYSTEM_UI_FLAG_LAYOUT_STABLE
                            | View.SYSTEM_UI_FLAG_LAYOUT_HIDE_NAVIGATION
                            | View.SYSTEM_UI_FLAG_LAYOUT_FULLSCREEN
                            | View.SYSTEM_UI_FLAG_HIDE_NAVIGATION
                            | View.SYSTEM_UI_FLAG_FULLSCREEN
                            | View.SYSTEM_UI_FLAG_IMMERSIVE_STICKY);
            applySystemGestureExclusion();
        }
    }

    @Override
    protected void onResume() {
        super.onResume();
        webView.onResume();
        // 恢复沉浸式
        getWindow().getDecorView().setSystemUiVisibility(
                View.SYSTEM_UI_FLAG_LAYOUT_STABLE
                        | View.SYSTEM_UI_FLAG_LAYOUT_HIDE_NAVIGATION
                        | View.SYSTEM_UI_FLAG_LAYOUT_FULLSCREEN
                        | View.SYSTEM_UI_FLAG_HIDE_NAVIGATION
                        | View.SYSTEM_UI_FLAG_FULLSCREEN
                        | View.SYSTEM_UI_FLAG_IMMERSIVE_STICKY);
        applySystemGestureExclusion();
    }

    @Override
    protected void onPause() {
        super.onPause();
        webView.onPause();
    }

    @Override
    protected void onDestroy() {
        super.onDestroy();
        try {
            unregisterReceiver(networkReceiver);
        } catch (Exception ignored) {}
        if (webView != null) {
            webView.destroy();
        }
    }

    /**
     * JavaScript接口：供前端调用下载视频到手机
     * 始终用DownloadManager的公共目录方式下载，最稳定可靠
     */
    public class DownloadBridge {
        @JavascriptInterface
        public void downloadVideo(final String url, final String fileName) {
            runOnUiThread(() -> {
                try {
                    // 把相对路径拼接成完整URL
                    String fullUrl = url;
                    if (url != null && url.startsWith("/")) {
                        String baseUrl = currentUrl;
                        if (baseUrl != null) {
                            int pathIndex = baseUrl.indexOf("/", 8);
                            if (pathIndex > 0) {
                                baseUrl = baseUrl.substring(0, pathIndex);
                            }
                            fullUrl = baseUrl + url;
                        }
                    }

                    // 清理文件名中的非法字符
                    String safeName = fileName.replaceAll("[\\\\/:*?\"<>|]", "_");
                    if (!safeName.toLowerCase().endsWith(".mp4")) {
                        safeName = safeName + ".mp4";
                    }

                    // 始终用公共Download目录，DownloadManager最稳定支持的方式
                    DownloadManager.Request request = new DownloadManager.Request(Uri.parse(fullUrl));
                    request.setDestinationInExternalPublicDir(
                            Environment.DIRECTORY_DOWNLOADS, "douyin/" + safeName);
                    request.setTitle("下载视频: " + safeName);
                    request.setDescription("保存到 Download/douyin/ 目录");
                    request.setNotificationVisibility(DownloadManager.Request.VISIBILITY_VISIBLE_NOTIFY_COMPLETED);
                    request.setAllowedOverMetered(true);
                    request.setAllowedOverRoaming(true);
                    // 添加User-Agent，避免某些服务器拒绝
                    request.addRequestHeader("User-Agent", "Mozilla/5.0 (Linux; Android 13) AppleWebKit/537.36");

                    DownloadManager dm = (DownloadManager) getSystemService(Context.DOWNLOAD_SERVICE);
                    if (dm != null) {
                        long downloadId = dm.enqueue(request);
                        Toast.makeText(MainActivity.this,
                                "开始下载: " + safeName + "\n保存到 Download/douyin/",
                                Toast.LENGTH_LONG).show();
                    } else {
                        Toast.makeText(MainActivity.this, "下载服务不可用", Toast.LENGTH_SHORT).show();
                    }
                } catch (Exception e) {
                    // 显示完整错误信息，方便排查
                    String errorMsg = e.toString();
                    if (e.getMessage() != null) errorMsg = e.getMessage();
                    Toast.makeText(MainActivity.this,
                            "下载失败: " + errorMsg,
                            Toast.LENGTH_LONG).show();
                    e.printStackTrace();
                }
            });
        }

        /**
         * 分享：复制抖音口令到剪贴板
         * 抖音 App 启动时会自动检测剪贴板口令并在推荐页上方弹出跳转提示
         */
        @JavascriptInterface
        public void copyText(final String text) {
            runOnUiThread(() -> {
                try {
                    if (text == null || text.isEmpty()) return;
                    ClipboardManager cm = (ClipboardManager) getSystemService(Context.CLIPBOARD_SERVICE);
                    if (cm != null) {
                        cm.setPrimaryClip(ClipData.newPlainText("douyin_share", text));
                        Toast.makeText(MainActivity.this, "口令已复制", Toast.LENGTH_SHORT).show();
                    }
                } catch (Exception ignored) {}
            });
        }

        /**
         * 分享：调起官方抖音 App
         * 支持 schema 深链（snssdk1128://aweme/detail/{id}）直达作品/音乐详情页；
         * 无深链或抖音不处理该 scheme 时回退到普通启动抖音首页。
         */
        @JavascriptInterface
        public void openDouyin(String deepLink) {
            runOnUiThread(() -> {
                try {
                    if (deepLink != null && !deepLink.isEmpty() && deepLink.startsWith("snssdk1128")) {
                        Intent intent = new Intent(Intent.ACTION_VIEW, Uri.parse(deepLink));
                        intent.setPackage("com.ss.android.ugc.aweme");
                        intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
                        startActivity(intent);
                        return;
                    }
                    Intent fallback = getPackageManager().getLaunchIntentForPackage("com.ss.android.ugc.aweme");
                    if (fallback != null) {
                        fallback.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
                        startActivity(fallback);
                    } else {
                        Toast.makeText(MainActivity.this, "未检测到抖音App", Toast.LENGTH_SHORT).show();
                    }
                } catch (Exception e) {
                    // scheme 无人处理等异常 → 回退普通启动
                    try {
                        Intent fallback = getPackageManager().getLaunchIntentForPackage("com.ss.android.ugc.aweme");
                        if (fallback != null) {
                            fallback.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
                            startActivity(fallback);
                        } else {
                            Toast.makeText(MainActivity.this, "未检测到抖音App", Toast.LENGTH_SHORT).show();
                        }
                    } catch (Exception e2) {
                        Toast.makeText(MainActivity.this, "无法打开抖音: " + e2.getMessage(), Toast.LENGTH_SHORT).show();
                    }
                }
            });
        }
    }
}
