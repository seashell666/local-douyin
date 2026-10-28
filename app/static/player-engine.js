/* player-engine.js —— 共享播放引擎（首页 home + 我页 my 通用）
 * 共享的是"播放功能"：加载/预加载/播放暂停/上下滑切换/手势/静音联动/双音防护；
 * 数据来源不共享，由 opts.dataSource 注入。 */
window.createPlayerEngine = function (opts) {
  "use strict";
  opts = opts || {};
  var variant = opts.variant === "my" ? "my" : "home";
  var playMode = "home";  // 单页引擎：当前播放模式（home/my），随数据源动态切换
  var rootEl = opts.rootEl;            // 引擎根容器（home=#stage / my=#myPlayer）
  var slider = opts.sliderEl;          // 滑动容器（home=#slider / my=#mySlider）
  var loading = opts.loadingEl;
  var toast = opts.toastEl;
  var musicPageEl = opts.musicPageEl;  // 音乐页（home=#musicPage / my=#myMusicPage）
  var dataSource = opts.dataSource;
  var myDataSource = opts.myDataSource || null;  // 单页引擎：我页数据源（与 home 数据隔离）
  var autoStart = opts.autoStart !== false;
  var showSplash = opts.showSplash === true;
  var onOpen = opts.onOpen || function () {};
  var onClose = opts.onClose || function () {};

  var videos = [];
  window.__VER = "v9.2.0-shared";
  var offset = 0;
  var hasMore = true;
  var loadingMore = false;
  var current = 0;
  var PAGE = opts.pageSize || 120;
  var THRESHOLD = 60;
  var FLING_SPEED = 0.35;
  var FLING_MIN_DIST = 25;
  var EASE = "cubic-bezier(0.22,1,0.36,1)";

  // ===== 反馈数据系统（首页/my 共用，全局共享一份）=====
  var _feedbackSet = {};
  try {
    var _fs0 = localStorage.getItem("dy_feedback_set");
    if (_fs0) _feedbackSet = JSON.parse(_fs0);
  } catch (e) {}
  function saveFeedbackSet() {
    try { localStorage.setItem("dy_feedback_set", JSON.stringify(_feedbackSet)); } catch (e) {}
  }
  function markFeedback(vid, kind) {
    if (!vid) return;
    _feedbackSet[vid] = _feedbackSet[vid] || {};
    if (kind === "unlike") { delete _feedbackSet[vid]["like"]; delete _feedbackSet[vid]["unlike"]; }
    else if (kind === "uncollect") { delete _feedbackSet[vid]["collect"]; delete _feedbackSet[vid]["uncollect"]; }
    else _feedbackSet[vid][kind] = 1;
    saveFeedbackSet();
  }
  function hasAnyFeedback(vid) {
    if (!vid) return false;
    var f = _feedbackSet[vid];
    if (!f) return false;
    return !!(f.like || f.collect || f.not_interested || f.super_like || f.secret_like || f.puzzle);
  }
  window.__markFeedback = markFeedback;
  window.__hasAnyFeedback = hasAnyFeedback;
  window.__getFeedbackState = function (vid) {
    if (!vid) return {};
    return _feedbackSet[vid] || {};
  };

  // 当前视频ID（中间槽位 slide.__vid）
  function currentVid() {
    try {
      var cur = slideEls[1];
      if (cur && cur.__vid) return cur.__vid;
      for (var i = 0; i < slideEls.length; i++) {
        var vv = slideEls[i].querySelector("video");
        if (vv && !vv.paused && slideEls[i].__vid) return slideEls[i].__vid;
      }
      return null;
    } catch (e) { return null; }
  }
  window.__currentVid = currentVid;

  // ===== 行为上报（点赞/收藏/观看等，落库 + 反馈记账）=====
  function reportBehaviorRaw(eventType, vid, pos, dur, meta) {
    try {
      var body = JSON.stringify({
        user_id: "local_user",
        video_id: vid,
        event_type: eventType,
        position: pos || 0,
        duration: dur || 0,
        session_id: "sess_" + Date.now(),
        algorithm_ver: "v001",
        metadata: meta || null
      });
      var sent = false;
      try {
        if (window.fetch) {
          fetch("/api/behavior", { method: "POST", headers: { "Content-Type": "application/json" }, body: body, keepalive: true }).catch(function () {});
          sent = true;
        }
      } catch (e) {}
      if (!sent && navigator.sendBeacon) {
        navigator.sendBeacon("/api/behavior", new Blob([body], { type: "application/json" }));
      }
    } catch (e) {}
  }
  function reportBehavior(eventType, vid, pos, dur, meta) {
    try {
      if (eventType === "like" || eventType === "collect" || eventType === "unlike" || eventType === "uncollect") {
        if (vid) {
          if (eventType === "like") markFeedback(vid, "like");
          else if (eventType === "collect") markFeedback(vid, "collect");
          else if (eventType === "unlike") markFeedback(vid, "unlike");
          else if (eventType === "uncollect") markFeedback(vid, "uncollect");
        }
      }
    } catch (e) {}
    reportBehaviorRaw(eventType, vid, pos, dur, meta);
  }
  window.reportBehavior = reportBehavior;

  // ===== 毛玻璃反馈提示（白底黑字小圆角，复刻抖音）=====
  var _fbToastEl = null;
  function feedbackToast(msg) {
    try {
      if (!_fbToastEl) {
        _fbToastEl = document.createElement("div");
        _fbToastEl.id = "feedbackToast";
        _fbToastEl.style.cssText = "position:fixed;left:12px;right:12px;bottom:calc(92px + env(safe-area-inset-bottom));transform:translateY(10px);" +
          "background:rgba(255,255,255,0.92);backdrop-filter:blur(20px);-webkit-backdrop-filter:blur(20px);" +
          "color:#000;padding:11px 22px;border-radius:8px;font-size:14px;font-weight:500;z-index:99999;" +
          "box-shadow:0 4px 16px rgba(0,0,0,0.10);opacity:0;transition:opacity .25s ease,transform .25s ease;pointer-events:none;text-align:center";
        document.body.appendChild(_fbToastEl);
      }
      _fbToastEl.textContent = msg;
      _fbToastEl.style.opacity = "1";
      _fbToastEl.style.transform = "translateY(0)";
      clearTimeout(_fbToastEl.__t);
      _fbToastEl.__t = setTimeout(function () { if (_fbToastEl) _fbToastEl.style.opacity = "0"; }, 1600);
    } catch (e) {}
  }
  window.feedbackToast = feedbackToast;

  var soundOn = false;
  var defaultMute = true;
  var defaultAutoPlay = false;
  var defaultCleanMode = false;
  var pendingUnmute = false; // 自动播放降级为静音后，等待用户第一次交互时自动取消静音


  function loadDefaults() {
    try {
      var dm = localStorage.getItem("dy_default_mute");
      var da = localStorage.getItem("dy_default_autoplay");
      var dc = localStorage.getItem("dy_default_clean");
      if (dm !== null) defaultMute = dm === "1";
      if (da !== null) defaultAutoPlay = da === "1";
      if (dc !== null) defaultCleanMode = dc === "1";
    } catch(e) {}
  }
  function saveDefaults() {
    try {
      localStorage.setItem("dy_default_mute", defaultMute ? "1" : "0");
      localStorage.setItem("dy_default_autoplay", defaultAutoPlay ? "1" : "0");
      localStorage.setItem("dy_default_clean", defaultCleanMode ? "1" : "0");
    } catch(e) {}
  }
  var autoPlayNext = true; // 自动联播：播完自动跳下一个
  var cleanMode = true; // 清屏播放：默认开启，隐藏所有UI只留视频
  // 全局视频排版函数：根据原始宽高比决定显示模式和垂直位置
  function applyVideoLayout(video, slide) {
    if (!video || !slide) return;
    // 元数据未就绪时：先设置默认全屏cover，防止黑边，500ms后重试
    if (video.videoWidth === 0 || video.videoHeight === 0) {
      video.style.objectFit = "cover";
      video.style.objectPosition = "center";
      setTimeout(function() { applyVideoLayout(video, slide); }, 500);
      return;
    }
    if (!video.duration || isNaN(video.duration) || !isFinite(video.duration)) return;
    var ratio = video.videoHeight / video.videoWidth;
    var containerH = slide.clientHeight;
    if (!containerH) return;
    var videoH = video.videoHeight * (slide.clientWidth / video.videoWidth);
    var bottomSafe = 142;
    // 9:16 = 1.7778，用>=1.77确保9:16视频命中cover
    if (ratio >= 1.77 || videoH >= containerH) {
      video.style.objectFit = "cover";
      video.style.objectPosition = "center";
    } else if (videoH >= containerH - bottomSafe) {
      video.style.objectFit = "contain";
      var topPos = containerH - videoH - bottomSafe;
      video.style.objectPosition = "center " + topPos + "px";
    } else {
      video.style.objectFit = "contain";
      video.style.objectPosition = "center";
    }
  }
  // 统一设置清屏模式
  function setCleanMode(enabled) {
    cleanMode = enabled;
    var sw = document.getElementById("lpCleanSwitch");
    if (sw) { if (enabled) sw.classList.add("on"); else sw.classList.remove("on"); }
    if (enabled) {
      document.body.classList.add("clean-mode");
    } else {
      document.body.classList.remove("clean-mode");
    }
  }
  var videoPositions = {};

  // 取消静音提示
  var unmuteTimer = null;
  function showUnmutePrompt() {
    if (soundOn) return;
    document.querySelectorAll(".music").forEach(function (m) { m.classList.add("prompt"); });
    unmuteTimer = setTimeout(hideUnmutePrompt, 3000);
  }
  function hideUnmutePrompt() {
    if (unmuteTimer) { clearTimeout(unmuteTimer); unmuteTimer = null; }
    document.querySelectorAll(".music").forEach(function (m) { m.classList.remove("prompt"); });
  }

  var liked = loadSet("dy_liked");
  var collected = loadSet("dy_collected");
  function loadSet(k) { try { return JSON.parse(localStorage.getItem(k) || "{}"); } catch (e) { return {}; } }
  function saveSet(k, s) { try { localStorage.setItem(k, JSON.stringify(s)); } catch (e) {} }

  // 关注状态（从API同步，localStorage做缓存）
  var followedCache = loadSet("dy_followed");

  var ICON_HEART = '<svg viewBox="0 0 24 24"><path d="M7.5 2.25C10.5 2.25 12 4.25 12 4.25C12 4.25 13.5 2.25 16.5 2.25C20 2.25 22.5 4.99999 22.5 8.5C22.5 12.5 19.2311 16.0657 16.25 18.75C14.4095 20.4072 13 21.5 12 21.5C11 21.5 9.55051 20.3989 7.75 18.75C4.81949 16.0662 1.5 12.5 1.5 8.5C1.5 4.99999 4 2.25 7.5 2.25Z"/></svg>';
  var ICON_COMMENT = '<svg viewBox="0 0 48 48"><path fill-rule="evenodd" d="M2 21.5c0-10.22 9.88-18 22-18s22 7.78 22 18c0 5.63-3.19 10.74-7.32 14.8a43.6 43.6 0 0 1-14.14 9.1A1.5 1.5 0 0 1 22.5 44v-5.04C11.13 38.4 2 31.34 2 21.5M14 25a3 3 0 1 0 0-6 3 3 0 0 0 0 6m10 0a3 3 0 1 0 0-6 3 3 0 0 0 0 6m13-3a3 3 0 1 1-6 0 3 3 0 0 1 6 0" clip-rule="evenodd"/></svg>';
  var ICON_STAR = '<svg viewBox="0 0 24 24"><path fill-rule="evenodd" d="M10.788 3.21c.448-1.077 1.976-1.077 2.424 0l2.082 5.007 5.404.433c1.164.093 1.636 1.545.749 2.305l-4.117 3.527 1.257 5.273c.271 1.136-.964 2.033-1.96 1.425L12 18.354 7.373 21.18c-.996.608-2.231-.29-1.96-1.425l1.257-5.273-4.117-3.527c-.887-.76-.415-2.212.749-2.305l5.404-.433 2.082-5.006z" clip-rule="evenodd"/></svg>';
  window.ICON_HEART = ICON_HEART;
  window.ICON_COMMENT = ICON_COMMENT;
  window.ICON_STAR = ICON_STAR;

  var AVATAR_COLORS = ["#E74C3C","#3498DB","#2ECC71","#F39C12","#9B59B6","#1ABC9C","#E67E22","#34495E"];
  function avatarColor(name) {
    var h = 0;
    for (var i = 0; i < (name || "?").length; i++) h = (h * 31 + name.charCodeAt(i)) & 0xffffffff;
    return AVATAR_COLORS[Math.abs(h) % AVATAR_COLORS.length];
  }

  function fetchPage() {
    // 数据来源由 dataSource 注入（首页走 /api/videos，my 走 my_posts.json）；
    // 排序也在各自 dataSource 内完成，引擎只负责拼接。
    return dataSource.fetch(offset, PAGE).then(function (res) {
      var items = res.items || [];
      videos = videos.concat(items);
      offset = (res.nextOffset != null) ? res.nextOffset : (offset + items.length);
      hasMore = !!res.hasMore;
    });
  }

  var slideEls = [];
  for (var k = 0; k < 3; k++) {
    var s = document.createElement("div");
    s.className = "slide";
    s.innerHTML =
      '<video muted playsinline preload="auto" webkit-playsinline></video>' +
      '<div class="video-mask"></div>' +
      '<div class="tap-layer"></div>' +
      '<div class="pause-icon"><svg viewBox="0 0 24 24" fill="white"><path d="M8 5.5c0-.83.9-1.33 1.6-.83l8.5 5c.67.4.67 1.43 0 1.83l-8.5 5c-.7.5-1.6 0-1.6-.83V5.5z"/></svg></div>' +
      '<div class="note-view" style="display:none">' +
        '<div class="note-images"></div>' +
        '<div class="note-progress"></div>' +
      '</div>' +
      '<div class="audio-view" style="display:none">' +
        '<div class="audio-bg"></div>' +
        '<div class="disc-wrap paused"><img class="disc-img" src=""><div class="disc-fallback" style="display:none">♫</div></div>' +
        '<div class="disc-hint"></div>' +
        '<div class="audio-music-title"></div>' +
        '<div class="audio-music-author"></div>' +
        '<div class="audio-progress-wrap"><span class="audio-cur">00:00</span><div class="audio-progress"><div class="audio-bar"></div></div><span class="audio-dur">00:00</span></div>' +
      '</div>' +
      '<audio class="audio-el"></audio>' +
      '<audio class="note-audio" loop></audio>' +
      '<div class="meta"><div class="author"></div><div class="title"></div></div>' +
      '<div class="actions">' +
        '<div class="avatar-wrap"><div class="avatar"><img src="" style="display:none"><span class="fallback"></span></div><button class="follow-btn">+</button></div>' +
        '<button class="act like">' + ICON_HEART + '<span class="num"></span></button>' +
        '<button class="act comment">' + ICON_COMMENT + '<span class="num"></span></button>' +
        '<button class="act collect">' + ICON_STAR + '<span class="num"></span></button>' +
        '<button class="act share"><img src="/icons/share/share.png" alt="分享"><span class="num"></span></button>' +
      '</div>' +
      '<button class="music off prompt"><span class="disc"><img src="" style="display:none"></span><span class="mute-icon"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5"></polygon><path d="M15.54 8.46a5 5 0 0 1 0 7.07"></path><path d="M19.07 4.93a10 10 0 0 1 0 14.14"></path></svg></span><span class="prompt-text">取消静音</span></button>' +
      '<div class="progress-wrap">' +
        '<div class="frames"></div>' +
        '<div class="time-label">00:00 / 00:00</div>' +
        '<div class="hint">∧ 上滑可精准调节进度</div>' +
        '<div class="progress"><div class="bar"></div><div class="thumb"></div></div>' +
      '</div>';
    slider.appendChild(s);
    slideEls.push(s);
    bindSlide(s);
  }

  function fmtTime(sec) {
    sec = Math.max(0, Math.floor(sec || 0));
    var m = Math.floor(sec / 60);
    var s = sec % 60;
    return (m < 10 ? "0" : "") + m + ":" + (s < 10 ? "0" : "") + s;
  }

  function preloadNext() {
    var v = slideEls[2].querySelector("video");
    if (!v || !v.src) return;
    if (v.__preloaded && v.readyState >= 2) return;
    v.__preloaded = true;
    v.__ready = v.readyState >= 2;
    if (v.readyState < 2) {
      v.preload = "auto";
      v.load();
      v.addEventListener("loadeddata", function onLD() {
        v.removeEventListener("loadeddata", onLD);
        v.__ready = true;
      }, { once: true });
    }
  }

  function bindSlide(slide) {
    var video = slide.querySelector("video");
    var pWrap = slide.querySelector(".progress-wrap");
    var pauseIcon = slide.querySelector(".pause-icon");
    pauseIcon.classList.remove("show"); // 复用slide时清除残留暂停图标（快速滑动场景）
    var tapLayer = slide.querySelector(".tap-layer");

    // 切换暂停图标的显示
    function setPauseIcon(show) {
      if (show) pauseIcon.classList.add("show");
      else pauseIcon.classList.remove("show");
    }

    // 全屏单击层：单击暂停/继续，双击/快速连点赞，长按弹窗
    (function () {
      var lastTap = 0, lastX = 0, lastY = 0;
      var singleTapTimer = null;
      var rapidTapMode = false;
      var rapidTapTimer = null;
      var rapidTapCount = 0; // 快速连点计数器，达到7次自动进入清屏模式
      // 进入快速连点模式：屏蔽单击暂停，350ms无点击后退出
      function enterRapidTap() {
        rapidTapMode = true;
        if (rapidTapTimer) clearTimeout(rapidTapTimer);
        rapidTapTimer = setTimeout(function () {
          rapidTapMode = false;
          rapidTapTimer = null;
          rapidTapCount = 0; // 退出连点模式时重置计数器
        }, 350);
      }
      // 执行连点点赞，计数达到7次自动进入清屏模式
      function doRapidLike(slide, cx, cy) {
        doLike(slide, true, cx, cy);
        rapidTapCount++;
        if (rapidTapCount >= 7 && !cleanMode) {
          setCleanMode(true);
          showToast("清屏播放已开启");
        }
      }
      tapLayer.addEventListener("touchstart", function (e) {
        tapLayer.__tsX = e.touches[0].clientX;
        tapLayer.__tsY = e.touches[0].clientY;
        tapLayer.__tsT = Date.now();
        slide.__note_axis = null;
        slide.__note_vel = 0;
        slide.__note_lastX = e.touches[0].clientX;
        slide.__note_lastT = Date.now();
        // 预热vibrator服务连接：vibrate(0)不产生震动，但触发WebView建立连接，避免第一次长按被忽略
        if (navigator.vibrate) navigator.vibrate(0);
        // 长按检测：300ms
        slide.__lpTimer = setTimeout(function () {
          slide.__lpTimer = null;
          playVibrate()
          openLongPressMenu();
        }, 300);
      }, { passive: true });
      tapLayer.addEventListener("touchmove", function (e) {
        var dx = e.touches[0].clientX - tapLayer.__tsX;
        var dy = e.touches[0].clientY - tapLayer.__tsY;
        if (Math.abs(dx) > 10 || Math.abs(dy) > 10) {
          if (slide.__lpTimer) { clearTimeout(slide.__lpTimer); slide.__lpTimer = null; }
          if (singleTapTimer) { clearTimeout(singleTapTimer); singleTapTimer = null; }
        }
        // 图集：首次越过阈值锁定滑动轴（横向/纵向），横向优先容忍80%垂直分量，避免轻微上下抖动误判
        if (slide.__note_images > 0 && !slide.__note_axis && (Math.abs(dx) > 10 || Math.abs(dy) > 10)) {
          slide.__note_axis = (Math.abs(dx) * 0.8 > Math.abs(dy)) ? "h" : "v";
        }
        if (slide.__note_images > 0 && slide.__note_axis === "h") {
          e.preventDefault();
          window.__noteAxisH = true;
          slide.__note_dragging = true;
          if (slide.__note_manual === false) { slide.__note_manual = true; }
          if (slide.__note_timer) { clearInterval(slide.__note_timer); slide.__note_timer = null; }
          var ni = slide.querySelector(".note-images");
          var w = ni.clientWidth;
          var n = slide.__note_images;
          ni.style.scrollSnapType = 'none';
          // 方向修正：图集横滚 scrollLeft 增大=向后。手指向左滑(dx<0)应滚向下一张 => 用 -dx
          slide.__note_follow = slide.__note_idx * w - dx;
          ni.scrollTo({ left: slide.__note_follow, behavior: 'auto' });
          // 速度采样（惯性判定用）：最近一次 move 的瞬时速度 px/ms
          var nowM = Date.now();
          var dtM = nowM - (slide.__note_lastT || nowM);
          if (dtM > 0 && slide.__note_lastX !== null) {
            slide.__note_vel = (e.touches[0].clientX - slide.__note_lastX) / dtM;
          }
          slide.__note_lastX = e.touches[0].clientX;
          slide.__note_lastT = nowM;
          var displayIdx = Math.round(slide.__note_follow / w) % n;
          var bars = slide.querySelectorAll(".note-progress .bar");
          for (var k = 0; k < bars.length; k++) bars[k].classList.toggle("active", k === displayIdx);
        }
      }, { passive: false });
      // 执行单击暂停/继续
      function doSingleTap(cx, cy) {
        var isNote = slide.__note_images > 0;
        if (slide.__is_audio) {
          var ae = slide.querySelector(".audio-el");
          if (ae) {
            if (ae.paused) {
              ae.play().catch(function () {});
              setPauseIcon(false);
              setDiscPlaying(slide, true);
            } else {
              ae.pause();
              setPauseIcon(true);
              setDiscPlaying(slide, false);
              // v9.1.5：恢复"暂停退出清屏"（用户需求：清屏开启后暂停退出、上下滑动不退出、
              // 连赞/菜单可再进）。v9.1.2 误删此处导致暂停不退清屏。
              if (cleanMode) setCleanMode(false);
            }
          }
          syncMusic(slide);
        } else if (isNote) {
          var na = slide.querySelector(".note-audio");
          if (!slide.__note_paused) {
            // 暂停：图片轮播 + 背景音乐一起停
            slide.__note_paused = true;
            if (slide.__note_timer) { clearInterval(slide.__note_timer); slide.__note_timer = null; }
            if (na && na.src) { na.pause(); }
            setPauseIcon(true);
            // v9.1.5：恢复"暂停退出清屏"（用户需求：清屏开启后暂停退出、上下滑动不退出、
            // 连赞/菜单可再进）。v9.1.2 误删此处导致暂停不退清屏。
            if (cleanMode) setCleanMode(false);
          } else {
            // 继续：图片轮播 + 背景音乐一起恢复
            slide.__note_paused = false;
            if (na && na.src) { na.play().catch(function () {}); }
            setPauseIcon(false);
            if (!slide.__note_manual && slide.__note_images > 1 && !slide.__note_timer) {
              var ni = slide.querySelector(".note-images");
              var nImgs = slide.__note_images;
              slide.__note_timer = setInterval(function () {
                if (slide.__note_manual) return;
                var w = ni.clientWidth;
                slide.__note_idx++;
                if (slide.__note_idx === nImgs) {
                  // 副本（视觉=第一张）：立即无缝回 0，避免循环时突兀停留
                  ni.style.scrollSnapType = 'none';
                  ni.scrollTo({ left: 0, behavior: 'auto' });
                  slide.__note_idx = 0;
                  requestAnimationFrame(function () { ni.style.scrollSnapType = ''; });
                } else {
                  ni.scrollTo({ left: slide.__note_idx * w, behavior: 'smooth' });
                }
              }, 2000);
            }
          }
          syncMusic(slide);
        } else {
          if (video.paused) {
            video.play().catch(function () {});
            pWrap.classList.remove("paused");
            setPauseIcon(false);
          } else {
            video.pause();
            pWrap.classList.add("paused");
            setPauseIcon(true);
            // v9.1.5：恢复"暂停退出清屏"（用户需求：清屏开启后暂停退出、上下滑动不退出、
            // 连赞/菜单可再进）。v9.1.2 误删此处导致暂停不退清屏。
            if (cleanMode) setCleanMode(false);
          }
        }
      }
      tapLayer.addEventListener("touchend", function (e) {
        if (slide.__lpTimer) { clearTimeout(slide.__lpTimer); slide.__lpTimer = null; }
        window.__noteAxisH = false;
        var dx = e.changedTouches[0].clientX - tapLayer.__tsX;
        var dy = e.changedTouches[0].clientY - tapLayer.__tsY;
        var dt = Date.now() - tapLayer.__tsT;
        // 图集横向滑动结束：JS判定切图（左右循环，惯性+缓出动画，手感对齐上下滑feed）
        if (slide.__note_images > 0 && slide.__note_dragging) {
          slide.__note_dragging = false;
          slide.__note_axis = null;
          var ni = slide.querySelector(".note-images");
          var w = ni.clientWidth;
          var n = slide.__note_images;
          var th = 25;
          var vel = slide.__note_vel || 0;
          var sw = true;
          // 惯性优先：速度快（>0.35px/ms）即使位移不够也翻页；否则按位移阈值
          if (vel > 0.35) { slide.__note_idx = (slide.__note_idx - 1 + n) % n; }
          else if (vel < -0.35) { slide.__note_idx = (slide.__note_idx + 1) % n; }
          else if (dx < -th) { slide.__note_idx = (slide.__note_idx + 1) % n; }
          else if (dx > th) { slide.__note_idx = (slide.__note_idx - 1 + n) % n; }
          else { sw = false; }
          // 动画时长随速度缩短（快滑=短促，慢滑=从容），全程缓出曲线（先快后慢=惯性滑到位的质感）
          var dur = sw ? Math.max(90, Math.min(320, 260 - Math.abs(vel) * 220)) : 240;
          var doAnim = function (targetL, d) {
            var fromL = ni.scrollLeft;
            var delta = targetL - fromL;
            ni.style.scrollSnapType = 'none';
            var t0 = Date.now();
            (function step() {
              var p = Math.min(1, (Date.now() - t0) / d);
              // 缓出：1-(1-p)^3，先快后慢
              ni.scrollLeft = fromL + delta * (1 - Math.pow(1 - p, 3));
              if (p < 1) requestAnimationFrame(step);
              else ni.style.scrollSnapType = '';
            })();
          };
          if (slide.__note_idx === 0) {
            ni.style.scrollSnapType = 'none';
            requestAnimationFrame(function() {
              doAnim(0, dur);
            });
          } else {
            var targetL = slide.__note_idx * w;
            doAnim(targetL, dur);
          }
          var bars = slide.querySelectorAll(".note-progress .bar");
          for (var k = 0; k < bars.length; k++) bars[k].classList.toggle("active", k === slide.__note_idx);
          if (window.reportBehavior && slide.__vid)
            window.reportBehavior("note_swipe", slide.__vid, slide.__note_idx);
          return;
        }
        if (Math.abs(dx) > 12 || Math.abs(dy) > 12 || dt > 400) return;
        var now = Date.now();
        var cx = e.changedTouches[0].clientX, cy = e.changedTouches[0].clientY;
        var isQuickTap = (now - lastTap < 280 && Math.abs(cx - lastX) < 60);

        // 快速连点模式：完全屏蔽单击暂停
        if (rapidTapMode) {
          enterRapidTap(); // 重置连点结束计时
          if (isQuickTap) doRapidLike(slide, cx, cy);
          lastTap = now; lastX = cx; lastY = cy;
          return;
        }

        // 双击：进入快速连点模式，点赞
        if (isQuickTap) {
          if (singleTapTimer) { clearTimeout(singleTapTimer); singleTapTimer = null; }
          enterRapidTap();
          lastTap = now; lastX = cx; lastY = cy;
          doRapidLike(slide, cx, cy);
          return;
        }

        // 正常单击：延迟180ms执行，期间有第二次点击则取消
        lastTap = now; lastX = cx; lastY = cy;
        if (singleTapTimer) clearTimeout(singleTapTimer);
        singleTapTimer = setTimeout(function () {
          singleTapTimer = null;
          doSingleTap(cx, cy);
        }, 180);
      }, { passive: true });
    })();

    video.addEventListener("ended", function () {
      // 播放完的视频清除位置记录，滑回来时从头播放
      if (slide.__id) videoPositions[slide.__id] = 0;
      if (autoPlayNext && current < videos.length - 1) {
        lockSwitch();
        var nv = slideEls[2].querySelector("video");
        var pos = videoPositions[slideEls[2].__id];
        if (pos && pos > 0.5 && nv.currentTime < 0.1 && nv.duration) nv.currentTime = Math.min(pos, nv.duration - 0.5);
        nv.muted = !soundOn; nv.play().catch(function () {});
        current++;
        // 模拟向上滑动动画
        slider.style.transition = "transform .3s " + EASE;
        slider.style.transform = "translateY(-100%)";
        setTimeout(function () { resetAndLayout(1); }, 320);
      } else if (!autoPlayNext) {
        // 关闭自动联播：单视频循环
        video.currentTime = 0;
        video.play().catch(function () {});
      }
    });

    video.addEventListener("play", function () { syncMusic(slide); });
    video.addEventListener("pause", function () { syncMusic(slide); });

    // 纯音频(图文作品的MP3)/加载失败 → 显示黑色遮罩
    var mask = slide.querySelector(".video-mask");
    video.addEventListener("error", function () { if (mask) mask.classList.remove("hide"); });
    function onVideoMeta() {
      var isAudioOnly = (video.videoWidth === 0 && video.videoHeight === 0);
      var isInvalid = (!video.duration || isNaN(video.duration) || !isFinite(video.duration) || video.duration === 0);
      if (isAudioOnly || isInvalid) {
        if (mask) mask.classList.remove("hide");
      } else {
        if (mask) mask.classList.add("hide");
        applyVideoLayout(video, slide);
      }
    }
    video.addEventListener("loadedmetadata", onVideoMeta);
    // 关键：如果视频元数据已加载（缓存），立即执行排版
    if (video.readyState >= 1) {
      onVideoMeta();
    } else {
      setTimeout(onVideoMeta, 300);
      setTimeout(onVideoMeta, 800);
    }

    var progress = slide.querySelector(".progress");
    var bar = slide.querySelector(".progress .bar");
    var thumb = slide.querySelector(".progress .thumb");
    var timeLabel = slide.querySelector(".time-label");
    var hint = slide.querySelector(".hint");
    var pWrap = slide.querySelector(".progress-wrap");
    var framesEl = slide.querySelector(".frames");

    video.addEventListener("timeupdate", function () {
      if (video.duration) {
        var pct = video.currentTime / video.duration;
        bar.style.width = (pct * 100) + "%";
        thumb.style.left = (pct * 100) + "%";
      }
    });

    // 纯音频作品：进度条 + 时长
    var audioElBind = slide.querySelector(".audio-el");
    if (audioElBind) {
      audioElBind.addEventListener("loadedmetadata", function () {
        var av = slide.querySelector(".audio-view");
        if (av && audioElBind.duration)
          av.querySelector(".audio-dur").textContent = fmtTime(audioElBind.duration);
      });
      audioElBind.addEventListener("timeupdate", function () {
        var av = slide.querySelector(".audio-view");
        if (!av || !audioElBind.duration) return;
        av.querySelector(".audio-cur").textContent = fmtTime(audioElBind.currentTime);
        av.querySelector(".audio-bar").style.width =
          (audioElBind.currentTime / audioElBind.duration * 100) + "%";
      });
      audioElBind.addEventListener("ended", function () {
        setDiscPlaying(slide, false);
      });
    }

    var seeking = false, precise = false, startX = 0, startY = 0, basePct = 0, framesGenerated = false;

    pWrap.addEventListener("touchstart", function (e) {
      var t = e.touches[0];
      var w = window.innerWidth;
      // 边缘触摸不拦截，交给edgeSwipe处理
      if (t.clientX < 25 || t.clientX > w - 25) return;
      e.stopPropagation(); e.preventDefault();
      if (!video.duration) return;
      seeking = true; precise = false; framesGenerated = false;
      startX = e.touches[0].clientX; startY = e.touches[0].clientY;
      var rect = pWrap.getBoundingClientRect();
      basePct = Math.max(0, Math.min(1, (startX - rect.left) / rect.width));
      pWrap.classList.add("seeking"); pWrap.classList.remove("precise");
      hint.textContent = "∧ 上滑可精准调节进度";
      applySeek(basePct); video.pause();
    }, { passive: false });

    pWrap.addEventListener("touchmove", function (e) {
      if (!seeking) return;
      e.stopPropagation(); e.preventDefault();
      var dx = e.touches[0].clientX - startX, dy = e.touches[0].clientY - startY;
      var rect = pWrap.getBoundingClientRect();
      if (!precise && dy < -50) {
        precise = true; pWrap.classList.add("precise");
        hint.textContent = "精准调节进度中";
        if (!framesGenerated) { generateFrames(video, framesEl); framesGenerated = true; }
      }
      var sensitivity = precise ? rect.width * 2 : rect.width;
      var pct = Math.max(0, Math.min(1, basePct + dx / sensitivity));
      applySeek(pct);
    }, { passive: false });

    pWrap.addEventListener("touchend", function (e) {
      if (!seeking) return;
      e.stopPropagation(); seeking = false; precise = false;
      pWrap.classList.remove("seeking", "precise", "paused");
      if (slide.__id) videoPositions[slide.__id] = video.currentTime;
      video.play().catch(function () {});
    });

    pWrap.addEventListener("click", function (e) {
      e.stopPropagation();
      if (!video.duration) return;
      var rect = pWrap.getBoundingClientRect();
      video.currentTime = video.duration * Math.max(0, Math.min(1, (e.clientX - rect.left) / rect.width));
    });

    function applySeek(pct) {
      if (!video.duration) return;
      video.currentTime = video.duration * pct;
      bar.style.width = (pct * 100) + "%";
      thumb.style.left = (pct * 100) + "%";
      timeLabel.textContent = fmtTime(video.currentTime) + " / " + fmtTime(video.duration);
    }

    // 视觉权威博主身份：touch 动画期间 __visualIdx 已预写目标内容，点击身份不再滞后（串号根治）
    function visualSecUid() {
      var vi = (window.__visualIdx != null) ? window.__visualIdx : (slide.__idx != null ? slide.__idx : -1);
      var v = (vi >= 0 && videos[vi]) ? videos[vi] : null;
      return (v && v.sec_uid) ? v.sec_uid : (window.__currentSecUid || slide.__sec_uid || "");
    }
    // 关注按钮（调用API）
    slide.querySelector(".follow-btn").addEventListener("click", function (e) {
      e.stopPropagation();
      var secUid = visualSecUid();
      if (!secUid) { showToast("暂无博主信息"); return; }
      var btn = this;
      var isFollowing = btn.classList.contains("followed");
      fetch("/api/authors/" + encodeURIComponent(secUid) + "/follow", { method: "POST" })
        .then(function (r) { return r.json(); })
        .then(function (data) {
          if (data.is_following) {
            btn.textContent = "✓"; btn.classList.add("followed");
            followedCache[secUid] = 1;
          } else {
            btn.textContent = "+"; btn.classList.remove("followed");
            delete followedCache[secUid];
          }
          saveSet("dy_followed", followedCache);
        })
        .catch(function () { showToast("关注操作失败"); });
    });

    // 点头像：my 变体 → 博主就是自己，关闭播放器；home → 进入博主主页
    slide.querySelector(".avatar-wrap").addEventListener("click", function (e) {
      e.stopPropagation();
      if (playMode === "my") { closeMyPlayer(); return; }
      // 视觉权威身份（touch 动画期间 __visualIdx 已预写目标内容，避免取到上一屏博主导致串号）
      var secUid = visualSecUid();
      if (!secUid) { showToast("暂无博主信息"); return; }
      openProfile(secUid);
    });
    // 点博主名称：my 变体 → 关闭播放器；home → 进入博主主页
    var authorEl = slide.querySelector(".meta .author");
    if (authorEl) {
      authorEl.addEventListener("click", function (e) {
        e.stopPropagation();
        e.preventDefault();
        if (playMode === "my") { closeMyPlayer(); return; }
        var secUid = visualSecUid();
        if (!secUid) { showToast("暂无博主信息"); return; }
        openProfile(secUid);
      });
    }
    // v9.1.12r：长按头像/博主名称 → 跳官方抖音博主主页（snssdk scheme）
    (function () {
      var targets = [slide.querySelector(".avatar-wrap"), authorEl];
      targets.forEach(function (el) {
        if (!el) return;
        var lpT = null;
        el.addEventListener("touchstart", function (e) {
          e.stopPropagation();
          if (slide.__lpTimer) { clearTimeout(slide.__lpTimer); slide.__lpTimer = null; }
          lpT = setTimeout(function () {
            lpT = null;
            playVibrate()
            var secUid = visualSecUid();
            if (!secUid) { showToast("暂无博主信息"); return; }
            openDouyinApp("snssdk1128://user/profile?sec_uid=" + encodeURIComponent(secUid) + "&refer=web&needlaunchlog=1");
          }, 300);
        }, { passive: true });
        el.addEventListener("touchmove", function (e) { e.stopPropagation(); if (lpT) { clearTimeout(lpT); lpT = null; } });
        el.addEventListener("touchend", function (e) {
          e.stopPropagation();
          if (lpT) { clearTimeout(lpT); lpT = null; }
        });
      });
    })();

    slide.querySelector(".act.like").addEventListener("click", function (e) { e.stopPropagation(); doLike(slide, false); });
    slide.querySelector(".act.collect").addEventListener("click", function (e) { e.stopPropagation(); toggleCollect(slide); });
    slide.querySelector(".act.comment").addEventListener("click", function (e) { e.stopPropagation(); showToast("评论功能开发中"); });
    slide.querySelector(".act.share").addEventListener("click", function (e) {
      e.stopPropagation();
      if (this.__lpFired) { this.__lpFired = false; return; }
      doSharePassword();
    });
    // 分享：单击=复制口令+唤起(原样)；双击=复制链接；长按=跳转到散人同好主页
    // v9.1.3：用户拍板去掉弹窗选项，长按直接跳转，双击直接复制链接
    (function () {
      var sBtn = slide.querySelector(".act.share");
      var sLP = null;
      var lastTap = 0;
      var singleTimer = null;
      sBtn.addEventListener("touchstart", function (e) {
        e.stopPropagation(); // 阻止冒泡到 tapLayer 全局长按（避免350ms弹长按菜单干扰分享长按跳转）
        if (slide.__lpTimer) { clearTimeout(slide.__lpTimer); slide.__lpTimer = null; }
        sBtn.__lpFired = false;
        sLP = setTimeout(function () {
          sLP = null; sBtn.__lpFired = true;
          playVibrate()
          if (singleTimer) { clearTimeout(singleTimer); singleTimer = null; }
          jumpToSourcePeer();
        }, 300);
      }, { passive: true });
      sBtn.addEventListener("touchmove", function (e) { e.stopPropagation(); if (sLP) { clearTimeout(sLP); sLP = null; } });
      sBtn.addEventListener("touchend", function (e) {
        e.stopPropagation();
        if (sLP) { clearTimeout(sLP); sLP = null; }
        if (sBtn.__lpFired) { sBtn.__lpFired = false; e.preventDefault(); return; }
        e.preventDefault(); // 阻止合成 click，避免与 touch 双触发
        var now = Date.now();
        if (now - lastTap < 320) {
          // 双击 = 复制链接
          if (singleTimer) { clearTimeout(singleTimer); singleTimer = null; }
          lastTap = 0;
          doShareLink();
        } else {
          lastTap = now;
          // 单击延迟判断是否双击（330ms 内无第二次则执行原样 doSharePassword）
          singleTimer = setTimeout(function () { singleTimer = null; doSharePassword(); }, 330);
        }
      });
    })();
    // 音乐按钮：单击=静音切换，长按=进入音乐页
    var musicBtn = slide.querySelector(".music");
    var isLongPress = false;
    function handleMusicTap() {
      if (isLongPress) { isLongPress = false; return; }
      // 单击：静音切换
      if (musicBtn.classList.contains("prompt")) {
        hideUnmutePrompt();
        if (!soundOn) toggleGlobalMusic();
      } else {
        toggleGlobalMusic();
      }
    }
    musicBtn.addEventListener("touchend", function (e) {
      e.stopPropagation();
      e.preventDefault();
      if (slide.__musicLpTimer) { clearTimeout(slide.__musicLpTimer); slide.__musicLpTimer = null; }
      handleMusicTap();
    });
    musicBtn.addEventListener("touchstart", function (e) {
      e.stopPropagation();
      if (slide.__lpTimer) { clearTimeout(slide.__lpTimer); slide.__lpTimer = null; }
      isLongPress = false;
      // 胶囊状态（取消静音提示）下不启动长按定时器，只能取消静音
      if (!musicBtn.classList.contains("prompt")) {
        slide.__musicLpTimer = setTimeout(function () { isLongPress = true; slide.__musicLpTimer = null; playVibrate(); openMusicPage(slide); }, 27);
      }
    }, { passive: true });
    musicBtn.addEventListener("touchmove", function (e) {
      if (slide.__musicLpTimer) { clearTimeout(slide.__musicLpTimer); slide.__musicLpTimer = null; }
    }, { passive: true });
    musicBtn.addEventListener("touchcancel", function (e) {
      if (slide.__musicLpTimer) { clearTimeout(slide.__musicLpTimer); slide.__musicLpTimer = null; }
    });
    // 桌面端点击
    musicBtn.addEventListener("click", function (e) {
      e.stopPropagation();
      if ('ontouchstart' in window) return;
      handleMusicTap();
    });
    // 桌面端长按
    var desktopLongPressTimer = null;
    musicBtn.addEventListener("mousedown", function (e) {
      if ('ontouchstart' in window) return;
      // 胶囊状态（取消静音提示）下不启动长按定时器，只能取消静音
      if (!musicBtn.classList.contains("prompt")) {
        desktopLongPressTimer = setTimeout(function () { desktopLongPressTimer = null; playVibrate(); openMusicPage(slide); }, 27);
      }
    });
    musicBtn.addEventListener("mouseup", function (e) {
      if (desktopLongPressTimer) { clearTimeout(desktopLongPressTimer); desktopLongPressTimer = null; }
    });
    musicBtn.addEventListener("mouseleave", function (e) {
      if (desktopLongPressTimer) { clearTimeout(desktopLongPressTimer); desktopLongPressTimer = null; }
    });
  }

  function generateFrames(video, container) {
    container.innerHTML = '';
    if (!video.duration) return;
    var count = 6, canvas = document.createElement('canvas');
    canvas.width = 90; canvas.height = 160;
    var ctx = canvas.getContext('2d'), origTime = video.currentTime, i = 0;
    function next() {
      if (i >= count) { video.currentTime = origTime; return; }
      var t = (i / (count - 1)) * video.duration, done = false;
      function onSeeked() {
        if (done) return; done = true;
        video.removeEventListener('seeked', onSeeked);
        try {
          ctx.drawImage(video, 0, 0, 90, 160);
          var img = document.createElement('img');
          img.src = canvas.toDataURL();
          img.style.cssText = 'height:64px;border-radius:5px;flex-shrink:0;';
          container.appendChild(img);
        } catch (e) {}
        i++; setTimeout(next, 60);
      }
      video.addEventListener('seeked', onSeeked);
      video.currentTime = t;
      setTimeout(onSeeked, 800);
    }
    next();
  }

  // HEIC/无法解码图片（HTTP 200 但 naturalWidth=0、onerror 静默失败）双保险降级：
  // 事件(error) + 解码检查(complete&&naturalWidth===0) 逐级降级 chain
  // 定义在外层：fillSlide 与 openMusicPage 共用（此前在 fillSlide 内部定义，
  // openMusicPage 调用时抛 ReferenceError，导致唱片长按无法进入音乐页）
  function setChainPic(img, chain, fallbackEl) {
    var ci = 0;
    var lock = false;
    function finalFail() {
      if (img.onerror) img.onerror = null;
      img.style.display = "none";
      if (fallbackEl) fallbackEl.style.display = "flex";
    }
    function applyNext() {
      if (lock) return;
      while (ci < chain.length) {
        var s = chain[ci++];
        if (s) {
          lock = true;
          img.onerror = function () { lock = false; applyNext(); };
          img.onload = function () {
            if (img.complete && img.naturalWidth === 0) { lock = false; applyNext(); }
            else { lock = true; }
          };
          img.src = s;
          img.style.display = "block";
          if (fallbackEl) fallbackEl.style.display = "none";
          setTimeout(function () {
            if (img.complete && img.naturalWidth === 0) { lock = false; applyNext(); }
          }, 600);
          return;
        }
      }
      finalFail();
    }
    applyNext();
  }

  function fillSlide(slide, idx) {
    window.__fillLog = window.__fillLog || [];
    window.__fillLog.push({idx: idx, n: videos.length, same: slide.__id === (videos[idx]||{}).id});
    if (idx < 0 || idx >= videos.length) { slide.style.display = "none"; return; }
    slide.style.display = "";
    var v = videos[idx];
    slide.__idx = idx;
    // 核心状态最先落：即使后续渲染抛错，博主身份也已锁定（串号根治）
    slide.__sec_uid = v.sec_uid || "";
    window.__currentSecUid = v.sec_uid || "";
    // setChainPic 定义在外层（fillSlide 上方），fillSlide 与 openMusicPage 共用
    // 图片降级链：music_cover → 封面 → 头像，HEIC/解码失败自动换下一级
    if (slide.__id !== v.id) {
      var vid = slide.querySelector("video");
      var mask = slide.querySelector(".video-mask");
      // v9.1.8：mask 直接 hide，让 video 元素自身的 poster（封面图）显示。
      // 根因：mask z-index:2 在 video 上方，mask 显示时（即使有 cover_url 背景）
      // 仍会遮住 video 的第一帧；用户实测"有些视频能看到第一帧上半部分"=video
      // 已加载到 readyState>=1 触发 onVideoMeta hide 了 mask，能看到 video 第一帧；
      // "有些黑屏"=video 还没加载好 mask 还在显示，纯黑或封面图都不对（用户要的是第一帧）。
      // 正确方案：fillSlide 时直接 hide mask，video.poster 由 line 1404 设为 cover_url，
      // video 元素加载期间显示 poster（封面），加载到 readyState>=2 显示第一帧——
      // 滑动过程看到的就是 video 元素的内容（poster→第一帧），全程无黑。
      // 纯音频/error 时 onVideoMeta 或 error 事件会重新显示 mask。
      if (mask) {
        mask.classList.add("hide");
        mask.style.background = "";  // 清除上轮 cover_url 背景，回归默认 #000（仅 error 显示）
      }
      vid.style.visibility = "";
      vid.src = v.url;
      // 封面 poster：视频加载/解码期显示封面而非灰底
      if (v.cover_url) { vid.poster = v.cover_url; } else { vid.removeAttribute("poster"); }
      vid.__preloaded = false;
      vid.__ready = false;
      vid.muted = !soundOn;
      // 统一清理备用音源，防止图集/音频/视频间切换残留双音乐（双播放器根因）
      var cleanAE = slide.querySelector(".audio-el");
      var cleanNA = slide.querySelector(".note-audio");
      if (cleanAE) { cleanAE.pause(); cleanAE.removeAttribute("src"); cleanAE.load(); }
      if (cleanNA) { cleanNA.pause(); cleanNA.removeAttribute("src"); cleanNA.load(); }
      // 设置src后立即尝试排版（缓存视频元数据已就绪）
      if (vid.readyState >= 1) {
        requestAnimationFrame(function() { applyVideoLayout(vid, slide); });
      } else {
        setTimeout(function() { applyVideoLayout(vid, slide); }, 300);
        setTimeout(function() { applyVideoLayout(vid, slide); }, 800);
      }
      slide.querySelector(".progress .bar").style.width = "0%";
      slide.__id = v.id;
      // 切换到新内容时隐藏暂停图标
      var pi = slide.querySelector(".pause-icon");
      if (pi) pi.classList.remove("show");

      // 图文作品处理
      var noteView = slide.querySelector(".note-view");
      var noteImages = slide.querySelector(".note-images");
      var noteProgress = slide.querySelector(".note-progress");
      var noteAudio = slide.querySelector(".note-audio");
      var audioView = slide.querySelector(".audio-view");
      var audioEl = slide.querySelector(".audio-el");
      // 清除旧的自动轮播
      if (slide.__note_timer) { clearInterval(slide.__note_timer); slide.__note_timer = null; }
      if (v.media_type === "audio") {
        // 纯音频作品：唱片界面
        noteView.style.display = "none";
        audioView.style.display = "flex";
        vid.style.display = "none";
        // 音频内容仅用 audioEl 单一音源：禁用 video 元素，杜绝双播放器双音乐
        vid.removeAttribute("src"); vid.load();
        var discWrap = audioView.querySelector(".disc-wrap");
        var discImg = audioView.querySelector(".disc-img");
        var discFb = audioView.querySelector(".disc-fallback");
        var discHint = audioView.querySelector(".disc-hint");
        // 大唱片降级链与右下角小唱片保持一致：music_cover → cover_url → avatar（曾漏 cover_url 导致大唱片黑而小唱片有图）
        var discChain = [mediaSrc(v.music_cover), v.cover_url || "", v.avatar_url || ""];
        // 双保险降级（顶部 setChainPic：error 事件 + HEIC 解码失败检查）
        setChainPic(discImg, discChain, discFb);
        discHint.textContent = "";
        // 毛玻璃动态背景：与唱片同链（music_cover → cover_url → avatar），HEIC 失败自动换下一级
        var audioBg = audioView.querySelector(".audio-bg");
        (function setBg() {
          var bgChain = [mediaSrc(v.music_cover), v.cover_url || "", v.avatar_url || ""];
          var bi = 0;
          (function tryBg() {
            while (bi < bgChain.length) {
              var bs = bgChain[bi++];
              if (bs) {
                var probe = new Image();
                probe.onload = function () { audioBg.style.backgroundImage = "url('" + bs + "')"; };
                probe.onerror = function () { tryBg(); };
                probe.src = bs;
                return;
              }
            }
            audioBg.style.backgroundImage = "";
          })();
        })();
        audioView.querySelector(".audio-music-title").textContent = v.music_title || v.title || "(未知音乐)";
        audioView.querySelector(".audio-music-author").textContent =
          "@" + (v.music_author || v.author || "未知作者");
        slide.__is_audio = true;
        if (v.music_file) { audioEl.src = "/api/music-file/" + v.music_file; }
        audioEl.loop = false;
        audioEl.muted = !soundOn;
        audioEl.currentTime = 0;
        audioView.querySelector(".audio-cur").textContent = "00:00";
        audioView.querySelector(".audio-dur").textContent = "00:00";
        audioView.querySelector(".audio-bar").style.width = "0%";
        discWrap.classList.add("paused");
      } else if (v.is_note && v.image_list) {
        try {
          var imgs = JSON.parse(v.image_list);
          if (imgs && imgs.length > 0) {
            // 横向滑动由 tap-layer JS 接管，禁用原生横向滚动
            noteImages.classList.add("js-driven");
            // 显示图文区域，隐藏video/音频
            audioView.style.display = "none";
            noteView.style.display = "block";
            vid.style.display = "none";
            // 图集内容仅用 noteAudio 单一音源：禁用 video 元素，杜绝双播放器双音乐
            vid.removeAttribute("src"); vid.load();
            // 加载图片：N张真实 + 1张第一张副本（用于无限循环）
            noteImages.innerHTML = "";
            for (var i = 0; i < imgs.length; i++) {
              var img = document.createElement("img");
              img.src = "/api/note-image/" + imgs[i];
              img.draggable = false;
              noteImages.appendChild(img);
            }
            // 第一张的副本（无限循环用）
            var cloneImg = document.createElement("img");
            cloneImg.src = "/api/note-image/" + imgs[0];
            cloneImg.draggable = false;
            noteImages.appendChild(cloneImg);
            // 进度条：N个（不包括副本）
            noteProgress.innerHTML = "";
            for (var j = 0; j < imgs.length; j++) {
              var bar = document.createElement("div");
              bar.className = "bar" + (j === 0 ? " active" : "");
              noteProgress.appendChild(bar);
            }
            // 更新进度条
            function updateNoteProgress(idx) {
              var bars = noteProgress.querySelectorAll(".bar");
              for (var k = 0; k < bars.length; k++) {
                bars[k].classList.toggle("active", k === idx);
              }
            }
            // 监听滚动更新进度条
            noteImages.onscroll = function() {
              var w = noteImages.clientWidth;
              var rawIdx = Math.round(noteImages.scrollLeft / w);
              var displayIdx = rawIdx % imgs.length;
              updateNoteProgress(displayIdx);
              if (rawIdx > 0 && slide.__note_last_swipe_idx !== displayIdx) {
                slide.__note_last_swipe_idx = displayIdx;
                if (window.reportBehavior && slide.__vid)
                  window.reportBehavior("note_swipe", slide.__vid, displayIdx);
              }
            };
            // 手动滑动结束后，如果在副本位置，无动画跳回0
            noteImages.addEventListener("touchend", function() {
              setTimeout(function() {
                var w = noteImages.clientWidth;
                if (noteImages.scrollLeft > (imgs.length - 0.3) * w) {
                  if (window.reportBehavior && slide.__vid)
                    window.reportBehavior("note_complete", slide.__vid, 0);
                  noteImages.style.scrollSnapType = 'none';
                  requestAnimationFrame(function() {
                    noteImages.scrollTo({ left: 0, behavior: 'auto' });
                    slide.__note_idx = 0;
                    requestAnimationFrame(function() { noteImages.style.scrollSnapType = ''; });
                  });
                }
              }, 100);
            }, { passive: true });
            slide.__note_images = imgs.length;
            slide.__note_idx = 0;
            slide.__note_manual = false;
            slide.__note_paused = false;
            slide.__note_dragging = false;
            // 背景音乐
            if (v.music_file) {
              noteAudio.src = "/api/music-file/" + v.music_file;
              noteAudio.loop = true;
              noteAudio.muted = !soundOn;
            } else {
              noteAudio.src = "";
            }
            // 自动轮播（每张2秒，无限循环），手动滑动后停止
            if (imgs.length > 1) {
              slide.__note_timer = setInterval(function() {
                if (slide.__note_manual) return;
                var w = noteImages.clientWidth;
                slide.__note_idx++;
                if (slide.__note_idx === imgs.length) {
                  // 副本（视觉=第一张）：立即无缝回 0，避免循环突兀
                  if (window.reportBehavior && slide.__vid)
                    window.reportBehavior("note_complete", slide.__vid, 0);
                  noteImages.style.scrollSnapType = 'none';
                  noteImages.scrollTo({ left: 0, behavior: 'auto' });
                  slide.__note_idx = 0;
                  requestAnimationFrame(function() { noteImages.style.scrollSnapType = ''; });
                } else {
                  noteImages.scrollTo({ left: slide.__note_idx * w, behavior: 'smooth' });
                }
              }, 2000);
              // 手动滑动后进入手动模式
              noteImages.addEventListener("touchstart", function() {
                slide.__note_manual = true;
                if (slide.__note_timer) { clearInterval(slide.__note_timer); slide.__note_timer = null; }
              }, { passive: true });
            }
          }
        } catch(e) { console.warn("note parse error", e); }
      } else {
        // 普通视频：隐藏图文/音频区域
        noteView.style.display = "none";
        audioView.style.display = "none";
        vid.style.display = "";
        noteImages.innerHTML = "";
        noteProgress.innerHTML = "";
        noteAudio.src = "";
        audioEl.src = "";
        slide.__note_images = 0;
        slide.__is_audio = false;
      }
    }
    slide.querySelector(".author").textContent = "@" + (v.author || "未知作者");
    slide.querySelector(".title").textContent = v.title || "(无标题)";
    slide.__author = v.author || "";

    // 真实头像
    var av = slide.querySelector(".avatar");
    var avImg = av.querySelector("img");
    var avFb = av.querySelector(".fallback");
    if (v.avatar_url) {
      avImg.src = v.avatar_url;
      avImg.style.display = "block";
      avFb.style.display = "none";
      av.style.background = "#333";
      // 头像加载失败 → 首字兜底
      avImg.onerror = function () {
        avImg.onerror = null;
        avImg.style.display = "none";
        avFb.style.display = "flex";
        avFb.textContent = (v.author || "?").charAt(0).toUpperCase();
        av.style.background = avatarColor(v.author);
      };
    } else {
      avImg.style.display = "none";
      avFb.style.display = "flex";
      avFb.textContent = (v.author || "?").charAt(0).toUpperCase();
      av.style.background = avatarColor(v.author);
    }

    // 关注按钮状态
    var fb = slide.querySelector(".follow-btn");
    if (followedCache[v.sec_uid] || v.is_following) {
      fb.textContent = "✓"; fb.classList.add("followed");
    } else {
      fb.textContent = "+"; fb.classList.remove("followed");
    }

    // 音乐唱片封面（用img更可靠）：music_cover → 封面 → 头像 三级兜底，加载失败自动降级
    var discImg = slide.querySelector(".music .disc img");
    var discList = [mediaSrc(v.music_cover), v.cover_url || "", v.avatar_url || ""];
    // 与音频大唱片一致的 HEIC/解码失败双保险降级
    setChainPic(discImg, discList, null);

    // 点赞/收藏/评论
    var isLiked = !!liked[v.id], lb = slide.querySelector(".act.like");
    lb.classList.toggle("on", isLiked);
    lb.querySelector(".num").textContent = fmtNum((isLiked ? 1 : 0) + (Number(v.like_count) || 0));
    var isCol = !!collected[v.id], cb = slide.querySelector(".act.collect");
    cb.classList.toggle("on", isCol);
    cb.querySelector(".num").textContent = fmtNum((isCol ? 1 : 0) + (Number(v.collect_count) || 0));
    slide.querySelector(".act.comment .num").textContent = fmtNum(v.comment_count);
    slide.__vid = v.id;
    window.__fillLog.push({done: idx, id: v.id});
  }

  function layout() {
    slideEls[0].style.transform = "translateY(-100%)";
    slideEls[1].style.transform = "translateY(0)";
    slideEls[2].style.transform = "translateY(100%)";
    fillSlide(slideEls[0], current - 1);
    fillSlide(slideEls[1], current);
    fillSlide(slideEls[2], current + 1);
    // 视觉权威下标：归位/程序跳转后当前内容 = current（touch 动画期间由切换分支预写目标值）
    window.__visualIdx = current;
    var prevV = slideEls[0].querySelector("video");
    var prevNA = slideEls[0].querySelector(".note-audio");
    if (slideEls[0].__id) {
      // 播放完的视频（接近末尾）记录为0，滑回来从头播
      var isFinished = prevV.duration && prevV.currentTime > prevV.duration - 0.5;
      videoPositions[slideEls[0].__id] = isFinished ? 0 : prevV.currentTime;
    }
    prevV.pause();
    if (prevNA) prevNA.pause();
    var prevAE = slideEls[0].querySelector(".audio-el");
    if (prevAE) prevAE.pause();
    if (prevV.currentTime > 0.1) prevV.currentTime = 0;
    // 清除上一个slide的图文自动轮播
    if (slideEls[0].__note_timer) { clearInterval(slideEls[0].__note_timer); slideEls[0].__note_timer = null; }
    playCurrent();
    preloadNext();
    maybeLoadMore();
  }

  // 调试 / 自动化测试
  function typeOf(x) { return x.media_type || (x.is_note ? "album" : "video"); }
  window.feedTypes = function () {
    return videos.map(typeOf);
  };
  // 跳转到指定索引；若该索引尚未加载，自动逐页加载后再跳转。返回 Promise<true/false>
  window.goTo = function (idx) {
    idx = Number(idx);
    if (isNaN(idx) || idx < 0) return Promise.resolve(false);
    function step() {
      if (idx < videos.length) { current = idx; layout(); return Promise.resolve(true); }
      if (!hasMore) return Promise.resolve(false);
      loadingMore = true;
      return fetchPage()
        .then(function () { loadingMore = false; return step(); })
        .catch(function () { loadingMore = false; return false; });
    }
    return step();
  };
  // 逐页加载直到找到第一个指定类型（audio/album/video），并跳转；返回其索引或 -1
  window.goToFirst = function (type) {
    function scan() {
      for (var i = 0; i < videos.length; i++) {
        if (typeOf(videos[i]) === type) {
          return window.goTo(i).then(function (ok) { return ok ? i : -1; });
        }
      }
      if (!hasMore) return Promise.resolve(-1);
      loadingMore = true;
      return fetchPage()
        .then(function () { loadingMore = false; return scan(); })
        .catch(function () { loadingMore = false; return -1; });
    }
    return scan();
  };

  // 窗口大小变化时重新排版所有视频
  var resizeTimer = null;
  window.addEventListener("resize", function() {
    if (resizeTimer) clearTimeout(resizeTimer);
    resizeTimer = setTimeout(function() {
      for (var i = 0; i < slideEls.length; i++) {
        var v = slideEls[i].querySelector("video");
        if (v && v.readyState >= 1) applyVideoLayout(v, slideEls[i]);
      }
    }, 150);
  });

  var justSwiped = false;
  // 滑动切换动画锁：350ms 动画期间忽略新的切换请求，防止快速连滑导致 current/__idx 错位（串号根因）
  var animating = false;
  function lockSwitch() { animating = true; setTimeout(function () { animating = false; }, 400); }

  function setDiscPlaying(slide, playing) {
    var dw = slide.querySelector(".disc-wrap");
    if (dw) dw.classList.toggle("paused", !playing);
  }

  // 桌面浏览器自动播放策略兜底：play() 被 NotAllowedError 拒绝后，
  // 等用户首次交互（鼠标按下/触摸，统一用 pointerdown）再尝试播放当前视频。
  // APK WebView 已配置 setMediaPlaybackRequiresUserGesture(false)，正常直接播放，不会走到这里。
  var _autoplayArmed = false;
  function armAutoplayFallback() {
    if (_autoplayArmed) return;
    _autoplayArmed = true;
    function fire() {
      window.removeEventListener("pointerdown", fire, true);
      try {
        var curSlide = slideEls[1];
        var v = curSlide.querySelector("video");
        if (v && v.paused && v.readyState >= 2) v.play().catch(function () {});
      } catch (e) {}
    }
    window.addEventListener("pointerdown", fire, true);
  }
  // 统一包装：尝试播放，NotAllowedError 时自动挂兜底
  function tryPlay(v) {
    if (!v) return;
    var p = v.play();
    if (p && p.catch) p.catch(function (err) {
      if (err && err.name === "NotAllowedError") armAutoplayFallback();
    });
  }

  function playCurrent() {
    var curSlide = slideEls[1];
    var curV = curSlide.querySelector("video");
    var noteAudio = curSlide.querySelector(".note-audio");
    var audioEl = curSlide.querySelector(".audio-el");
    var pauseIcon = curSlide.querySelector(".pause-icon");
    if (pauseIcon) pauseIcon.classList.remove("show");
    curV.muted = !soundOn;
    if (curSlide.__is_audio) {
      // 纯音频作品：播放 audio-el，唱片旋转
      if (audioEl) {
        audioEl.muted = !soundOn;
        if (audioEl.paused) audioEl.play().catch(function () {});
      }
      setDiscPlaying(curSlide, true);
    } else if (curSlide.__note_images > 0) {
      // 图文作品：播放背景音乐
      if (window.reportBehavior && curSlide.__vid)
        window.reportBehavior("note_view", curSlide.__vid, 0);
      if (noteAudio.src) {
        noteAudio.muted = !soundOn;
        noteAudio.play().catch(function () {});
      }
    } else {
      // 普通视频
      if (curV.paused) {
        var pos = videoPositions[curSlide.__id];
        if (pos && pos > 0.5 && curV.currentTime < 0.1 && curV.duration) {
          curV.currentTime = Math.min(pos, curV.duration - 0.5);
        }
        if (curV.readyState >= 2) {
          tryPlay(curV);
        } else {
          curV.addEventListener("loadeddata", function onLD() {
            curV.removeEventListener("loadeddata", onLD);
            tryPlay(curV);
          }, { once: true });
        }
      }
    }
    syncMusic(curSlide);
    slideEls[2].querySelector("video").pause();
    var nextNoteAudio = slideEls[2].querySelector(".note-audio");
    if (nextNoteAudio) nextNoteAudio.pause();
    var nextAE = slideEls[2].querySelector(".audio-el");
    if (nextAE) nextAE.pause();
  }

  function toggleGlobalMusic() {
    soundOn = !soundOn;
    for (var i = 0; i < slideEls.length; i++) {
      var v = slideEls[i].querySelector("video");
      var na = slideEls[i].querySelector(".note-audio");
      var aeb = slideEls[i].querySelector(".audio-el");
      v.muted = !soundOn;
      if (na) na.muted = !soundOn;
      if (aeb) aeb.muted = !soundOn;
      syncMusic(slideEls[i]);
    }
    if (soundOn) {
      var curSlide = slideEls[1];
      if (curSlide.__is_audio) {
        var aec = curSlide.querySelector(".audio-el");
        if (aec && aec.paused) aec.play().catch(function () {});
        setDiscPlaying(curSlide, true);
      } else if (curSlide.__note_images > 0) {
        var na = curSlide.querySelector(".note-audio");
        if (na && na.src) na.play().catch(function () {});
      } else {
        curSlide.querySelector("video").play().catch(function () {});
      }
      hideUnmutePrompt();
    }
  }

  // APK音量键调用：按音量加/减自动解除静音
  window.unmute = function() {
    if (!soundOn) toggleGlobalMusic();
  };

  function syncMusic(slide) {
    var m = slide.querySelector(".music"), v = slide.querySelector("video");
    var noteAudio = slide.querySelector(".note-audio");
    var audioEl = slide.querySelector(".audio-el");
    if (!m || !v) return;
    // 图文作品用noteAudio状态，纯音频用audioEl状态，普通视频用video状态
    var isNote = slide.__note_images > 0;
    var muted = isNote ? noteAudio.muted : (slide.__is_audio ? audioEl.muted : v.muted);
    var paused = isNote ? noteAudio.paused : (slide.__is_audio ? audioEl.paused : v.paused);
    m.classList.toggle("on", !muted);
    m.classList.toggle("off", muted);
    m.classList.toggle("playing", !paused && !muted);
  }

  function doLike(slide, forceOn, x, y) {
    var b = slide.querySelector(".act.like"), id = slide.__vid;
    var on = forceOn ? true : !b.classList.contains("on");
    b.classList.toggle("on", on);
    if (on) liked[id] = 1; else delete liked[id];
    saveSet("dy_liked", liked);
    if (on && window.reportBehavior) window.reportBehavior("like", id, 0);
    b.querySelector(".num").textContent = fmtNum((on ? 1 : 0) + (Number(videos[current].like_count) || 0));
    if (on && x !== undefined) {
      var h = document.createElement("div");
      h.className = "burst-heart show";
      h.style.left = x + "px"; h.style.top = y + "px";
      h.innerHTML = ICON_HEART;
      document.body.appendChild(h);
      setTimeout(function () { h.remove(); }, 850);
    }
  }

  function toggleCollect(slide) {
    var b = slide.querySelector(".act.collect"), id = slide.__vid;
    var on = !b.classList.contains("on");
    b.classList.toggle("on", on);
    if (on) collected[id] = 1; else delete collected[id];
    saveSet("dy_collected", collected);
    if (on && window.reportBehavior) window.reportBehavior("collect", id, 0);
    b.querySelector(".num").textContent = fmtNum((on ? 1 : 0) + (Number(videos[current].collect_count) || 0));
  }

  var __vbCount = 0;
  function playVibrate() {
    if (navigator.vibrate) navigator.vibrate([50]);
  }

  function showToast(msg) {
    toast.textContent = msg; toast.classList.add("show");
    setTimeout(function () { toast.classList.remove("show"); }, 1500);
  }

  // ===== 分享：抖音口令机制 =====
  function contentLink(v) {
    var id = v.aweme_id || v.id || "";
    if (v.is_note || v.media_type === "album") return "https://www.douyin.com/note/" + id;
    if (v.media_type === "audio") return "https://www.douyin.com/music/" + id;
    return "https://www.douyin.com/video/" + id;
  }
  // 媒体文件相对名 → /api/ 前缀（music_cover 存的是 {aweme_id}.jpg 文件名；http 直链/接口已带 /api/ 前缀的不动）
  function mediaSrc(name) {
    if (!name) return "";
    if (name.indexOf("http") === 0 || name.indexOf("/") === 0) return name;
    return "/api/music-cover/" + name;
  }
  function buildShareText(v) {
    var author = v.author || "";
    var title = String(v.title || "").replace(/[\r\n#]+/g, " ").slice(0, 80);
    var head = (Math.random() * 9 + 0.1).toFixed(2);
    return head + " 复制打开抖音，看看【" + author + "的作品】" + title + " " + contentLink(v) + " 复制此链接，打开Dou音搜索，直接观看视频！";
  }
  function copyToClipboard(text) {
    if (window.AndroidBridge && window.AndroidBridge.copyText) {
      try { window.AndroidBridge.copyText(text); return true; } catch (e) {}
    }
    try {
      if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(text);
        return true;
      }
    } catch (e) {}
    try {
      var ta = document.createElement("textarea");
      ta.value = text;
      ta.style.position = "fixed";
      ta.style.opacity = "0";
      document.body.appendChild(ta);
      ta.select();
      var ok = document.execCommand("copy");
      document.body.removeChild(ta);
      return ok;
    } catch (e) {}
    return false;
  }
  // 抖音 schema 深链（snssdk1128），直达作品/音乐详情页，不依赖剪贴板口令识别
  function deepLink(v) {
    var id = v.aweme_id || v.id || "";
    return "snssdk1128://aweme/detail/" + id + "?refer=web&needlaunchlog=1";
  }
  function openDouyinApp(deepLinkUrl) {
    var dl = deepLinkUrl || "snssdk1128://";
    // APK 环境：AndroidBridge 原生调起（v4 起支持 schema 参数）；浏览器环境：直接跳 scheme
    if (window.AndroidBridge && window.AndroidBridge.openDouyin) {
      try { window.AndroidBridge.openDouyin(dl); return true; } catch (e) {}
    }
    try { window.location.href = dl; return true; } catch (e) {}
    return false;
  }
  function openShareSheet() {
    document.getElementById("shareSheet").classList.add("show");
  }
  function closeShareSheet() {
    document.getElementById("shareSheet").classList.remove("show");
  }
  // 单击分享：复制口令 + 调起官方抖音（跳转定时器存句柄，双击时可取消，避免残留跳转）
  var sharePasswordTimer = null;
  function doSharePassword() {
    var v = videos[current];
    if (!v) return;
    var ok = copyToClipboard(buildShareText(v));
    if (sharePasswordTimer) { clearTimeout(sharePasswordTimer); sharePasswordTimer = null; }
    sharePasswordTimer = setTimeout(function () { sharePasswordTimer = null; openDouyinApp(deepLink(v)); }, 350);
  }
  // 长按/双击分享：只复制链接（Web 不弹 toast，统一由 APK 原生提示"链接已复制"）
  function doShareLink() {
    var v = videos[current];
    if (!v) return;
    var ok = copyToClipboard(contentLink(v));
    if (sharePasswordTimer) { clearTimeout(sharePasswordTimer); sharePasswordTimer = null; }
  }
  // v9.1.3：跳转到散人同好（视频来源节点）主页——fetch /api/videos/{vid}/peers，
  // 取权重最高且有 sec_uid 的同好，用 snssdk1128 scheme 唤起抖音进其主页。
  // 服务端路由兜底：likes 类走 video_peer_sources；posts 类走"作者=peer"匹配（覆盖所有视频）
  function jumpToSourcePeer() {
    var v = videos[current];
    if (!v) { showToast("视频信息不存在"); return; }
    showToast("正在查询来源同好…");
    var authorSecUid = v.sec_uid || "";
    fetch("/api/videos/" + v.id + "/peers")
      .then(function (r) { return r.json(); })
      .then(function (data) {
        var items = data.items || [];
        var peer = null;
        for (var i = 0; i < items.length; i++) {
          // v9.1.4：排除博主自己（兜底"作者=peer"会匹配到博主，跳到博主主页而非来源同好）
          if (items[i].sec_uid && items[i].sec_uid !== authorSecUid) { peer = items[i]; break; }
        }
        if (!peer) { showToast(items.length ? "来源同好缺少主页信息" : "该视频暂无来源同好"); return; }
        showToast("跳转同好：" + (peer.nickname || "未知"));
        setTimeout(function () {
          openDouyinApp("snssdk1128://user/profile?sec_uid=" + encodeURIComponent(peer.sec_uid) + "&refer=web&needlaunchlog=1");
        }, 350);
      })
      .catch(function () { showToast("查询来源同好失败"); });
  }

  // 长按弹窗
  // ===== 长按菜单（方案B：iframe 优先 + 内联兜底）=====
  function getCurrentVidSafe() {
    return (typeof window.__currentVid === "function") ? window.__currentVid() : null;
  }
  function getFeedbackStateSafe(cv) {
    return (typeof window.__getFeedbackState === "function") ? window.__getFeedbackState(cv) : {};
  }
  function hasAnyFeedbackSafe(cv) {
    return cv && (typeof window.__hasAnyFeedback === "function") ? window.__hasAnyFeedback(cv) : false;
  }

  // 刷新 iframe 菜单状态
  function refreshMenuFrame() {
    var f = document.getElementById("menuFrame");
    if (!f || !f.contentWindow) return;
    var cv = getCurrentVidSafe();
    var st = getFeedbackStateSafe(cv);
    var hf = hasAnyFeedbackSafe(cv);
    try { f.contentWindow.postMessage({ type: "state", payload: { feedbackState: st, hasFeedback: !!hf } }, "*"); } catch (e) {}
  }

  function openLongPressMenu() {
    // 方案B：优先用 iframe 独立菜单（menu.html，层级与播放器隔离）
    var f = document.getElementById("menuFrame");
    var cv = getCurrentVidSafe();
    var st = getFeedbackStateSafe(cv);
    var hf = hasAnyFeedbackSafe(cv);
    if (f && f.contentWindow) {
      f.style.display = "block";
      try {
        f.contentWindow.postMessage({ type: "open", payload: { currentId: cv, feedbackState: st, hasFeedback: !!hf } }, "*");
        return;
      } catch (e) {}
    }
    // 兜底：内联菜单
    openLongPressMenuInline(cv, st, hf);
  }

  function openLongPressMenuInline(cv, st, hf) {
    var mask = document.getElementById("longPressMask");
    if (!mask) return;
    var csw = document.getElementById("lpCleanSwitch");
    var dm = document.getElementById("lpDefaultMuteSwitch");
    var da = document.getElementById("lpDefaultAutoPlaySwitch");
    if (cleanMode) csw.classList.add("on"); else csw.classList.remove("on");
    if (dm) { try { if (localStorage.getItem("dy_default_mute") !== "1") dm.classList.add("on"); else dm.classList.remove("on"); } catch (e) {} }
    if (da) { try { if (localStorage.getItem("dy_default_autoplay") === "1") da.classList.add("on"); else da.classList.remove("on"); } catch (e) {} }
    try {
      var ritualNow = localStorage.getItem("dy_jump_ritual") || "s3";
      var rsw = document.getElementById("lpDefaultCleanSwitch");
      if (rsw) rsw.classList.toggle("on", ritualNow !== "s1");
    } catch (e) {}
    try {
      var niIc = document.getElementById("lpNotInterestedIcon");
      if (niIc) niIc.style.color = st.not_interested ? "#fe2c55" : "";
      var slIc = document.getElementById("lpSuperLikeIcon");
      if (slIc) { slIc.style.color = st.super_like ? "#8B008B" : ""; var slSv = slIc.querySelector("svg"); if (slSv) slSv.setAttribute("fill", st.super_like ? "#8B008B" : "none"); }
      var scIc = document.getElementById("lpSecretLikeIcon");
      if (scIc) { scIc.style.color = st.secret_like ? "#ffc107" : ""; var scSv = scIc.querySelector("svg"); if (scSv) scSv.setAttribute("fill", st.secret_like ? "#ffc107" : "none"); }
      var pz = document.getElementById("lpPuzzleIcon");
      if (pz) {
        if (st.puzzle) { pz.style.color = "#fff"; pz.style.background = "#34c759"; pz.style.borderRadius = "4px"; }
        else { pz.style.color = ""; pz.style.background = ""; pz.style.borderRadius = ""; }
      }
    } catch (e) {}
    try {
      var niArrow = document.getElementById("lpNotInterestedArrow");
      if (niArrow) { niArrow.textContent = hf ? "已反馈 \u203a" : "\u203a"; }
    } catch (e) {}
    mask.style.display = "flex";
  }
  function closeLongPressMenu() {
    document.getElementById("longPressMask").style.display = "none";
    var _jm2 = document.getElementById("jumpRitualMask");
    if (_jm2) _jm2.style.display = "none";
    var _f2 = document.getElementById("menuFrame");
    if (_f2) { _f2.style.display = "none"; try { _f2.contentWindow.postMessage({ type: "close" }, "*"); } catch(e) {} }
  }

  // 反馈类菜单（超级喜欢/迷惑视频/不感兴趣/偷偷喜欢）：
  // 记录反馈 → 关菜单 → 按"跳转仪式"方案切下一个视频。
  // 之前这四个内联元素只画了 UI、没绑事件，iframe 点击最终 el.click() 无任何反应 → 功能失效。
  function handleFeedback(kind) {
    var vid = getCurrentVidSafe();
    if (!vid) { showToast("视频信息不存在"); return; }
    try { markFeedback(vid, kind); } catch (e) {}
    window.__lastFeedbackKind = kind;
    try { if (window.reportBehavior) window.reportBehavior("feedback_" + kind, vid, 0); } catch (e) {}
    closeLongPressMenu();
    if (window.goNextSlide) window.goNextSlide();
  }
  function bindFeedbackBtn(id, kind) {
    var b = document.getElementById(id);
    if (b) b.addEventListener("click", function () { handleFeedback(kind); });
  }
  bindFeedbackBtn("lpSuperLike", "super_like");
  bindFeedbackBtn("lpPuzzle", "puzzle");
  bindFeedbackBtn("lpNotInterested", "not_interested");
  bindFeedbackBtn("lpSecretLike", "secret_like");

  // 方案B：iframe 菜单点击分发（复用内联隐藏 DOM 的 click，逻辑零改动）
  window.addEventListener("message", function (e) {
    var d = e.data || {};
    if (!d.action) return;
    if (d.action === "click" && d.selector) {
      var el = document.querySelector(d.selector);
      if (el) el.click();
      refreshMenuFrame();
      // 反馈/下载类（menu.html 已标注 close=true）：同步隐藏 iframe + 内联 mask + 跳转仪式窗
      if (d.close) {
        var _fc = document.getElementById("menuFrame");
        if (_fc) { _fc.style.display = "none"; try { _fc.contentWindow.postMessage({ type: "close" }, "*"); } catch (e2) {} }
        var _mc = document.getElementById("longPressMask");
        if (_mc) _mc.style.display = "none";
        var _jc = document.getElementById("jumpRitualMask");
        if (_jc) _jc.style.display = "none";
      }
    } else if (d.action === "ritual" && d.s) {
      var it = document.querySelector('#jumpRitualMask [data-ritual="' + d.s + '"]');
      if (it) it.click();
      refreshMenuFrame();
    } else if (d.action === "ritual_custom") {
      var cu = document.querySelector("#jumpRitualCustom");
      if (cu) cu.click();
      refreshMenuFrame();
    } else if (d.action === "close") {
      closeLongPressMenu();
    }
  });

  function fmtNum(n) {
    n = Number(n) || 0;
    if (n >= 10000) return (n / 10000).toFixed(1).replace(/\.0$/, "") + "w";
    return String(n);
  }

  function maybeLoadMore() {
    if (hasMore && !loadingMore && current >= videos.length - 3) {
      loadingMore = true;
      fetchPage().then(function () { loadingMore = false; }).catch(function () { loadingMore = false; });
    }
  }

  // ===== 朋友页面 =====
  var friendsPageEl = document.getElementById("friendsPage");
  var friendsListEl = document.getElementById("friendsList");
  var friendsEmptyEl = document.getElementById("friendsEmpty");

  function formatVisitTime(ts) {
    if (!ts) return "从未访问";
    var now = Math.floor(Date.now() / 1000);
    var diff = now - ts;
    if (diff < 60) return "刚刚";
    if (diff < 3600) return Math.floor(diff / 60) + "分钟前";
    if (diff < 86400) return Math.floor(diff / 3600) + "小时前";
    if (diff < 2592000) return Math.floor(diff / 86400) + "天前";
    var d = new Date(ts * 1000);
    return (d.getMonth() + 1) + "月" + d.getDate() + "日";
  }

  function openFriendsPage() {
    if (!friendsPageEl) return;
    loadFriendsList();
    friendsPageEl.classList.add("show");
    currentPage = "friends";
  }

  function closeFriendsPage() {
    friendsPageEl.classList.remove("show");
    if (currentPage === "friends") {
      currentPage = "home";
      resumeCurrentVideo();
    }
  }

  function loadFriendsList() {
    fetch("/api/friends")
      .then(function (r) { return r.json(); })
      .then(function (data) {
        renderFriendsList(data.items || []);
      })
      .catch(function () {
        renderFriendsList([]);
      });
  }

  function renderFriendsList(friends) {
    friendsListEl.innerHTML = "";
    if (!friends || friends.length === 0) {
      friendsEmptyEl.style.display = "block";
      return;
    }
    friendsEmptyEl.style.display = "none";
    friends.forEach(function (f) {
      var item = document.createElement("div");
      item.className = "friend-item";
      item.innerHTML =
        '<img class="friend-avatar" src="' + (f.avatar || '/api/avatar/default.jpg') + '" onerror="this.style.background=\'#ddd\';this.src=\'\'">' +
        '<div class="friend-info">' +
        '<div class="friend-name">' + (f.nickname || f.douyin_id || "未知用户") + '</div>' +
        '<div class="friend-visit">' + formatVisitTime(f.last_visit_time) + '</div>' +
        '</div>' +
        '<div class="friend-arrow">›</div>';
      item.addEventListener("click", function () {
        // 更新最后访问时间
        fetch("/api/friends/" + f.sec_uid + "/visit", { method: "POST" }).catch(function () {});
        closeFriendsPage();
        // 进入博主主页
        setTimeout(function () { openProfile(f.sec_uid); }, 150);
      });
      friendsListEl.appendChild(item);
    });
  }

  if (variant === "home") {
    document.getElementById("friendsMenu").addEventListener("click", function() { showToast("菜单功能开发中"); });
    document.getElementById("friendsAdd").addEventListener("click", function() { showToast("添加朋友功能开发中"); });
    document.getElementById("friendsSearch").addEventListener("click", function() { showToast("搜索功能开发中"); });
  }

  // ===== 页面切换系统 =====
  var currentPage = variant === "my" ? "profile" : "home";
  var messagesPageEl = document.getElementById("messagesPage");
  var profilePageEl = document.getElementById("profilePage");
  var myPlayerOpen = false;   // my 变体：播放器是否打开（否则停留在我页）

  function pauseAllMedia() {
    // 暂停所有视频和音乐
    var slides = document.querySelectorAll(".slide video");
    slides.forEach(function (v) { v.pause(); });
    var noteAudios = document.querySelectorAll(".note-audio");
    noteAudios.forEach(function (a) { a.pause(); });
    var audioEls = document.querySelectorAll(".audio-el");
    audioEls.forEach(function (a) { a.pause(); });
  }

  function resumeCurrentVideo() {
    // 恢复当前视频播放
    var curSlide = slideEls[1];
    if (curSlide) {
      if (curSlide.__is_audio) {
        var aex = curSlide.querySelector(".audio-el");
        if (aex) { aex.muted = !soundOn; aex.play().catch(function () {}); }
        setDiscPlaying(curSlide, true);
        return;
      }
      var v = curSlide.querySelector("video");
      if (v) {
        v.muted = !soundOn;
        v.play().catch(function () {});
      }
      var na = curSlide.querySelector(".note-audio");
      if (na && na.src && soundOn) {
        na.muted = false;
        na.play().catch(function () {});
      }
    }
  }

  function closeAllPages() {
    if (friendsPageEl) friendsPageEl.classList.remove("show");
    if (messagesPageEl) messagesPageEl.classList.remove("show");
    if (profilePageEl) profilePageEl.classList.remove("show");
  }

  // 导航栏页面顺序
  var pageOrder = ["home", "friends", "messages", "profile"];

  function switchToAdjacentPage(direction) {
    // direction: -1=右滑(上一个), 1=左滑(下一个)
    var idx = pageOrder.indexOf(currentPage);
    if (idx < 0) return;
    var newIdx = idx + direction;
    if (newIdx >= 0 && newIdx < pageOrder.length) {
      switchPage(pageOrder[newIdx]);
    }
  }

  function updateTabActive(page) {
    document.querySelectorAll(".tabbar .tab").forEach(function (t) {
      t.classList.remove("active");
      var text = t.textContent.trim();
      if (page === "home" && text.indexOf("首页") === 0) t.classList.add("active");
      else if (page === "friends" && text.indexOf("朋友") === 0) t.classList.add("active");
      else if (page === "messages" && text.indexOf("消息") === 0) t.classList.add("active");
      else if (page === "profile" && (t.id === "tabMe" || text.indexOf("我") === 0)) t.classList.add("active");
    });
  }

  function switchPage(page) {
    if (currentPage === page) return;
    if (page === "home") {
      // 必须先关闭朋友/消息/我页，否则它们的 .show 层会盖在首页播放器之上
      // （现象：从朋友/消息点首页，画面仍停留在朋友/消息页）
      closeAllPages();
      if (profilePageEl) { profilePageEl.style.display = ""; }
      // enterHomePlayer 处理 my→home 数据源切换 + 视图 + 播放
      enterHomePlayer();
      currentPage = "home";
      var _tb0 = document.querySelector(".tabbar");
      if (_tb0) _tb0.classList.remove("tabbar-light");
      updateTabActive("home");
      return;
    }
    closeAllPages();
    pauseAllMedia();
    if (page === "friends") openFriendsPage();
    else if (page === "messages") messagesPageEl.classList.add("show");
    else if (page === "profile") profilePageEl.classList.add("show");
    currentPage = page;
    // 非首页 tabbar 纯白（用户需求）
    var _tbEl = document.querySelector(".tabbar");
    if (_tbEl) { _tbEl.classList.add("tabbar-light"); }
    updateTabActive(page);
  }

  // 加号：确认后清除所有本地数据并重启
  function doClearData() {
    if (confirm("确定要清除所有本地数据并重启应用吗？")) {
      try { localStorage.clear(); } catch (e) {}
      try { sessionStorage.clear(); } catch (e) {}
      location.reload();
    }
  }

  // 底部导航tab点击（单页：全部页面内切换，不刷新、URL 不变）
  document.querySelectorAll(".tabbar .tab").forEach(function (tab) {
    tab.addEventListener("click", function (e) {
      var text = tab.textContent.trim();
      if (text.indexOf("首页") === 0) {
        switchPage("home");
      } else if (text.indexOf("朋友") === 0) {
        switchPage("friends");
      } else if (text.indexOf("消息") === 0) {
        switchPage("messages");
      } else if (tab.id === "tabMe" || text.indexOf("我") === 0) {
        if (window.__iconPickerOpen) { e.stopPropagation(); e.preventDefault(); return; }
        // 若当前在我的播放器，先关闭回九宫格
        if (myPlayerOpen) { closeMyPlayer(); return; }
        switchPage("profile");
      } else if (text.indexOf("+") === 0) {
        doClearData();
      }
    });
  });

    // ===== 自定义"我"页图标：长按底部"我"tab 弹窗选图（PNG/WebP/JPG 作为新 APP 图标）=====
    function myIconPreviewData() { var d = null; try { d = localStorage.getItem("dy_tab_me_icon"); } catch(e){} return d; }
    function myIconApplyToTab(dataUrl) {
      var t = document.getElementById("tabMe");
      if (!t) return;
      if (dataUrl) t.innerHTML = '<img src="' + dataUrl + '" style="width:26px;height:26px;border-radius:8px;object-fit:cover;" alt="我">';
      else t.innerHTML = "我";
    }
    function openIconPicker() {
      var m = document.getElementById("iconPickerModal");
      if (!m) return;
      var prev = myIconPreviewData();
      document.getElementById("iconPickerPreview").src = prev || "";
      document.getElementById("iconPickerPreview").style.display = prev ? "block" : "none";
      window.__iconPickerOpen = true;
      m.style.display = "flex";
      var fi = document.getElementById("iconFileInput");
      fi.value = ""; fi.dataset.pending = "";
    }
    function closeIconPicker() {
      var m = document.getElementById("iconPickerModal");
      if (m) m.style.display = "none";
      window.__iconPickerOpen = false;
    }
    document.getElementById("iconPickBtn").addEventListener("click", function (e) {
      e.stopPropagation();
      document.getElementById("iconFileInput").click();
    });
    document.getElementById("iconFileInput").addEventListener("change", function () {
      var f = this.files && this.files[0];
      if (!f) return;
      if (!/image\/(png|webp|jpeg|jpg)/.test(f.type)) { showToast("仅支持 PNG/WebP/JPG 图片"); return; }
      var rd = new FileReader(), inp = this;
      rd.onload = function () {
        document.getElementById("iconPickerPreview").src = rd.result;
        document.getElementById("iconPickerPreview").style.display = "block";
        inp.dataset.pending = rd.result;
      };
      rd.readAsDataURL(f);
    });
    document.getElementById("iconApplyBtn").addEventListener("click", function (e) {
      e.stopPropagation();
      var inp = document.getElementById("iconFileInput");
      var data = inp.dataset.pending || "";
      try { if (data) localStorage.setItem("dy_tab_me_icon", data); else localStorage.removeItem("dy_tab_me_icon"); } catch(_) {}
      myIconApplyToTab(data || null);
      closeIconPicker();
      showToast(data ? "已设置新图标" : "已恢复默认图标");
    });
    document.getElementById("iconCancelBtn").addEventListener("click", function (e) { e.stopPropagation(); closeIconPicker(); });
    document.getElementById("iconPickerModal").addEventListener("click", function (e) { if (e.target === this) closeIconPicker(); });
    (function () {
      var meTab = document.getElementById("tabMe");
      if (!meTab) return;
      var lpTimer = null, fired = false;
      meTab.addEventListener("touchstart", function () {
        fired = false;
        lpTimer = setTimeout(function () { lpTimer = null; fired = true; try { navigator.vibrate && navigator.vibrate(30); } catch(_) {} openIconPicker(); }, 450);
      }, { passive: true });
      meTab.addEventListener("touchmove", function () { if (lpTimer) { clearTimeout(lpTimer); lpTimer = null; } }, { passive: true });
      meTab.addEventListener("touchend", function (e) {
        if (lpTimer) { clearTimeout(lpTimer); lpTimer = null; }
        if (fired) { fired = false; e.preventDefault(); e.stopPropagation(); }
      });
      var mdT = null;
      meTab.addEventListener("mousedown", function () { mdT = setTimeout(function () { mdT = null; openIconPicker(); }, 450); });
      meTab.addEventListener("mouseup", function () { if (mdT) { clearTimeout(mdT); mdT = null; } });
      var saved = myIconPreviewData();
      if (saved) myIconApplyToTab(saved);
    })();

  // ===== 博主主页 =====
  var profileEl = document.getElementById("profile");
  var currentProfileSecUid = "";
  var profileAutoLoadTimer = null;
  var profileLowerLoaded = false;

  function fmtNumWan(n) {
    n = Number(n) || 0;
    if (n >= 10000) return (n / 10000).toFixed(1).replace(/\.0$/, "") + "万";
    return String(n);
  }

  function openProfile(secUid) {
    if (!profileEl) return;
    currentProfileSecUid = secUid;
    profileLowerLoaded = false;
    pauseAllMedia();
    profileEl.classList.add("show");
    document.getElementById("profileGrid").innerHTML = "";
    document.getElementById("profileEmpty").style.display = "none";
    document.getElementById("profileLoading").style.display = "block";
    document.querySelectorAll(".profile-tab").forEach(function(t) { t.classList.remove("active"); });
    document.querySelector('.profile-tab[data-tab="works"]').classList.add("active");
    loadProfileData(secUid);
    if (profileAutoLoadTimer) clearTimeout(profileAutoLoadTimer);
    profileAutoLoadTimer = setTimeout(function() {
      if (!profileLowerLoaded && currentProfileSecUid) {
        loadProfileLower(currentProfileSecUid);
      }
    }, 4000);
  }

  function closeProfile() {
    profileEl.classList.remove("show");
    currentProfileSecUid = "";
    if (profileAutoLoadTimer) { clearTimeout(profileAutoLoadTimer); profileAutoLoadTimer = null; }
    if (currentPage === "home") resumeCurrentVideo();
  }

  if (variant === "home") {
  document.getElementById("profileBack").addEventListener("click", closeProfile);
  document.getElementById("profileMore").addEventListener("click", function () { showToast("更多功能开发中"); });
  document.getElementById("profileSearch").addEventListener("click", function () {
    if (currentProfileSecUid) loadProfileLower(currentProfileSecUid);
  });
  document.getElementById("profileMsg").addEventListener("click", function () { showToast("私信功能开发中"); });
  document.getElementById("bioMore").addEventListener("click", function () {
    var bioEl = document.getElementById("profileBio");
    var isExp = bioEl.classList.toggle("expanded");
    this.textContent = isExp ? "收起" : "更多";
  });

  document.querySelectorAll(".profile-tab").forEach(function(tab) {
    tab.addEventListener("click", function() {
      document.querySelectorAll(".profile-tab").forEach(function(t) { t.classList.remove("active"); });
      tab.classList.add("active");
      var tabName = tab.getAttribute("data-tab");
      if (tabName === "works") {
        loadProfileVideos(currentProfileSecUid);
      } else {
        document.getElementById("profileGrid").innerHTML = "";
        document.getElementById("profileEmpty").style.display = "block";
        document.getElementById("profileEmpty").textContent = tabName === "likes" ? "喜欢的视频" : "收藏的视频";
      }
    });
  });

  document.getElementById("profileFollow").addEventListener("click", function () {
    if (!currentProfileSecUid) return;
    var btn = this;
    fetch("/api/authors/" + encodeURIComponent(currentProfileSecUid) + "/follow", { method: "POST" })
      .then(function (r) { return r.json(); })
      .then(function (data) {
        if (data.is_following) {
          btn.textContent = "已关注"; btn.classList.add("followed");
          followedCache[currentProfileSecUid] = 1;
        } else {
          btn.textContent = "+ 关注"; btn.classList.remove("followed");
          delete followedCache[currentProfileSecUid];
        }
        saveSet("dy_followed", followedCache);
        layout();
      })
      .catch(function () { showToast("关注操作失败"); });
  });
  }

  function loadProfileData(secUid) {
    fetch("/api/authors/" + encodeURIComponent(secUid))
      .then(function (r) { return r.json(); })
      .then(function (data) {
        if (data.error) { showToast("获取博主信息失败"); return; }
        try {
          renderProfileInfo(data, secUid);
        } catch (e) {
          window.__profileErr = String(e && e.stack || e);
          showToast("主页渲染异常");
        }
      })
      .catch(function () {
        document.getElementById("profileLoading").style.display = "none";
        showToast("加载失败");
      });
  }

  function loadProfileLower(secUid) {
    profileLowerLoaded = true;
    loadProfileVideos(secUid);
  }

  function loadProfileVideos(secUid) {
    document.getElementById("profileLoading").style.display = "block";
    document.getElementById("profileEmpty").style.display = "none";
    // 先获取本地视频
    fetch("/api/authors/" + encodeURIComponent(secUid) + "/videos?source=local&limit=50")
      .then(function (r) { return r.json(); })
      .then(function (localData) {
        var localItems = localData.items || [];
        // 本地不足9条时，从抖音远程补充（15秒超时）
        if (localItems.length < 9) {
          var controller = new AbortController();
          var timeoutId = setTimeout(function() { controller.abort(); }, 15000);
          fetch("/api/authors/" + encodeURIComponent(secUid) + "/videos?source=remote&limit=20", { signal: controller.signal })
            .then(function (r) { clearTimeout(timeoutId); return r.json(); })
            .then(function (remoteData) {
              var remoteItems = remoteData.items || [];
              var localIds = {};
              localItems.forEach(function(v) { if (v.aweme_id) localIds[v.aweme_id] = true; });
              var merged = localItems.concat(remoteItems.filter(function(v) {
                return !localIds[v.aweme_id];
              }));
              renderProfileVideos({ items: merged, total: merged.length });
            })
            .catch(function () {
              clearTimeout(timeoutId);
              renderProfileVideos(localData);
            });
        } else {
          renderProfileVideos(localData);
        }
      })
      .catch(function () { document.getElementById("profileLoading").style.display = "none"; });
  }

  function renderProfileInfo(data, secUid) {
    document.getElementById("profileName").textContent = data.nickname || "";
    document.getElementById("profileIdHeader").textContent = data.unique_id ? "抖音号：" + data.unique_id : "";
    document.getElementById("profileFavorited").textContent = fmtNumWan(data.total_favorited || 0);
    document.getElementById("profileFollowing").textContent = fmtNumWan(data.following_count || 0);
    document.getElementById("profileFollowers").textContent = fmtNumWan(data.follower_count || 0);
    var bioEl = document.getElementById("profileBio");
    var bioMore = document.getElementById("bioMore");
    var sig = data.signature || "";
    bioEl.classList.remove("expanded");
    if (sig) {
      bioEl.innerHTML = sig.replace(/@([\w\u4e00-\u9fa5^_]+)/g, '<span class="at-link">@$1</span>');
      // 检测是否超过4行（bioMore 是 bioEl 的兄弟节点，不会被 innerHTML 销毁）
      setTimeout(function() {
        if (!bioMore) return;
        if (bioEl.scrollHeight > bioEl.clientHeight + 2) {
          bioMore.style.display = "block";
          bioMore.textContent = "更多";
        } else {
          bioMore.style.display = "none";
        }
      }, 50);
    } else {
      bioEl.textContent = "";
      if (bioMore) bioMore.style.display = "none";
    }
    document.getElementById("profileIp").textContent = data.ip_location ? "IP属地：" + data.ip_location : "";
    var av = document.getElementById("profileAvatar");
    var headerBg = document.getElementById("profileHeaderBg");
    // 主页头像三级兜底：接口头像 → 本博主 feed 头像 → 隐藏
    // 关键：按 secUid 匹配本博主视频取头像；禁用 videos[current]（滑动动画滞后时 current 是上一屏博主 → 头像串号）
    var curV = null;
    if (secUid) {
      for (var i = 0; i < videos.length; i++) {
        if (videos[i].sec_uid === secUid) { curV = videos[i]; break; }
      }
    }
    var fallbackAv = (curV && curV.avatar_url) || "";
    function setProfileAvatar(src) {
      if (src) { av.src = src; av.style.display = "block"; }
      else { av.style.display = "none"; }
    }
    av.onerror = function () {
      if (fallbackAv) {
        av.onerror = null;
        setProfileAvatar(fallbackAv);
        if (data.cover_url) {
          headerBg.style.backgroundImage = "url('" + data.cover_url + "')";
          headerBg.style.filter = "blur(0px)";
        } else if (fallbackAv) {
          headerBg.style.backgroundImage = "url('" + fallbackAv + "')";
          headerBg.style.filter = "blur(30px)";
          headerBg.style.transform = "scale(1.3)";
        }
      } else {
        av.onerror = null;
        av.style.display = "none";
      }
    };
    if (data.avatar_url) {
      setProfileAvatar(data.avatar_url);
    } else if (fallbackAv) {
      setProfileAvatar(fallbackAv);
    } else {
      av.style.display = "none";
    }
    // 优先用博主封面图，没有则用模糊头像
    if (data.cover_url) {
      headerBg.style.backgroundImage = "url('" + data.cover_url + "')";
      headerBg.style.filter = "blur(0px)";
      headerBg.style.transform = "scale(1)";
    } else if (data.avatar_url) {
      headerBg.style.backgroundImage = "url('" + data.avatar_url + "')";
      headerBg.style.filter = "blur(30px)";
      headerBg.style.transform = "scale(1.3)";
    }
    var fb = document.getElementById("profileFollow");
    if (data.is_following || followedCache[data.sec_uid]) {
      fb.textContent = "已关注"; fb.classList.add("followed");
    } else {
      fb.textContent = "+ 关注"; fb.classList.remove("followed");
    }
  }

  function renderProfileVideos(data) {
    document.getElementById("profileLoading").style.display = "none";
    var grid = document.getElementById("profileGrid");
    var items = data.items || [];
    document.getElementById("worksCount").textContent = data.total || items.length;
    if (items.length === 0) {
      document.getElementById("profileEmpty").style.display = "block";
      document.getElementById("profileEmpty").textContent = "暂无作品";
      return;
    }
    grid.innerHTML = "";
    items.forEach(function (v) {
      var div = document.createElement("div");
      div.className = "profile-grid-item";
      var isRemote = !v.id && v.cover;
      var likeCount = v.like_count || v.digg_count || 0;

      if (isRemote) {
        // 远程视频：用封面图
        var img = document.createElement("img");
        img.src = v.cover;
        img.style.cssText = "width:100%;height:100%;object-fit:cover;display:block";
        img.loading = "lazy";
        div.appendChild(img);
        // 未下载标记
        var badge = document.createElement("div");
        badge.style.cssText = "position:absolute;top:4px;right:4px;background:rgba(0,0,0,.6);color:#fff;font-size:10px;padding:2px 5px;border-radius:3px";
        badge.textContent = "未下载";
        div.appendChild(badge);
      } else {
        // 本地视频：用video首帧
        var thumb = document.createElement("video");
        thumb.src = v.url;
        thumb.muted = true;
        thumb.playsInline = true;
        thumb.preload = "auto";
        thumb.addEventListener("loadedmetadata", function() {
          try { thumb.currentTime = 0.5; } catch(e) {}
        });
        thumb.addEventListener("canplay", function() {
          thumb.play().then(function() { setTimeout(function(){ thumb.pause(); }, 100); }).catch(function(){});
        });
        div.appendChild(thumb);
      }

      var pc = document.createElement("div");
      pc.className = "play-count";
      pc.textContent = "❤ " + fmtNum(likeCount);
      div.appendChild(pc);

      div.addEventListener("click", function () {
        if (isRemote) {
          showToast("该视频未下载，点击下载后可播放");
          return;
        }
        closeProfile();
        var idx = videos.findIndex(function (vv) { return vv.id === v.id; });
        if (idx >= 0) { current = idx; layout(); }
      });
      grid.appendChild(div);
    });
  }

  // ===== 音乐页（musicPageEl 由 opts 注入） =====
  // 音乐页播放状态
  var musicPagePlaying = false;
  var musicPagePausedTime = 0; // 音乐界面暂停时的播放位置
  var musicPageVideoSavedTime = 0; // 进入音乐界面前视频的播放位置
  var musicPageIsNote = false;

  // 获取当前播放的音频元素（视频作品用video，图文作品用note-audio）
  function getCurrentAudioEl() {
    var curSlide = slideEls[1];
    if (!curSlide) return null;
    var isNote = curSlide.__note_images > 0;
    if (isNote) {
      var na = curSlide.querySelector(".note-audio");
      return (na && na.src) ? na : null;
    } else {
      var v = curSlide.querySelector("video");
      return (v && v.src) ? v : null;
    }
  }

  function openMusicPage(slide) {
    var v = videos[current];
    if (!v) return;
    // 大唱片封面（music_cover → 封面 → 头像 三级兜底，HEIC/解码失败双保险降级）
    var discImg = document.getElementById("musicDiscImg");
    var discList = [mediaSrc(v.music_cover), v.cover_url || "", v.avatar_url || ""];
    var mBg = document.querySelector("#musicPage .music-page-bg");
    // 背景与唱片同链预检（HEIC 失败自动换下一级）
    (function setBg() {
      var bi = 0;
      (function tryBg() {
        while (bi < discList.length) {
          var bs = discList[bi++];
          if (bs) {
            var probe = new Image();
            probe.onload = function () { mBg.style.backgroundImage = "url('" + bs + "')"; };
            probe.onerror = function () { tryBg(); };
            probe.src = bs;
            return;
          }
        }
        mBg.style.backgroundImage = "";
      })();
    })();
    setChainPic(discImg, discList, null);
    // 音乐标题
    document.getElementById("musicTitle").textContent = v.music_title || (v.author + "创作的原声");
    document.getElementById("musicSub").textContent = (v.music_author || v.author) + " | 本地收录";
    // 使用该音乐的视频：先留空
    document.getElementById("musicVideoGrid").innerHTML = "";
    document.getElementById("musicEmpty").style.display = "none";
    
    // 进入音乐页：暂停外面的视频和音乐，记录视频播放位置（用于退出时恢复）
    var curSlide = slideEls[1];
    musicPageIsNote = curSlide ? (curSlide.__note_images > 0) : false;
    var audioEl = getCurrentAudioEl();
    if (audioEl) {
      musicPageVideoSavedTime = audioEl.currentTime; // 记录视频原位置
      audioEl.pause(); // 暂停外面的视频/音乐
    }
    // 唱片默认暂停状态（停止旋转，显示暂停图标）
    musicPagePlaying = false;
    musicPagePausedTime = 0; // 第一次播放从头开始
    var disc = document.getElementById("musicDisc");
    disc.classList.add("playing");
    disc.classList.add("paused");
    document.getElementById("musicPauseIcon").classList.add("show");
    
    musicPageEl.classList.add("show");
  }

  function closeMusicPage() {
    musicPageEl.classList.remove("show");
    // 先暂停音乐界面的播放
    var audioEl = getCurrentAudioEl();
    if (audioEl) {
      audioEl.pause();
    }
    // 返回首页：视频从进入音乐界面前的原位置继续播放（不是从音乐界面断点继续）
    if (audioEl && soundOn) {
      try { audioEl.currentTime = musicPageVideoSavedTime; } catch(e) {}
      audioEl.muted = false;
      audioEl.play().catch(function () {});
    }
    // 唱片恢复正常
    var disc = document.getElementById("musicDisc");
    disc.classList.remove("paused");
    musicPagePlaying = false;
  }

  // 点击唱片：切换播放/暂停（音乐界面独立播放）
  // 触控范围：整个唱片容器（music-disc-wrap）都能点击
  document.querySelector(".music-disc-wrap").addEventListener("click", function(e) {
    e.stopPropagation();
    var audioEl = getCurrentAudioEl();
    if (!audioEl) return;
    
    var disc = document.getElementById("musicDisc");
    var pauseIcon = document.getElementById("musicPauseIcon");
    if (musicPagePlaying) {
      // 暂停：记录当前位置，停在当前位置
      musicPagePausedTime = audioEl.currentTime;
      audioEl.pause();
      musicPagePlaying = false;
      disc.classList.add("paused");
      pauseIcon.classList.add("show"); // 暂停时显示图标
    } else {
      // 播放：从暂停位置继续（第一次播放时musicPagePausedTime=0，即从头开始）
      try { audioEl.currentTime = musicPagePausedTime; } catch(e) {}
      audioEl.muted = false;
      audioEl.play().catch(function () {});
      musicPagePlaying = true;
      // 保险：确保唱片带 playing（打开时若 playing 丢失，点击播放时补上，否则不转）
      if (!disc.classList.contains("playing")) disc.classList.add("playing");
      disc.classList.remove("paused");
      pauseIcon.classList.remove("show"); // 播放时隐藏图标
    }
  });

  document.getElementById("musicBack").addEventListener("click", closeMusicPage);
  document.getElementById("musicShare").addEventListener("click", function () { doSharePassword(); });
  document.getElementById("musicCollect").addEventListener("click", function () {
    var v = videos[current];
    var on = !this.classList.contains("on");
    this.classList.toggle("on", on);
    this.querySelector(".icon").textContent = on ? "★" : "☆";
    if (on && v && window.reportBehavior) window.reportBehavior("collect", v.aweme_id || v.id, 0);
    showToast(on ? "已收藏" : "已取消收藏");
  });

  // 分享面板事件
  document.getElementById("shareCopyPassword").addEventListener("click", function () {
    var v = videos[current];
    if (!v) return;
    var ok = copyToClipboard(buildShareText(v));
    closeShareSheet();
    openDouyinApp(deepLink(v));
  });
  document.getElementById("shareCopyLink").addEventListener("click", function () {
    var v = videos[current];
    if (!v) return;
    var ok = copyToClipboard(contentLink(v));
    if (ok) showToast("链接已复制");
    closeShareSheet();
  });
  document.getElementById("shareMask").addEventListener("click", closeShareSheet);
  document.getElementById("shareCancel").addEventListener("click", closeShareSheet);

  // v9.1.2：跳转到散人同好——查该视频的来源同好节点（/api/videos/{vid}/peers），
  // 取权重最高的同好，用 snssdk1128 scheme 唤起抖音进其主页（与单击分享同一唤起通道）。
  // scheme 用 sec_uid query 形式；若无来源同好或缺 sec_uid 则提示。
  document.getElementById("shareGoPeer").addEventListener("click", function () {
    var v = videos[current];
    if (!v) { closeShareSheet(); return; }
    closeShareSheet();
    showToast("正在查询来源同好…");
    fetch("/api/videos/" + v.id + "/peers")
      .then(function (r) { return r.json(); })
      .then(function (data) {
        var items = data.items || [];
        var peer = null;
        for (var i = 0; i < items.length; i++) {
          if (items[i].sec_uid) { peer = items[i]; break; } // 服务端已按权重降序
        }
        if (!peer) { showToast(items.length ? "来源同好缺少主页信息" : "该视频暂无来源同好"); return; }
        showToast("跳转同好：" + (peer.nickname || "未知"));
        setTimeout(function () {
          openDouyinApp("snssdk1128://user/profile?sec_uid=" + encodeURIComponent(peer.sec_uid) + "&refer=web&needlaunchlog=1");
        }, 350);
      })
      .catch(function () { showToast("查询来源同好失败"); });
  });

  // 长按弹窗事件
  document.getElementById("longPressMask").addEventListener("click", function (e) {
    if (e.target === this) closeLongPressMenu();
  });
  document.getElementById("lpSwitch").addEventListener("click", function (e) {
    e.stopPropagation();
    // 占位项（功能待开发）：仅 UI 层面响应开关动画，无实际功能（2026-10-14 需求冻结）
    this.classList.toggle("on");
  });
  document.getElementById("lpDefaultCleanSwitch").addEventListener("click", function (e) {
    e.stopPropagation();
    // v9.1.12i：跳转仪式开关 —— 开=按所选方案动画(s2/s3)，关=无动画直切(s1)
    // 点击开关在"当前方案"与"无动画"之间切换：若当前非s1 → 切到s1(关)；若当前s1 → 恢复动画(上次动画方案或默认s3)
    var cur = localStorage.getItem("dy_jump_ritual") || "s3";
    var lastAnim = localStorage.getItem("dy_jump_ritual_last") || "s3";
    var next;
    if (cur === "s1") { next = (lastAnim === "s1") ? "s3" : lastAnim; }
    else { next = "s1"; }
    localStorage.setItem("dy_jump_ritual", next);
    if (next !== "s1") localStorage.setItem("dy_jump_ritual_last", next);
    this.classList.toggle("on", next !== "s1");
    showToast(next === "s1" ? "跳转仪式：已切换为无动画直切" : "跳转仪式：已启用" + (next === "s2" ? "方案二" : "方案三") + "动画");
  });
  // v9.1.3：删除 lpCleanSwitch 小球独立处理器——它和全局委托(capture先执行)双重 toggle 抵消，
  // 导致开关视觉不变+localStorage回原值+toast一直"已开启"。现在点小球冒泡到行→全局委托
  // 走完整持久化链路（setStorage + saveSettingToServer + window.setCleanMode）。

  // 下载视频
  document.getElementById("lpDownload").addEventListener("click", function () {
    var curSlide = slideEls[1];
    var vid = curSlide.__id;
    var v = videos.find(function(x) { return x.id === vid; });
    if (!v) { showToast("视频信息不存在"); return; }
    closeLongPressMenu();
    // v9.1.2：文件名 = 博主名-标题（清洗文件名非法字符，标题截断60字）
    // v9.1.3：文件名 = 博主名-标题。严格清洗：只保留中文/字母数字/空格/横杠，
    // 去掉 emoji/#/特殊符号/点（防原生下载把点后当扩展名导致后缀漏缺/下载失败）
    var _dlTitle = String(v.title || "")
      .replace(/[\r\n]+/g, " ")
      .replace(/[^\u4e00-\u9fa5a-zA-Z0-9\s\-]/g, "")
      .replace(/\s+/g, " ")
      .trim()
      .slice(0, 50);
    var _dlAuthor = String(v.author || "douyin")
      .replace(/[^\u4e00-\u9fa5a-zA-Z0-9\s]/g, "")
      .trim()
      .slice(0, 30) || "douyin";
    var _dlName = _dlAuthor + (_dlTitle ? "-" + _dlTitle : "") + ".mp4";
    // APK环境：调用Android下载接口保存到/storage/emulated/0/douyin/
    if (window.AndroidBridge && window.AndroidBridge.downloadVideo) {
      window.AndroidBridge.downloadVideo(v.url, _dlName);
      // v9.1.4：去掉黑底 toast（用户反馈屏幕上半部分黑底弹窗是Web端的，只要系统白底弹窗）
    } else {
      // 浏览器环境：用a标签下载
      var a = document.createElement("a");
      a.href = v.url;
      a.download = _dlName;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      showToast("开始下载视频");
    }
  });

  // 跟手滑动
  // 触摸是否落在非 feed 区域（不触发跟手滑动）：home 排除各覆盖页；my 只排除我页/音乐页
  // （myPlayer 内的触摸必须触发 mySlider，所以不排除 myPlayer）
  function touchBlocked(e) {
    if (!e.target.closest) return false;
    var t = e.target;
    if (t.closest(".progress-wrap")) return true;
    return !!(t.closest("#profile") || t.closest("#musicPage") || t.closest("#friendsPage") || t.closest("#messagesPage") || t.closest("#profilePage") || t.closest("#myPlayer"));
  }
  function touchMoveBlocked(e) {
    if (!e.target.closest) return false;
    var t = e.target;
    return !!(t.closest("#profilePage") || t.closest("#friendsPage") || t.closest("#messagesPage") || t.closest("#myPlayer"));
  }
  var startY = 0, startX = 0, startTime = 0, dragging = false, dy = 0;
  document.addEventListener("touchstart", function (e) {
    if (touchBlocked(e)) return;
    startY = e.touches[0].clientY;
    startX = e.touches[0].clientX;
    startTime = Date.now();
    dragging = true; dy = 0;
    slider.style.transition = "none";
    hideUnmutePrompt();
  }, { passive: true });

  document.addEventListener("touchmove", function (e) {
    if (!dragging) return;
    if (touchMoveBlocked(e)) return;
    dy = e.touches[0].clientY - startY;
    var dx = e.touches[0].clientX - startX;
    // 判断是否是图文的左右滑动（轴已锁定横向，或目标在note-images内，或水平移动大于垂直移动）
    var isNoteHScroll = window.__noteAxisH === true || (e.target.closest && e.target.closest(".note-images"));
    var isHScroll = Math.abs(dx) > Math.abs(dy) && Math.abs(dx) > 10;
    // 真正开始上下滑动时（超过10px），立即暂停当前slide的所有音频，避免重叠
    // 但图文左右滑动时不暂停音乐
    if (Math.abs(dy) > 10 && !window.__swipeAudioPaused && !isNoteHScroll && !isHScroll) {
      window.__swipeAudioPaused = true;
      var curV = slideEls[1].querySelector("video");
      var curNA = slideEls[1].querySelector(".note-audio");
      if (curV && !curV.paused) curV.pause();
      if (curNA && !curNA.paused) curNA.pause();
    }
    if ((current === 0 && dy > 0) || (current === videos.length - 1 && dy < 0)) dy = dy * 0.35;
    // 图集横向滑动中：不跟随上下位移（避免画面上下抖动），也不触发视频切换
    if (isNoteHScroll || isHScroll) return;
    slider.style.transform = "translateY(" + dy + "px)";
    if (Math.abs(dy) > 8) e.preventDefault();
  }, { passive: false });

  document.addEventListener("touchend", function () {
    if (!dragging) return;
    dragging = false;
    window.__swipeAudioPaused = false;
    var VH = window.innerHeight;
    var dt = Math.max(1, Date.now() - startTime);
    var velocity = Math.abs(dy) / dt;
    var shouldGo = Math.abs(dy) > THRESHOLD || (velocity > FLING_SPEED && Math.abs(dy) > FLING_MIN_DIST);
    var isNoteSwipe = window.__noteAxisH === true;
    if (!isNoteSwipe && animating) return;
    if (!isNoteSwipe && dy < 0 && shouldGo && current < videos.length - 1) {
      lockSwitch();
      // 立即暂停当前slide的所有音频
      var curV0 = slideEls[1].querySelector("video");
      var curNA0 = slideEls[1].querySelector(".note-audio");
      if (curV0) curV0.pause();
      if (curNA0) curNA0.pause();
      var tv = slideEls[2].querySelector("video");
      var tvPi = slideEls[2].querySelector(".pause-icon");
      if (tvPi) tvPi.classList.remove("show");
      var pos = videoPositions[slideEls[2].__id];
      if (pos && pos > 0.5 && tv.currentTime < 0.1 && tv.duration) tv.currentTime = Math.min(pos, tv.duration - 0.5);
      tv.muted = !soundOn; tv.play().catch(function () {});
      var tvNA = slideEls[2].querySelector(".note-audio");
      if (tvNA && tvNA.src) { tvNA.muted = !soundOn; tvNA.play().catch(function () {}); }
      window.__visualIdx = current + 1; // touch 动画中：视觉内容已滑向下一条（串号根治：点击身份不再滞后）
      animateTo(-VH, function () { current++; resetAndLayout(1); });
    } else if (!isNoteSwipe && dy > 0 && shouldGo && current > 0) {
      lockSwitch();
      window.__visualIdx = current - 1; // touch 动画中：视觉内容已滑向上一条
      var curV1 = slideEls[1].querySelector("video");
      var curNA1 = slideEls[1].querySelector(".note-audio");
      if (curV1) curV1.pause();
      if (curNA1) curNA1.pause();
      var tv = slideEls[0].querySelector("video");
      var tvPi0 = slideEls[0].querySelector(".pause-icon");
      if (tvPi0) tvPi0.classList.remove("show");
      var pos = videoPositions[slideEls[0].__id];
      if (pos && pos > 0.5 && tv.currentTime < 0.1 && tv.duration) tv.currentTime = Math.min(pos, tv.duration - 0.5);
      tv.muted = !soundOn; tv.play().catch(function () {});
      var tvNA2 = slideEls[0].querySelector(".note-audio");
      if (tvNA2 && tvNA2.src) { tvNA2.muted = !soundOn; tvNA2.play().catch(function () {}); }
      animateTo(VH, function () { current--; resetAndLayout(-1); });
    } else {
      // 没有切换：不自动恢复播放，让click事件处理单击暂停/继续
      animateTo(0, null);
    }
  });

  function animateTo(targetPx, cb, dur, curve) {
    var d = dur || 0.35;
    slider.style.transition = "transform " + d + "s " + (curve || EASE);
    slider.style.transform = "translateY(" + targetPx + "px)";
    var done = false;
    function handler() { if (done) return; done = true; slider.removeEventListener("transitionend", handler); if (cb) cb(); }
    slider.addEventListener("transitionend", handler);
    // 兜底超时 = 动画时长 + 110ms 余量（0.35s→460ms；0.7s→810ms），
    // 避免长动画未跑完就被 resetAndLayout 打断（transition 被置 none 截断动画）
    setTimeout(handler, Math.round(d * 1000) + 110);
  }

  function resetAndLayout(direction) {
    justSwiped = true;
    setTimeout(function () { justSwiped = false; }, 200);
    slider.style.transition = "none";
    slider.style.transform = "translateY(0)";
    if (direction === 1) slider.appendChild(slideEls[0]);
    else if (direction === -1) slider.insertBefore(slideEls[2], slideEls[0]);
    slideEls = Array.from(slider.children);
    layout();
  }

  // 全局：跳到下一个视频（供外部注入代码/新菜单复用，逻辑与 ended/滚轮一致）
  window.goNextSlide = function () {
    if (current >= videos.length - 1) { showToast("已是最后一个"); return false; }
    lockSwitch();
    // v9.1.12d：跳转前立即暂停当前slide的所有音频（与触摸滑动路径一致），
    // 消除"下一个已开始播、上一个没立马停"的 450ms 声音重叠窗口（原依赖 layout() 动画后才暂停）。
    var curV0 = slideEls[1].querySelector("video");
    var curNA0 = slideEls[1].querySelector(".note-audio");
    var curAE0 = slideEls[1].querySelector(".audio-el");
    if (curV0) curV0.pause();
    if (curNA0) curNA0.pause();
    if (curAE0) curAE0.pause();
    var tv = slideEls[2].querySelector("video");
    var tvPi = slideEls[2].querySelector(".pause-icon");
    if (tvPi) tvPi.classList.remove("show");
    var pos = videoPositions[slideEls[2].__id];
    if (pos && pos > 0.5 && tv.currentTime < 0.1 && tv.duration) tv.currentTime = Math.min(pos, tv.duration - 0.5);
    // v9.1.12b：play 提前到滑动动画开始前（与触摸滑动路径一致），
    // Surface 在滑动期间即建立 → 消除"菜单确认跳转前几帧黑屏"（对比触摸滑动不黑的根因差异）。
    tv.muted = !soundOn; tv.play().catch(function () {});
    var tvNA = slideEls[2].querySelector(".note-audio");
    if (tvNA && tvNA.src) { tvNA.muted = !soundOn; tvNA.play().catch(function () {}); }
    // v9.1.12i：跳转仪式 —— 按 dy_jump_ritual 方案分流
    // s1 = 无动画直切；s2 = 0.7s cubic-bezier(0.2,0.9,0.4,1)；s3 = 0.7s cubic-bezier(0.5,0.06,0.13,1)
    // v9.1.12p：各自专用自定义模式 —— 按反馈类型(kind)映射方案：
    //   not_interested/puzzle → s1；secret_like → s2；super_like → s3
    var ritual = "s3";
    try { ritual = localStorage.getItem("dy_jump_ritual") || "s3"; } catch (e) {}
    var customOn = false;
    try { customOn = localStorage.getItem("dy_jump_ritual_custom") === "on"; } catch (e) {}
    if (customOn && window.__lastFeedbackKind) {
      var k = window.__lastFeedbackKind;
      if (k === "not_interested" || k === "puzzle") ritual = "s1";
      else if (k === "secret_like") ritual = "s2";
      else if (k === "super_like") ritual = "s3";
    }
    window.__visualIdx = current + 1;
    if (ritual === "s1") {
      slider.style.transition = "none";
      slider.style.transform = "translateY(-100%)";
      current++; resetAndLayout(1);
    } else if (ritual === "s2") {
      animateTo(-window.innerHeight, function () { current++; resetAndLayout(1); }, 0.7, "cubic-bezier(0.2, 0.9, 0.4, 1)");
    } else {
      animateTo(-window.innerHeight, function () { current++; resetAndLayout(1); }, 0.7, "cubic-bezier(0.5, 0.06, 0.13, 1)");
    }
    return true;
  };
  // 全局：设置当前会话连播状态（供"启动时默认自动连播"开关使用）
  window.setAutoPlayNext = function (on) {
    autoPlayNext = !!on;
    // v9.1：不再同步占位1(lpSwitch) 开关样式，各开关独立（修"联动"bug）
  };
  // v9.1.1：暴露声音/清屏运行时接口（修服务器回灌在全局作用域赋值变隐式全局变量、
  // 主IIFE运行时状态永不更新的致命bug）
  window.setSoundOn = function (on) {
    soundOn = !!on;
    try {
      var slides = document.querySelectorAll(".slide");
      if (slides[1]) { var tv = slides[1].querySelector("video"); if (tv) tv.muted = !soundOn; }
      // v9.1.4：music 按钮默认带 off prompt 类（HTML模板），soundOn=true 时必须主动移除 prompt，
      // 否则"取消静音"胶囊永不消失（用户实测：进APP前几秒/首个视频循环时胶囊一直在）
      if (soundOn) { hideUnmutePrompt(); }
      else { showUnmutePrompt(); }
    } catch(e) {}
  };
  window.setCleanMode = setCleanMode;

  var wheelLock = false;
  document.addEventListener("wheel", function (e) {
    if (wheelLock || animating) return; wheelLock = true;
    if (e.deltaY > 0 && current < videos.length - 1) {
      lockSwitch();
      // v9.1.12d：滚轮跳转同样先暂停当前音频，避免新旧重叠
      var cV0 = slideEls[1].querySelector("video");
      var cNA0 = slideEls[1].querySelector(".note-audio");
      var cAE0 = slideEls[1].querySelector(".audio-el");
      if (cV0) cV0.pause();
      if (cNA0) cNA0.pause();
      if (cAE0) cAE0.pause();
      var tv = slideEls[2].querySelector("video");
      var pos = videoPositions[slideEls[2].__id];
      if (pos && pos > 0.5 && tv.currentTime < 0.1 && tv.duration) tv.currentTime = Math.min(pos, tv.duration - 0.5);
      tv.muted = !soundOn; tv.play().catch(function () {});
      current++; resetAndLayout(1);
    } else if (e.deltaY < 0 && current > 0) {
      lockSwitch();
      // v9.1.12d：滚轮上滑同样先暂停当前音频
      var cV1 = slideEls[1].querySelector("video");
      var cNA1 = slideEls[1].querySelector(".note-audio");
      var cAE1 = slideEls[1].querySelector(".audio-el");
      if (cV1) cV1.pause();
      if (cNA1) cNA1.pause();
      if (cAE1) cAE1.pause();
      var tv = slideEls[0].querySelector("video");
      var pos = videoPositions[slideEls[0].__id];
      if (pos && pos > 0.5 && tv.currentTime < 0.1 && tv.duration) tv.currentTime = Math.min(pos, tv.duration - 0.5);
      tv.muted = !soundOn; tv.play().catch(function () {});
      current--; resetAndLayout(-1);
    } else { wheelLock = false; return; }
    setTimeout(function () { wheelLock = false; }, 400);
  }, { passive: true });

  // 全局边缘滑动：左边缘右滑=返回上一层，右边缘左滑=进入博主主页
  var edgeSwipe = { active: false, side: "", startX: 0, startY: 0 };
  document.addEventListener("touchstart", function (e) {
    var t = e.touches[0];
    var w = window.innerWidth;
    // 单页引擎：非播放页面（我页九宫格/朋友/消息）不触发边缘手势
    if (e.target.closest && (e.target.closest("#profilePage") || e.target.closest("#friendsPage") || e.target.closest("#messagesPage") || e.target.closest("#myPlayer"))) {
      edgeSwipe.active = false; return;
    }
    // 边缘触发（首页和非首页都只在边缘25px触发）
    if (t.clientX < 25) {
      edgeSwipe.active = true; edgeSwipe.side = "left";
      edgeSwipe.startX = t.clientX; edgeSwipe.startY = t.clientY;
    } else if (t.clientX > w - 25) {
      edgeSwipe.active = true; edgeSwipe.side = "right";
      edgeSwipe.startX = t.clientX; edgeSwipe.startY = t.clientY;
    } else {
      edgeSwipe.active = false;
    }
  }, { passive: true });

  // 全局：任何touchmove都清除所有slide的长按定时器（防止滑动时触发长按弹窗）
  document.addEventListener("touchmove", function (e) {
    var allSlides = document.querySelectorAll(".slide");
    for (var i = 0; i < allSlides.length; i++) {
      var s = allSlides[i];
      if (s.__lpTimer) { clearTimeout(s.__lpTimer); s.__lpTimer = null; }
      if (s.__musicLpTimer) { clearTimeout(s.__musicLpTimer); s.__musicLpTimer = null; }
    }
  }, { passive: true });
  document.addEventListener("touchmove", function (e) {
    if (!edgeSwipe.active) return;
    var t = e.touches[0];
    var dx = t.clientX - edgeSwipe.startX;
    var dy = t.clientY - edgeSwipe.startY;
    if (Math.abs(dx) > Math.abs(dy) && Math.abs(dx) > 10) {
      e.preventDefault();
    }
  }, { passive: false });
  document.addEventListener("touchend", function (e) {
    if (!edgeSwipe.active) return;
    var t = e.changedTouches[0];
    var dx = t.clientX - edgeSwipe.startX;
    var side = edgeSwipe.side;
    edgeSwipe.active = false;
    // 我页播放：边缘横滑退出已废止（WebView 被系统手势抢占），退出靠点头像/名称
    if (playMode === "my") { return; }
    // 非首页时：边缘左右滑动切换相邻导航栏页面
    if (currentPage !== "home" && !profileEl.classList.contains("show") && !musicPageEl.classList.contains("show")) {
      if (Math.abs(dx) > 60 && Math.abs(dx) > Math.abs(dy)) {
        if (dx > 0) switchToAdjacentPage(-1); // 右滑→上一个页面
        else switchToAdjacentPage(1); // 左滑→下一个页面
      }
      return;
    }
    if (side === "left" && dx > 60) {
      // 左边缘右滑：返回上一层
      if (profileEl.classList.contains("show")) { closeProfile(); }
      else if (friendsPageEl.classList.contains("show")) { closeFriendsPage(); }
      else if (messagesPageEl.classList.contains("show")) { switchPage("home"); }
      else if (profilePageEl.classList.contains("show")) { switchPage("home"); }
      else if (musicPageEl.classList.contains("show")) { closeMusicPage(); }
    } else if (side === "right" && dx < -60) {
      // 右边缘左滑：进入当前视频博主主页（仅首页）
      if (currentPage === "home" && !profileEl.classList.contains("show") && !musicPageEl.classList.contains("show")) {
        var cur = slideEls[1];
        if (cur && (cur.__sec_uid || window.__currentSecUid)) {
          openProfile(cur.__sec_uid || window.__currentSecUid);
        } else {
          showToast("暂无博主信息");
        }
      }
    }
  });

  // ===== 历史记录管理：利用WebView历史记录实现右边缘左滑进入博主主页 =====
  // 首页加载后构造历史记录：[占位页] → [首页]
  // 系统返回goBack到占位页时触发popstate，自动进入博主主页
  var profileHistoryReady = false;

  function setupHomeHistory() {
    if (profileHistoryReady) return;
    try {
      // 把当前状态替换为占位页
      history.replaceState({page: "profile_placeholder"}, "", "");
      // 压入首页状态
      history.pushState({page: "home"}, "", "");
      profileHistoryReady = true;
    } catch(e) {}
  }

  // 进入博主主页时调整历史记录：[占位页] → [博主主页] → [首页]
  function setupProfileHistory() {
    try {
      // 替换占位页为博主主页状态
      history.replaceState({page: "profile"}, "", "");
      // 压入首页状态（这样在博主主页返回时goBack到profile状态，触发关闭）
      history.pushState({page: "home"}, "", "");
    } catch(e) {}
  }

  // 关闭博主主页时恢复历史记录：[占位页] → [首页]
  function restoreHomeHistory() {
    try {
      // 替换当前状态为占位页
      history.replaceState({page: "profile_placeholder"}, "", "");
      // 压入首页状态
      history.pushState({page: "home"}, "", "");
    } catch(e) {}
  }

  // 监听popstate事件（setupHomeHistory已延迟2000ms，无需额外保护）
  window.addEventListener("popstate", function(e) {
    if (!e.state) return;
    if (e.state.page === "profile_placeholder") {
      // goBack到占位页：进入当前视频博主主页
      if (currentPage === "home" && !profileEl.classList.contains("show") && !musicPageEl.classList.contains("show")) {
        var cur = slideEls[1];
        if (cur && cur.__sec_uid) {
          // 先调整历史记录，再打开博主主页
          setupProfileHistory();
          openProfile(cur.__sec_uid);
        } else {
          // 没有博主信息，恢复历史记录
          restoreHomeHistory();
        }
      } else {
        // 非首页或有overlay，恢复历史记录
        restoreHomeHistory();
      }
    } else if (e.state.page === "profile") {
      // goBack到博主主页状态：关闭博主主页，回到首页
      if (profileEl.classList.contains("show")) {
        closeProfile();
      }
      // 恢复首页历史记录结构
      restoreHomeHistory();
    }
  });

  // APK返回键接口：关闭overlay，返回true表示已处理
  window.androidBack = function() {
    if (profileEl.classList.contains("show")) { closeProfile(); return true; }
    if (friendsPageEl.classList.contains("show")) { closeFriendsPage(); return true; }
    if (messagesPageEl.classList.contains("show")) { switchPage("home"); return true; }
    if (profilePageEl.classList.contains("show")) { switchPage("home"); return true; }
    if (musicPageEl.classList.contains("show")) { closeMusicPage(); return true; }
    return false;
  };

  // APK边缘滑动接口：APK拦截边缘触摸后调用此函数处理滑动逻辑
  // side: "left"=左边缘, "right"=右边缘; dx: 滑动距离(正=右滑, 负=左滑)
  window.handleEdgeSwipe = function(side, dx) {
    // 非首页时：边缘左右滑动切换相邻导航栏页面
    if (currentPage !== "home" && !profileEl.classList.contains("show") && !musicPageEl.classList.contains("show")) {
      if (Math.abs(dx) > 60) {
        if (dx > 0) switchToAdjacentPage(-1);
        else switchToAdjacentPage(1);
      }
      return;
    }
    if (side === "left" && dx > 60) {
      if (profileEl.classList.contains("show")) { closeProfile(); }
      else if (friendsPageEl.classList.contains("show")) { closeFriendsPage(); }
      else if (messagesPageEl.classList.contains("show")) { switchPage("home"); }
      else if (profilePageEl.classList.contains("show")) { switchPage("home"); }
      else if (musicPageEl.classList.contains("show")) { closeMusicPage(); }
    } else if (side === "right" && dx < -60) {
      if (currentPage === "home" && !profileEl.classList.contains("show") && !musicPageEl.classList.contains("show")) {
        var cur = slideEls[1];
        if (cur && (cur.__sec_uid || window.__currentSecUid)) {
          openProfile(cur.__sec_uid || window.__currentSecUid);
        } else {
          showToast("暂无博主信息");
        }
      }
    }
  };

  // APK调用：右边缘左滑处理（系统返回手势触发时调用）
  // 首页→进入当前视频博主主页；非首页→切换到下一个页面
  window.handleRightEdgeSwipe = function() {
    // 如果有overlay（博主主页/音乐页），先关闭
    if (profileEl.classList.contains("show")) { closeProfile(); return true; }
    if (musicPageEl.classList.contains("show")) { closeMusicPage(); return true; }
    // 非首页：切换到下一个页面
    if (currentPage !== "home") {
      var pageOrder = ["home", "friends", "messages", "profile"];
      var idx = pageOrder.indexOf(currentPage);
      if (idx < pageOrder.length - 1) {
        switchPage(pageOrder[idx + 1]);
        return true;
      }
      return false; // 已经在最右端，让系统退出
    }
    // 首页：进入当前视频博主主页
    var cur = slideEls[1];
    if (cur && (cur.__sec_uid || window.__currentSecUid)) {
      openProfile(cur.__sec_uid || window.__currentSecUid);
      return true;
    }
    showToast("暂无博主信息");
    return true;
  };

  // APK调用：左边缘右滑处理（系统返回手势触发时调用）
  // 非首页→切换到上一个页面；首页→返回false让系统退出
  window.handleLeftEdgeSwipe = function() {
    // 如果有overlay（博主主页/音乐页），先关闭
    if (profileEl.classList.contains("show")) { closeProfile(); return true; }
    if (musicPageEl.classList.contains("show")) { closeMusicPage(); return true; }
    // 非首页：切换到上一个页面
    if (currentPage !== "home") {
      var pageOrder = ["home", "friends", "messages", "profile"];
      var idx = pageOrder.indexOf(currentPage);
      if (idx > 0) {
        switchPage(pageOrder[idx - 1]);
        return true;
      }
      return false; // 已经在首页，让系统退出
    }
    // 首页：左边缘右滑无操作，让系统退出
    return false;
  };

  // APK调用：统一的返回键处理（完全在JS端处理，不依赖WebView历史记录）
  // 参数：touchX=最后触摸X坐标(px), screenWidth=屏幕宽度(px), edgeWidth=边缘宽度(px)
  // 返回值："handled"=已处理, "exit"=退出APK
  window.handleBackPressWithHistory = function(touchX, screenWidth, edgeWidth) {
    // 1. 有overlay先关闭
    if (profileEl.classList.contains("show")) { closeProfile(); return "handled"; }
    if (musicPageEl.classList.contains("show")) { closeMusicPage(); return "handled"; }
    if (friendsPageEl.classList.contains("show")) { closeFriendsPage(); return "handled"; }
    
    // 2. 非首页：边缘滑动切换相邻页面，否则回首页
    if (currentPage !== "home") {
      var isLeftEdge = (touchX >= 0 && touchX < edgeWidth);
      var isRightEdge = (touchX >= 0 && touchX > screenWidth - edgeWidth);
      var pageOrder = ["home", "friends", "messages", "profile"];
      var idx = pageOrder.indexOf(currentPage);
      if (isRightEdge && idx < pageOrder.length - 1) { switchPage(pageOrder[idx + 1]); return "handled"; }
      if (isLeftEdge && idx > 0) { switchPage(pageOrder[idx - 1]); return "handled"; }
      switchPage("home");
      return "handled";
    }
    
    // 3. 首页：判断是右边缘左滑还是左边缘/返回键
    var isRightEdge = (touchX >= 0 && touchX > screenWidth - edgeWidth);
    if (isRightEdge) {
      // 右边缘左滑：进入当前视频博主主页
      var cur = slideEls[1];
      if (cur && (cur.__sec_uid || window.__currentSecUid)) {
        openProfile(cur.__sec_uid || window.__currentSecUid);
        return "handled";
      }
      showToast("暂无博主信息");
      return "handled";
    }
    // 左边缘右滑或按返回键：退出APK
    return "exit";
  };

  // APK调用：取消长按和上下滑动（边缘水平滑动时调用）
  window.cancelLongPress = function() {
    // 隐藏长按弹窗
    var mask = document.getElementById("longPressMask");
    if (mask) mask.style.display = "none";
    // 直接清除所有slide的长按定时器
    var allSlides = document.querySelectorAll(".slide");
    for (var i = 0; i < allSlides.length; i++) {
      var s = allSlides[i];
      if (s.__lpTimer) { clearTimeout(s.__lpTimer); s.__lpTimer = null; }
      if (s.__musicLpTimer) { clearTimeout(s.__musicLpTimer); s.__musicLpTimer = null; }
    }
    // 重置上下滑动状态
    dragging = false;
  };

  // 从服务器同步设置（跨设备一致）：/api/settings 回灌 localStorage + 运行时
  function loadSettingsFromServer() {
    try {
      fetch("/api/settings")
        .then(function (r) { return r.json(); })
        .then(function (data) {
          if (!data || typeof data !== "object") return;
          var keys = ["dy_default_mute", "dy_default_autoplay", "dy_default_clean", "dy_jump_ritual", "dy_jump_ritual_custom"];
          var changed = false;
          for (var i = 0; i < keys.length; i++) {
            if (data[keys[i]] !== undefined) {
              try { localStorage.setItem(keys[i], data[keys[i]]); } catch (e) {}
              changed = true;
            }
          }
          if (changed) {
            var dm = document.getElementById("lpDefaultMuteSwitch");
            var da = document.getElementById("lpDefaultAutoPlaySwitch");
            var dc = document.getElementById("lpCleanSwitch");
            if (dm) { if (localStorage.getItem("dy_default_mute") !== "1") dm.classList.add("on"); else dm.classList.remove("on"); }
            if (da) { if (localStorage.getItem("dy_default_autoplay") === "1") da.classList.add("on"); else da.classList.remove("on"); }
            if (dc) { if (localStorage.getItem("dy_default_clean") === "1") dc.classList.add("on"); else dc.classList.remove("on"); }
            var rsw = document.getElementById("lpDefaultCleanSwitch");
            if (rsw) { var _rv = localStorage.getItem("dy_jump_ritual"); rsw.classList.toggle("on", _rv !== null && _rv !== "s1"); }
            try {
              if (window.setAutoPlayNext) window.setAutoPlayNext(localStorage.getItem("dy_default_autoplay") === "1");
              if (window.setSoundOn) window.setSoundOn(localStorage.getItem("dy_default_mute") !== "1");
              if (window.setCleanMode) window.setCleanMode(localStorage.getItem("dy_default_clean") === "1");
            } catch (e2) {}
          }
        })
        .catch(function () {});
    } catch (e) {}
  }

  // 应用默认设置（直接读 localStorage，不依赖 loadDefaults）
  function applyDefaultSettings() {
    var _apDef = null;
    try { _apDef = localStorage.getItem("dy_default_autoplay"); } catch (e) {}
    if (window.setAutoPlayNext) window.setAutoPlayNext(_apDef === null ? true : _apDef === "1");
    // 开启时默认不静音：dy_default_mute !== "1" → soundOn=true
    try { if (localStorage.getItem("dy_default_mute") !== "1") { if (window.setSoundOn) window.setSoundOn(true); } } catch (e) {}
    var _cmDef = null;
    try { _cmDef = localStorage.getItem("dy_default_clean"); } catch (e) {}
    setCleanMode(_cmDef === "1");
  }

  // 启动（首页）：加载数据 → 布局 → 播放 → 淡出开屏
  function bootHome() {
    applyDefaultSettings();
    loadSettingsFromServer();
    return fetchPage().then(function () {
      if (loading) loading.style.display = "none";
      setTimeout(function () { try { setupHomeHistory(); } catch (e) {} }, 2000);
      try { layout(); } catch (e) { console.error("layout error", e); }
      try {
        if (localStorage.getItem("dy_default_mute") !== "1") { if (window.setSoundOn) window.setSoundOn(true); }
        else { if (window.setSoundOn) window.setSoundOn(false); }
      } catch (e) {}
      setTimeout(showUnmutePrompt, 600);
      var splash = document.getElementById("splash");
      var curVideo = slideEls[1].querySelector("video");
      var hideSplash = function () {
        if (splash && !splash.classList.contains("hide")) {
          document.body.classList.add("video-ready");
          splash.classList.add("hide");
          setTimeout(function () { if (splash && splash.parentNode) splash.parentNode.removeChild(splash); }, 250);
        }
      };
      if (curVideo) {
        if (curVideo.readyState >= 2 && !curVideo.paused) {
          hideSplash();
        } else {
          curVideo.addEventListener("playing", hideSplash, { once: true });
          curVideo.addEventListener("canplay", hideSplash, { once: true });
          // 兜底：3秒后强制淡出
          setTimeout(hideSplash, 3000);
        }
      } else {
        setTimeout(hideSplash, 500);
      }
    }).catch(function () {
      if (loading) loading.textContent = "加载失败，请检查服务是否启动";
    });
  }

  // ===== my 播放器：打开 / 关闭 =====
  // ===== 单页引擎：home / my 两套播放上下文，切换数据源不重新拉已缓存数据 =====
  var homeCtx = { ds: opts.dataSource, videos: [], offset: 0, hasMore: true, current: 0, loaded: false };
  var myCtx = { ds: myDataSource, videos: [], offset: 0, hasMore: true, current: 0, loaded: false };
  function snapshotCtx(c) { c.videos = videos; c.offset = offset; c.hasMore = hasMore; c.current = current; }
  function restoreCtx(c) { dataSource = c.ds; videos = c.videos; offset = c.offset; hasMore = c.hasMore; current = c.current; }
  function myPlayerBarEl() { return document.getElementById("myPlayerBar"); }

  var myBooted = false;
  var myPreloading = null;
  // 预热 my 数据（不显示播放器、不切全局、不污染首页）：九宫格渲染完就调用。
  // 目的：让首次点封面时 myCtx.loaded 已为 true，openMyPlayer 走同步路径，
  // play() 落在用户真实点击手势内。否则首次进入要 await fetchPage，非静音 autoplay
  // 在异步回调里脱离手势被 WebView 拦截（NotAllowedError）→ 视频加载好却停在封面。
  function preloadMy() {
    if (myCtx.loaded) return Promise.resolve();
    if (myPreloading) return myPreloading;
    myPreloading = myDataSource.fetch(0, PAGE).then(function (res) {
      var items = res.items || [];
      myCtx.videos = items;
      myCtx.offset = (res.nextOffset != null) ? res.nextOffset : items.length;
      myCtx.hasMore = !!res.hasMore;
      myCtx.current = 0;
      myCtx.loaded = true;
      myPreloading = null;
    }).catch(function (e) {
      myPreloading = null;
      console.error("preloadMy error", e);
    });
    return myPreloading;
  }
  function openMyPlayer(idx) {
    myPlayerOpen = true;
    // 首次从我页九宫格进入（当前还是 home 数据），先快照 home
    if (playMode === "home" && !myCtx.loaded) { snapshotCtx(homeCtx); }
    var go = function () {
      restoreCtx(myCtx);
      current = idx;
      if (profilePageEl) { profilePageEl.classList.remove("show"); profilePageEl.style.display = "none"; }
      var tb = document.querySelector(".tabbar");
      if (tb) tb.style.display = "none";
      var mb = myPlayerBarEl();
      if (mb) mb.style.display = "flex";
      rootEl.style.display = "block";
      playMode = "my";
      try { layout(); } catch (e) { console.error("layout error", e); }
      playCurrent();
      onOpen();
    };
    // 数据已预热（九宫格渲染时 preloadMy）：整条路径在真实点击手势内同步执行，
    // 非静音 play() 合法，一点封面直接开播。
    if (myCtx.loaded) {
      if (!myBooted) { try { applyDefaultSettings(); loadSettingsFromServer(); } catch (e) {} myBooted = true; }
      go();
    }
    else {
      // 兜底：极端情况下预热未完成（首次进入），仍异步加载后再进
      applyDefaultSettings();
      loadSettingsFromServer();
      preloadMy().then(function () {
        myBooted = true;
        if (loading) loading.style.display = "none";
        go();
      }).catch(function () {
        if (loading) loading.textContent = "加载失败，请检查服务是否启动";
        myPlayerOpen = false;
      });
    }
  }

  function closeMyPlayer() {
    snapshotCtx(myCtx);
    pauseAllMedia();
    if (musicPageEl) musicPageEl.classList.remove("show");
    rootEl.style.display = "none";
    var mb = myPlayerBarEl();
    if (mb) mb.style.display = "none";
    var tb = document.querySelector(".tabbar");
    if (tb) tb.style.display = "";
    if (profilePageEl) {
      profilePageEl.style.display = "";
      profilePageEl.classList.add("show");
    }
    // 数据源仍为 my（停在我页），下次点封面直接复用
    playMode = "my";
    myPlayerOpen = false;
    onClose();
  }

  // 切回首页：若刚从 my 播放/我页回来，恢复 home 上下文；否则只做视图切换
  function enterHomePlayer() {
    if (playMode === "my") { snapshotCtx(myCtx); restoreCtx(homeCtx); }
    pauseAllMedia();
    if (profilePageEl) { profilePageEl.classList.remove("show"); profilePageEl.style.display = ""; }
    var mb = myPlayerBarEl();
    if (mb) mb.style.display = "none";
    rootEl.style.display = "block";
    playMode = "home";
    var tb = document.querySelector(".tabbar");
    if (tb) tb.style.display = "";
    try { layout(); } catch (e) { console.error("layout error", e); }
    playCurrent();
  }

  // 启动：首页自动启动；my 等点封面时 open
  if (variant === "home" && autoStart) {
    bootHome();
  }

  return {
    boot: bootHome,
    open: openMyPlayer,
    close: closeMyPlayer,
    preloadMy: preloadMy,
    goNext: function () { return window.goNextSlide(); },
    goPrev: function () {
      try { if (current > 0) { current--; layout(); } } catch (e) {}
    },
    setSoundOn: function (b) { if (window.setSoundOn) window.setSoundOn(b); },
    setAutoPlayNext: function (b) { if (window.setAutoPlayNext) window.setAutoPlayNext(b); },
    isOpen: function () { return myPlayerOpen; },
    getCurrentVid: function () { return (typeof window.__currentVid === "function") ? window.__currentVid() : null; }
  };
};
