/* menu-setup.js —— 长按菜单/设置的全局交互（首页 home 与 我页 my 共用）
 * 包含：设置服务器同步、菜单整栏 click 委托、跳转仪式方案弹窗、取消静音胶囊 FLIP 动画。
 * 菜单 DOM 两个页面相同，所以这里只写一份，全局生效。 */
(function () {
  "use strict";

  // ===== 设置服务器同步（单个设置，异步不阻塞）=====
  function saveSettingToServer(key, value) {
    try {
      var body = {};
      body[key] = value;
      fetch("/api/settings", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body)
      }).catch(function () {});
    } catch (e) {}
  }
  window.saveSettingToServer = saveSettingToServer;

  // ===== 毛玻璃弹窗整栏点击（全局 capture 委托）=====
  function lpSetSwitch(switchId, on) {
    var sw = document.getElementById(switchId);
    if (sw) { if (on) sw.classList.add("on"); else sw.classList.remove("on"); }
  }
  function lpGetStorage(key) { return localStorage.getItem(key) === "1"; }
  function lpSetStorage(key, val) { try { localStorage.setItem(key, val ? "1" : "0"); } catch (e) {} }
  function lpToast(msg) {
    var t = document.getElementById("toast");
    if (t) { t.textContent = msg; t.style.opacity = "1"; setTimeout(function () { t.style.opacity = "0"; }, 1500); }
  }

  document.addEventListener("click", function (e) {
    var item = e.target.closest ? e.target.closest(".lp-item") : null;
    if (!item) return;
    var mask = item.closest("#longPressMask");
    if (!mask) return;

    if (item.id === "lpDefaultMute") {
      // dy_default_mute=1 表示默认静音；开关 on = 不静音
      var newOn = localStorage.getItem("dy_default_mute") === "1";
      lpSetStorage("dy_default_mute", !newOn);
      lpSetSwitch("lpDefaultMuteSwitch", newOn);
      saveSettingToServer("dy_default_mute", newOn ? "0" : "1");
      if (window.setSoundOn) window.setSoundOn(newOn);
      lpToast(newOn ? "开启时默认不静音已开启" : "开启时默认不静音已关闭");
      return;
    }
    if (item.id === "lpDefaultAutoPlay") {
      var v2 = !lpGetStorage("dy_default_autoplay");
      lpSetStorage("dy_default_autoplay", v2);
      lpSetSwitch("lpDefaultAutoPlaySwitch", v2);
      saveSettingToServer("dy_default_autoplay", v2 ? "1" : "0");
      if (window.setAutoPlayNext) window.setAutoPlayNext(v2);
      lpToast(v2 ? "启动时默认自动连播已开启" : "启动时默认自动连播已关闭");
      return;
    }
    // lpDefaultCleanMode：点击行（非开关）弹出跳转仪式三方案窗
    if (item.id === "lpDefaultCleanMode") {
      if (e.target.closest && e.target.closest("#lpDefaultCleanSwitch")) return;
      var jm = document.getElementById("jumpRitualMask");
      if (jm) {
        jm.style.display = "flex";
        if (window.refreshJumpRitualUI) window.refreshJumpRitualUI();
      }
      return;
    }
    if (item.id === "lpAutoPlay") {
      lpToast("功能待开发");
      return;
    }
    if (item.id === "lpCleanMode") {
      // 基于运行时开关状态翻转（点赞7次清屏会同步开关但不改 localStorage）
      var _cmSw = document.getElementById("lpCleanSwitch");
      var v5 = _cmSw ? !_cmSw.classList.contains("on") : !lpGetStorage("dy_default_clean");
      lpSetStorage("dy_default_clean", v5);
      saveSettingToServer("dy_default_clean", v5 ? "1" : "0");
      if (window.setCleanMode) window.setCleanMode(v5);
      lpToast(v5 ? "开启时默认清屏播放已开启" : "开启时默认清屏播放已关闭");
      return;
    }
  }, true);

  // ===== 跳转仪式方案选择弹窗 =====
  var jm = document.getElementById("jumpRitualMask");
  if (jm) {
    function closeRitual() { jm.style.display = "none"; }
    function saveRitualServer(k, v) {
      try {
        var b = {}; b[k] = v;
        fetch("/api/settings", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(b) }).catch(function () {});
      } catch (e) {}
    }
    function refreshCustomUI() {
      var customOn = false;
      try { customOn = localStorage.getItem("dy_jump_ritual_custom") === "on"; } catch (e) {}
      jm.classList.toggle("custom-on", customOn);
      var sw = document.getElementById("jumpRitualCustomSwitch");
      if (sw) sw.classList.toggle("on", customOn);
      var checks = jm.querySelectorAll(".lp-ritual-check");
      var curR = localStorage.getItem("dy_jump_ritual") || "s3";
      for (var ci = 0; ci < checks.length; ci++) {
        var ck = checks[ci].getAttribute("data-check");
        var on = customOn ? true : (ck === curR);
        checks[ci].classList.toggle("on", on);
        checks[ci].textContent = on ? "✓" : "";
      }
    }
    jm.addEventListener("click", function (e) {
      if (e.target === jm) { closeRitual(); return; }
      // 各自专用自定义开关
      if (e.target.closest && e.target.closest("#jumpRitualCustom")) {
        var now = false;
        try { now = localStorage.getItem("dy_jump_ritual_custom") === "on"; } catch (e2) {}
        var next = !now;
        try { localStorage.setItem("dy_jump_ritual_custom", next ? "on" : "off"); } catch (e3) {}
        saveRitualServer("dy_jump_ritual_custom", next ? "on" : "off");
        var outerSw = document.getElementById("lpDefaultCleanSwitch");
        if (outerSw) {
          if (next) outerSw.classList.add("on");
          else {
            var r = localStorage.getItem("dy_jump_ritual") || "s3";
            outerSw.classList.toggle("on", r !== "s1");
          }
        }
        refreshCustomUI();
        lpToast(next ? "各自专用自定义已开启" : "各自专用自定义已关闭");
        return;
      }
      var item = e.target.closest ? e.target.closest(".lp-ritual-item") : null;
      if (item) {
        var s = item.getAttribute("data-ritual");
        if (!s) return;
        var customOn = false;
        try { customOn = localStorage.getItem("dy_jump_ritual_custom") === "on"; } catch (e4) {}
        if (customOn) { lpToast("各自专用自定义开启中：三方案同时生效"); return; }
        try { localStorage.setItem("dy_jump_ritual", s); } catch (e5) {}
        if (s !== "s1") { try { localStorage.setItem("dy_jump_ritual_last", s); } catch (e6) {} }
        saveRitualServer("dy_jump_ritual", s);
        var sw2 = document.getElementById("lpDefaultCleanSwitch");
        if (sw2) sw2.classList.toggle("on", s !== "s1");
        refreshCustomUI();
        var names = { s1: "方案一·无动画直切", s2: "方案二·0.7s直接了当", s3: "方案三·0.7s粘稠柔和" };
        lpToast("跳转仪式已设为 " + (names[s] || s));
        return;
      }
    });
    window.closeJumpRitual = closeRitual;
    window.refreshJumpRitualUI = refreshCustomUI;
  }

  // ===== FLIP 动画：取消静音大胶囊 → 小圆（GPU transform）=====
  document.addEventListener("click", function (e) {
    var musicBtn = e.target.closest ? e.target.closest(".music") : null;
    if (!musicBtn) return;
    if (!musicBtn.classList.contains("prompt")) return;
    if (musicBtn.classList.contains("flipping")) return;

    var firstW = musicBtn.offsetWidth;
    var firstH = musicBtn.offsetHeight;
    if (firstW === 0 || firstH === 0) return;
    musicBtn.classList.add("flipping");

    requestAnimationFrame(function () {
      requestAnimationFrame(function () {
        var lastW = musicBtn.offsetWidth;
        var lastH = musicBtn.offsetHeight;
        if (lastW === 0 || lastH === 0) {
          musicBtn.classList.remove("flipping");
          return;
        }
        var scaleX = firstW / lastW;
        var scaleY = firstH / lastH;
        musicBtn.style.transform = "scale(" + scaleX + ", " + scaleY + ")";
        requestAnimationFrame(function () {
          musicBtn.style.transform = "scale(1)";
        });
        var onEnd = function (ev) {
          if (ev.propertyName !== "transform") return;
          musicBtn.removeEventListener("transitionend", onEnd);
          musicBtn.classList.remove("flipping");
          musicBtn.style.transform = "";
        };
        musicBtn.addEventListener("transitionend", onEnd);
        // 兜底：0.7s 强制清理
        setTimeout(function () {
          if (musicBtn.classList.contains("flipping")) {
            musicBtn.classList.remove("flipping");
            musicBtn.style.transform = "";
          }
        }, 700);
      });
    });
  }, true);
})();
